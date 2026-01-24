"""Paprika API client using reverse-engineered REST API"""

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

from models import GroceryItem

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
        self._grocery_lists_cache: Optional[List[Dict[str, Any]]] = None

    def authenticate(self) -> None:
        """Authenticate with Paprika API using V1 auth (more stable than V2)"""
        try:
            logger.info("Authenticating with Paprika...")

            url = f"{self.BASE_URL}/v1/account/login/"

            # V1 API requires HTTP Basic Auth + form data
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(self.email, self.password)
            data = {"email": self.email, "password": self.password}

            response = self._session.post(url, data=data, auth=auth)
            response.raise_for_status()

            result = response.json()
            logger.debug(f"Auth response: {result}")

            # Response format: {"result": {"token": "..."}}
            self.token = result.get("result", {}).get("token") or result.get("token")

            if not self.token:
                logger.error(f"Unexpected auth response format: {result}")
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
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        gzip_form_data: bool = False,
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Paprika API

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint (e.g., "/v2/sync/groceries/")
            data: Optional data payload for POST/PUT
            gzip_form_data: If True, gzip compress data and send as multipart form

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
            # Prepare request based on data format
            if gzip_form_data and data:
                # Gzip compress JSON and send as multipart form data
                json_data = json.dumps(data).encode("utf-8")
                compressed_data = gzip.compress(json_data)
                files = {"data": ("data", compressed_data, "application/octet-stream")}
                response = self._session.request(method, url, files=files, headers=headers)
            else:
                # Regular JSON request
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
                if gzip_form_data and data:
                    json_data = json.dumps(data).encode("utf-8")
                    compressed_data = gzip.compress(json_data)
                    files = {"data": ("data", compressed_data, "application/octet-stream")}
                    response = self._session.request(method, url, files=files, headers=headers)
                else:
                    response = self._session.request(method, url, json=data, headers=headers)

            response.raise_for_status()

            # Handle gzip-compressed responses
            content = response.content
            content_encoding = response.headers.get("Content-Encoding", "").lower()

            # Try to decompress if content encoding indicates gzip
            # or if the content starts with gzip magic number
            if content_encoding == "gzip" or (content and content[:2] == b"\x1f\x8b"):
                try:
                    content = gzip.decompress(content)
                except Exception as e:
                    logger.debug(f"Failed to decompress gzip (might not be compressed): {e}")

            return json.loads(content)

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    def get_grocery_lists(self) -> List[Dict[str, Any]]:
        """
        Get all grocery lists with their UIDs and names

        Returns:
            List of grocery list dictionaries with 'uid', 'name', 'is_default', etc.
        """
        if self._grocery_lists_cache is None:
            try:
                logger.debug("Fetching grocery lists from Paprika...")
                result = self._make_request("GET", "/v2/sync/grocerylists/")
                self._grocery_lists_cache = result.get("result", [])
                logger.info(f"Retrieved {len(self._grocery_lists_cache)} grocery lists")
            except Exception as e:
                logger.error(f"Failed to get grocery lists from Paprika: {e}")
                raise

        return self._grocery_lists_cache

    def get_list_uid_by_name(self, list_name: str) -> Optional[str]:
        """
        Get the UID of a grocery list by its name

        Args:
            list_name: Name of the grocery list

        Returns:
            List UID or None if not found
        """
        lists = self.get_grocery_lists()
        for grocery_list in lists:
            if grocery_list.get("name") == list_name:
                return grocery_list.get("uid")
        return None

    def get_grocery_list(self, list_name: str) -> List[GroceryItem]:
        """
        Get all items from a specific grocery list

        Args:
            list_name: Name of the grocery list to filter by

        Returns:
            List of GroceryItem objects from the specified list
        """
        try:
            logger.debug(f"Fetching grocery items from Paprika list: {list_name}")

            # Get the list UID for filtering
            list_uid = self.get_list_uid_by_name(list_name)
            if not list_uid:
                logger.warning(f"Grocery list '{list_name}' not found, returning all items")

            result = self._make_request("GET", "/v2/sync/groceries/")
            groceries = result.get("result", [])

            items = []
            for grocery in groceries:
                # Filter by list_uid if specified
                if list_uid and grocery.get("list_uid") != list_uid:
                    continue

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

            logger.info(f"Retrieved {len(items)} items from '{list_name}'")
            return items

        except Exception as e:
            logger.error(f"Failed to get grocery list from Paprika: {e}")
            raise

    def add_item(self, name: str, checked: bool = False, list_name: str) -> str:
        """
        Add item to grocery list (aisle auto-assigned by Paprika)

        Args:
            name: Item name
            checked: Whether item is checked/purchased
            list_name: Name of the grocery list to add to

        Returns:
            Paprika UID of created item
        """
        try:
            logger.debug(f"Adding item to Paprika list '{list_name}': {name} (checked={checked})")

            # Get the list UID
            list_uid = self.get_list_uid_by_name(list_name)
            if not list_uid:
                logger.warning(f"List '{list_name}' not found, using default list")
                # Get default list
                lists = self.get_grocery_lists()
                default_list = next((l for l in lists if l.get("is_default")), None)
                if default_list:
                    list_uid = default_list.get("uid")
                    logger.debug(f"Using default list: {default_list.get('name')}")

            # Generate a UUID for the item
            import uuid
            uid = str(uuid.uuid4()).upper()

            # Create grocery item - API requires gzip-compressed JSON array
            grocery_item = {
                "uid": uid,
                "recipe_uid": None,
                "name": name,
                "order_flag": 0,
                "purchased": checked,
                "aisle": "",  # Will be auto-assigned by Paprika
                "ingredient": name.lower(),  # Use name as ingredient
                "recipe": None,
                "instruction": "",
                "quantity": "",
                "separate": False,
                "list_uid": list_uid,  # Specify which list to add to
            }

            # API expects an array, send as gzipped multipart form data
            result = self._make_request(
                "POST", "/v2/sync/groceries/", data=[grocery_item], gzip_form_data=True
            )
            logger.debug(f"Create response: {result}")

            # Check for success
            if result.get("error"):
                error_msg = result.get("error", {}).get("message", "Unknown error")
                raise Exception(f"API error: {error_msg}")

            if not result.get("result"):
                raise Exception("Create operation did not return success")

            logger.info(f"Added item to Paprika '{list_name}': {name} (uid={uid})")
            return uid

        except Exception as e:
            logger.error(f"Failed to add item to Paprika: {e}")
            raise

    def update_item(self, paprika_id: str, checked: bool, name: Optional[str] = None, list_name: str = None) -> None:
        """
        Update item (checked status or name)

        Args:
            paprika_id: Paprika UID of the item
            checked: New checked status
            name: Optional new name for the item
            list_name: Name of the grocery list containing the item
        """
        if list_name is None:
            raise ValueError("list_name parameter is required")

        try:
            logger.debug(f"Updating item in Paprika: {paprika_id} (checked={checked})")

            # Get current item details first
            items = self.get_grocery_list(list_name)
            current_item = next((item for item in items if item.paprika_id == paprika_id), None)

            if not current_item:
                raise Exception(f"Item {paprika_id} not found in grocery list")

            # Get full item data from API
            result = self._make_request("GET", "/v2/sync/groceries/")
            full_items = result.get("result", [])
            full_item = next((item for item in full_items if item["uid"] == paprika_id), None)

            if not full_item:
                raise Exception(f"Item {paprika_id} not found in full item list")

            # Update fields
            full_item["purchased"] = checked
            if name:
                full_item["name"] = name
                full_item["ingredient"] = name.lower()

            # Send as gzipped array
            result = self._make_request(
                "POST", "/v2/sync/groceries/", data=[full_item], gzip_form_data=True
            )

            if not result.get("result"):
                raise Exception("Update operation did not return success")

            logger.info(f"Updated item in Paprika: {paprika_id}")

        except Exception as e:
            logger.error(f"Failed to update item in Paprika: {e}")
            raise

    def remove_item(self, paprika_id: str) -> None:
        """
        Remove item from grocery list

        Note: Paprika uses a sync-based API. To delete an item, we need to
        upload the full list without the deleted item, or mark it appropriately.
        For now, we'll try the DELETE endpoint.

        Args:
            paprika_id: Paprika UID of the item to remove
        """
        try:
            logger.debug(f"Removing item from Paprika: {paprika_id}")

            # Try DELETE endpoint first
            try:
                self._make_request("DELETE", f"/v2/sync/groceries/{paprika_id}")
                logger.info(f"Removed item from Paprika: {paprika_id}")
                return
            except requests.exceptions.HTTPError as e:
                if e.response.status_code != 404:
                    raise

            # DELETE endpoint might not be supported, fallback approach:
            # Set purchased=True and order_flag very high to "hide" it
            logger.debug("DELETE endpoint not supported, using update workaround")
            self.update_item(paprika_id, checked=True)
            logger.info(f"Marked item as purchased in Paprika: {paprika_id}")

        except Exception as e:
            logger.error(f"Failed to remove item from Paprika: {e}")
            raise
