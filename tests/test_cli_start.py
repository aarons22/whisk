"""Tests for `whisk start` deciding whether there is anything to sync."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from whisk import cli


def _run_start(list_pairs, meal_sync_enabled):
    config = SimpleNamespace(
        list_pairs=list_pairs, meal_sync_enabled=meal_sync_enabled, meal_sync_days_ahead=14
    )
    manager = MagicMock()
    manager.config_exists.return_value = True
    manager.load_config.return_value = config
    daemon = MagicMock()
    daemon.start_daemon.return_value = 0
    with (
        patch("whisk.config.ConfigManager", return_value=manager),
        patch("whisk.daemon.DaemonManager", return_value=daemon),
    ):
        rc = cli.cmd_start(SimpleNamespace(config_dir=None, foreground=False))
    return rc, daemon


def test_start_with_meal_sync_only():
    rc, daemon = _run_start(list_pairs=[], meal_sync_enabled=True)
    assert rc == 0
    daemon.start_daemon.assert_called_once()


def test_start_refuses_when_nothing_to_sync():
    rc, daemon = _run_start(list_pairs=[], meal_sync_enabled=False)
    assert rc == 1
    daemon.start_daemon.assert_not_called()


def test_start_with_list_pairs_only():
    pair = SimpleNamespace(enabled=True, paprika_list="Groceries", skylight_list="Groceries")
    rc, daemon = _run_start(list_pairs=[pair], meal_sync_enabled=False)
    assert rc == 0
    daemon.start_daemon.assert_called_once()
