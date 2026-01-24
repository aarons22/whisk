"""Paprika API client using reverse-engineered REST API"""

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

from .models import GroceryItem

logger = logging.getLogger(__name__)


class PaprikaClient:
    """Client for interacting with Paprika grocery lists via reverse-engineered API"""

    BASE_URL = "https://www.paprikaapp.com/api"

    def __init__(self, email: str, password: str, token_cache_file: str = ".paprika_token"):
        """
        Initialize Paprika client with credentials

        Args:
            email: Paprika account email
            password: Paprika account password
            token_cache_file: Path to cache authentication token
        """
        self.email = email
        self.password = password
        self.token_cache_file = Path(token_cache_file)
        self.token: Optional[str] = None
        self._session = requests.Session()

    def authenticate(self) -> None:
        """Authenticate with Paprika API using V1 auth (more stable than V2)"""
        try:
            logger.info("Authenticating with Paprika...")

            url = f"{self.BASE_URL}/v1/account/login/"
            data = {"email": self.email, "password": self.password}

            response = self._session.post(url, json=data)
            response.raise_for_status()

            result = response.json()
            self.token = result.get("result", {}).get("token")

            if not self.token:
                raise Exception("No token in authentication response")

            logger.info("Successfully authenticated with Paprika")
            self._cache_token()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Invalid Paprika credentials")
            else:
                logger.error(f"HTTP error during authentication: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to authenticate with Paprika: {e}")
            raise

    def _cache_token(self) -> None:
        """Cache authentication token to file to avoid repeated auth"""
        try:
            token_data = {"token": self.token, "email": self.email}
            with open(self.token_cache_file, "w") as f:
                json.dump(token_data, f)
            # Set restrictive permissions (owner only)
            self.token_cache_file.chmod(0o600)
            logger.debug(f"Cached token to {self.token_cache_file}")
        except Exception as e:
            logger.warning(f"Failed to cache token: {e}")

    def _load_cached_token(self) -> bool:
        """
        Load cached token if available

        Returns:
            True if token loaded successfully, False otherwise
        """
        try:
            if not self.token_cache_file.exists():
                return False

            with open(self.token_cache_file, "r") as f:
                token_data = json.load(f)

            if token_data.get("email") != self.email:
                logger.debug("Cached token is for different email")
                return False

            self.token = token_data.get("token")
            logger.debug("Loaded cached token")
            return True

        except Exception as e:
            logger.debug(f"Failed to load cached token: {e}")
            return False

    def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated, trying cached token first"""
        if self.token:
            return

        # Try loading cached token first
        if self._load_cached_token():
            # Verify token still works by making a test request
            try:
                self._make_request("GET", "/v2/sync/groceries/")
                logger.debug("Cached token is valid")
                return
            except Exception as e:
                logger.debug(f"Cached token invalid: {e}")
                self.token = None

        # Cached token didn't work, authenticate fresh
        self.authenticate()

    def _make_request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Paprika API

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint (e.g., "/v2/sync/groceries/")
            data: Optional data payload for POST/PUT

        Returns:
            Parsed JSON response

        Raises:
            HTTPError: If request fails
        """
        self._ensure_authenticated()

        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept-Encoding": "gzip",
        }

        try:
            response = self._session.request(method, url, json=data, headers=headers)

            # Handle 401 (token expired) - re-authenticate and retry once
            if response.status_code == 401:
                logger.debug("Token expired, re-authenticating...")
                self.token = None
                if self.token_cache_file.exists():
                    self.token_cache_file.unlink()
                self.authenticate()

                # Retry request with new token
                headers["Authorization"] = f"Bearer {self.token}"
                response = self._session.request(method, url, json=data, headers=headers)

            response.raise_for_status()

            # Handle gzip-compressed responses
            content = response.content
            if response.headers.get("Content-Encoding") == "gzip":
                content = gzip.decompress(content)

            return json.loads(content)

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    def get_grocery_list(self, list_name: str = "Test List") -> List[GroceryItem]:
        """
        Get all items from grocery list

        Args:
            list_name: Name of the grocery list (currently unused - Paprika returns all items)

        Returns:
            List of GroceryItem objects
        """
        try:
            logger.debug("Fetching grocery items from Paprika...")

            result = self._make_request("GET", "/v2/sync/groceries/")
            groceries = result.get("result", [])

            items = []
            for grocery in groceries:
                # Parse timestamp
                timestamp = None
                updated_at = grocery.get("updated_at") or grocery.get("created")
                if updated_at:
                    try:
                        # Handle various timestamp formats
                        timestamp_str = updated_at.replace("Z", "+00:00")
                        timestamp = datetime.fromisoformat(timestamp_str)
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse timestamp for {grocery.get('name')}: {e}"
                        )

                item = GroceryItem(
                    name=grocery.get("name", ""),
                    checked=grocery.get("purchased", False),
                    paprika_id=grocery.get("uid"),
                    paprika_timestamp=timestamp,
                )
                items.append(item)

            logger.info(f"Retrieved {len(items)} items from Paprika")
            return items

        except Exception as e:
            logger.error(f"Failed to get grocery list from Paprika: {e}")
            raise

    def add_item(self, name: str, checked: bool = False) -> str:
        """
        Add item to grocery list (aisle auto-assigned by Paprika)

        Args:
            name: Item name
            checked: Whether item is checked/purchased

        Returns:
            Paprika UID of created item
        """
        try:
            logger.debug(f"Adding item to Paprika: {name} (checked={checked})")

            # Create grocery item payload
            # Note: Paprika auto-assigns aisle, so we don't specify it
            data = {
                "name": name,
                "purchased": checked,
            }

            result = self._make_request("POST", "/v2/sync/groceries/", data=data)
            uid = result.get("result", {}).get("uid")

            if not uid:
                raise Exception("No UID returned from create operation")

            logger.info(f"Added item to Paprika: {name} (uid={uid})")
            return uid

        except Exception as e:
            logger.error(f"Failed to add item to Paprika: {e}")
            raise

    def update_item(self, paprika_id: str, checked: bool, name: Optional[str] = None) -> None:
        """
        Update item (checked status or name)

        Args:
            paprika_id: Paprika UID of the item
            checked: New checked status
            name: Optional new name for the item
        """
        try:
            logger.debug(f"Updating item in Paprika: {paprika_id} (checked={checked})")

            # Build update payload
            data = {"uid": paprika_id, "purchased": checked}
            if name:
                data["name"] = name

            self._make_request("POST", f"/v2/sync/groceries/{paprika_id}", data=data)
            logger.info(f"Updated item in Paprika: {paprika_id}")

        except Exception as e:
            logger.error(f"Failed to update item in Paprika: {e}")
            raise

    def remove_item(self, paprika_id: str) -> None:
        """
        Remove item from grocery list

        Args:
            paprika_id: Paprika UID of the item to remove
        """
        try:
            logger.debug(f"Removing item from Paprika: {paprika_id}")
            self._make_request("DELETE", f"/v2/sync/groceries/{paprika_id}")
            logger.info(f"Removed item from Paprika: {paprika_id}")

        except Exception as e:
            logger.error(f"Failed to remove item from Paprika: {e}")
            raise
