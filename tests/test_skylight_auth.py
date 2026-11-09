"""Tests for Skylight login flow, including emailed verification codes (2FA)."""

import base64
import hashlib
import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from whisk import skylight_client as sc
from whisk.skylight_client import SkylightAuthError, SkylightClient

BASE = "https://app.ourskylight.com"
LOGIN_HTML = '<meta name="csrf-token" content="LOGINTOKEN" />'
MFA_HTML = (
    '<form action="/auth/mfa_challenge" method="post">'
    '<input type="hidden" name="authenticity_token" value="MFATOKEN" />'
    '<input type="text" name="code" /></form>'
)


def _resp(status=200, location=None, text="", url=""):
    r = MagicMock()
    r.status_code = status
    r.headers = {"Location": location} if location else {}
    r.text = text
    r.url = url
    r.raise_for_status = MagicMock()
    return r


class FakeSession:
    """Scripted stand-in for requests.Session used during login."""

    def __init__(self, post_login_location, mfa_results=()):
        self.post_login_location = post_login_location
        self.mfa_results = list(mfa_results)  # locations returned for each code submission
        self.posts = []
        self.gets = []
        self.omit_state = False

    def get(self, url, **kwargs):
        self.gets.append(url)
        if url.endswith("/auth/session/new"):
            return _resp(text=LOGIN_HTML, url=url)
        if "/auth/mfa_challenge" in url:
            return _resp(text=MFA_HTML, url=f"{BASE}/auth/mfa_challenge/new")
        if url.endswith("/auth/session/success"):
            self.visited_success = True
            return _resp(text="ok", url=url)
        if "/oauth/authorize" in url:
            q = parse_qs(urlparse(url).query)
            if q.get("code_challenge_method") != ["S256"] or not q.get("code_challenge"):
                # Mirrors Skylight's real response when PKCE is missing
                return _resp(
                    400, text="<h1>An error has occurred</h1><p>Code challenge is required.</p>"
                )
            self.code_challenge = q["code_challenge"][0]
            state = "" if self.omit_state else f"&state={q['state'][0]}"
            return _resp(302, f"https://ourskylight.com/welcome?code=AUTHCODE{state}")
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, data=None, **kwargs):
        self.posts.append((url, data))
        if url.endswith("/auth/session"):
            return _resp(302, self.post_login_location)
        if url.endswith("/auth/mfa_challenge"):
            return _resp(302, self.mfa_results.pop(0))
        raise AssertionError(f"unexpected POST {url}")


def _token_response():
    r = _resp()
    r.json.return_value = {"access_token": "AT", "refresh_token": "RT", "expires_in": 7200}
    return r


def _client(tmp_path, provider=None):
    return SkylightClient(
        "a@b.com", "pw", "frame", str(tmp_path / "tok"), mfa_code_provider=provider
    )


def test_login_without_mfa(tmp_path):
    fake = FakeSession(f"{BASE}/auth/session/success")
    with (
        patch.object(sc.requests, "Session", return_value=fake),
        patch.object(sc.requests, "post", return_value=_token_response()),
    ):
        client = _client(tmp_path, provider=lambda: pytest.fail("should not prompt"))
        client._do_login()
        exchange = sc.requests.post.call_args.kwargs["data"]
    # PKCE: verifier sent at token exchange must hash to the challenge sent at authorize
    digest = hashlib.sha256(exchange["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == fake.code_challenge
    assert fake.visited_success
    assert client.access_token == "AT"


def test_bad_credentials_raise_clear_error(tmp_path):
    fake = FakeSession(f"{BASE}/auth/session/new")
    with patch.object(sc.requests, "Session", return_value=fake):
        with pytest.raises(SkylightAuthError, match="incorrect email or password"):
            _client(tmp_path)._do_login()


def test_mfa_code_is_prompted_and_submitted(tmp_path):
    fake = FakeSession(
        f"{BASE}/auth/mfa_challenge/start", mfa_results=[f"{BASE}/auth/session/success"]
    )
    with (
        patch.object(sc.requests, "Session", return_value=fake),
        patch.object(sc.requests, "post", return_value=_token_response()),
    ):
        client = _client(tmp_path, provider=lambda: " 123456 ")
        client._do_login()
    assert (
        f"{BASE}/auth/mfa_challenge",
        {"authenticity_token": "MFATOKEN", "code": "123456"},
    ) in fake.posts
    assert client.access_token == "AT"


def test_mfa_retries_after_wrong_code(tmp_path):
    fake = FakeSession(
        f"{BASE}/auth/mfa_challenge/start",
        mfa_results=[f"{BASE}/auth/mfa_challenge/new", f"{BASE}/auth/session/success"],
    )
    codes = iter(["000000", "123456"])
    with (
        patch.object(sc.requests, "Session", return_value=fake),
        patch.object(sc.requests, "post", return_value=_token_response()),
    ):
        client = _client(tmp_path, provider=lambda: next(codes))
        client._do_login()
    submitted = [d["code"] for u, d in fake.posts if u.endswith("/auth/mfa_challenge")]
    assert submitted == ["000000", "123456"]


def test_mfa_without_terminal_stops_before_sending_email(tmp_path):
    fake = FakeSession(f"{BASE}/auth/mfa_challenge/start")
    with (
        patch.object(sc.requests, "Session", return_value=fake),
        patch.object(sc.sys, "stdin", None),
    ):
        with pytest.raises(SkylightAuthError, match="verification code"):
            _client(tmp_path)._do_login()
    # /auth/mfa_challenge/start (which emails the code) must never be requested
    assert not any("mfa_challenge" in u for u in fake.gets)
    # ...and the account is remembered as 2FA for the next unattended run
    assert json.loads((tmp_path / "tok").read_text())["mfa_required"] is True


def test_known_mfa_account_without_terminal_makes_no_requests(tmp_path):
    (tmp_path / "tok").write_text(json.dumps({"email": "a@b.com", "mfa_required": True}))
    client = _client(tmp_path)
    no_network = MagicMock(side_effect=AssertionError("must not contact Skylight"))
    with (
        patch.object(sc.requests, "Session", no_network),
        patch.object(sc.requests, "post", no_network),
        patch.object(client._session, "request", no_network),
        patch.object(sc.sys, "stdin", None),
    ):
        with pytest.raises(SkylightAuthError, match="verification code"):
            client.authenticate()


def test_mfa_flag_survives_failed_refresh_and_is_cached_after_login(tmp_path):
    fake = FakeSession(
        f"{BASE}/auth/mfa_challenge/start", mfa_results=[f"{BASE}/auth/session/success"]
    )
    with (
        patch.object(sc.requests, "Session", return_value=fake),
        patch.object(sc.requests, "post", return_value=_token_response()),
    ):
        _client(tmp_path, provider=lambda: "123456")._do_login()
    cached = json.loads((tmp_path / "tok").read_text())
    assert cached["mfa_required"] is True and cached["access_token"] == "AT"


def test_login_without_mfa_clears_stale_flag(tmp_path):
    fake = FakeSession(f"{BASE}/auth/session/success")
    with (
        patch.object(sc.requests, "Session", return_value=fake),
        patch.object(sc.requests, "post", return_value=_token_response()),
    ):
        client = _client(tmp_path, provider=lambda: "unused")
        client.mfa_required = True  # user has since turned 2FA off
        client._do_login()
    assert json.loads((tmp_path / "tok").read_text())["mfa_required"] is False


def test_missing_oauth_state_is_rejected(tmp_path):
    fake = FakeSession(f"{BASE}/auth/session/success")
    fake.omit_state = True
    with patch.object(sc.requests, "Session", return_value=fake):
        with pytest.raises(SkylightAuthError, match="state mismatch"):
            _client(tmp_path)._do_login()


def test_failed_setup_login_keeps_existing_token(tmp_path):
    from whisk.setup_wizard import SetupWizard

    token = tmp_path / "skylight_token"
    token.write_text('{"email": "a@b.com", "access_token": "OLD"}')
    wizard = SetupWizard(tmp_path)
    with patch.object(
        sc.SkylightClient, "authenticate", side_effect=SkylightAuthError("bad password")
    ):
        assert wizard._test_skylight_auth_and_discover_frames("a@b.com", "wrong") is None
    assert json.loads(token.read_text())["access_token"] == "OLD"
    assert not (tmp_path / "skylight_token_temp").exists()


def test_successful_setup_login_promotes_token(tmp_path):
    from whisk.setup_wizard import SetupWizard

    wizard = SetupWizard(tmp_path)

    def fake_auth(self):
        self.access_token, self.refresh_token, self._token_expires_at = "NEW", "RT", 9e9
        self._cache_token()

    with (
        patch.object(sc.SkylightClient, "authenticate", fake_auth),
        patch.object(sc.SkylightClient, "get_frames", return_value=[{"id": "f1"}]),
    ):
        assert wizard._test_skylight_auth_and_discover_frames("a@b.com", "pw") == [{"id": "f1"}]
    assert json.loads((tmp_path / "skylight_token").read_text())["access_token"] == "NEW"
    assert not (tmp_path / "skylight_token_temp").exists()
