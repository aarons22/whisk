"""Skylight API client with optimized authentication and token caching"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

from .models import ListItem

logger = logging.getLogger(__name__)


class SkylightClient:
    """Client for interacting with Skylight API with optimized authentication"""

    BASE_URL = "https://app.ourskylight.com/api"

    def __init__(self, email: str, password: str, frame_id: str, token_cache_file: str = "skylight_token"):
        """
        Initialize Skylight client with credentials

        Args:
            email: Skylight account email
            password: Skylight account password
            frame_id: Skylight frame ID (e.g., "4878053")
            token_cache_file: Path to token cache file
        """
        self.email = email
        self.password = password
        self.frame_id = frame_id
        self.user_id: Optional[str] = None
        self.auth_token: Optional[str] = None
        self.token_cache_file = Path(token_cache_file)
        self._session = requests.Session()
        self._user_data: Optional[Dict[str, Any]] = None
        self._frames_cache: Optional[List[Dict[str, Any]]] = None
        self._lists_cache: Optional[List[Dict[str, Any]]] = None

    def authenticate(self) -> None:
        """Authenticate with Skylight API using optimized approach with token caching"""
        # Try loading cached token first
        if self._load_cached_token():
            logger.debug("Using cached Skylight token")
            return

        try:
            logger.info("Authenticating with Skylight...")

            # Try direct known method first (from CLAUDE.md research)
            if self._authenticate_direct():
                logger.info(f"✅ Skylight authenticated successfully (user_id: {self.user_id})")
                self._cache_token()
                return

            # Fallback to multi-endpoint approach
            logger.debug("Direct authentication failed, trying fallback methods...")
            if self._authenticate_fallback():
                logger.info(f"✅ Skylight authenticated via fallback (user_id: {self.user_id})")
                self._cache_token()
                return

            raise Exception("All authentication methods failed")

        except Exception as e:
            logger.error(f"Failed to authenticate with Skylight: {e}")
            raise

    def _authenticate_direct(self) -> bool:
        """
        Try direct authentication using known working endpoint from CLAUDE.md research

        Returns:
            True if authentication succeeded, False otherwise
        """
        try:
            url = f"{self.BASE_URL}/sessions"
            payload = {
                "user": {
                    "email": self.email,
                    "password": self.password
                }
            }

            logger.debug("Trying direct authentication via /sessions endpoint")
            response = self._session.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Direct login response: {data}")

                # Look for user_id and token
                if "user_id" in data and "user_token" in data:
                    self.user_id = str(data["user_id"])
                    self.auth_token = data["user_token"]
                    return True
                elif "user_id" in data and "token" in data:
                    self.user_id = str(data["user_id"])
                    self.auth_token = data["token"]
                    return True

            logger.debug(f"Direct authentication failed with status {response.status_code}")
            return False

        except Exception as e:
            logger.debug(f"Direct authentication method failed: {e}")
            return False

    def _authenticate_fallback(self) -> bool:
        """
        Fallback authentication using multiple endpoints and payload formats

        Returns:
            True if authentication succeeded, False otherwise
        """
        # Common endpoints to try for login
        login_endpoints = [
            "/sessions",
            "/auth/login",
            "/login",
            "/user/login",
            "/authenticate"
        ]

        for endpoint in login_endpoints:
            try:
                url = f"{self.BASE_URL}{endpoint}"

                # Try with various payload formats
                payloads_to_try = [
                    {"user": {"email": self.email, "password": self.password}},
                    {"email": self.email, "password": self.password},
                    {"username": self.email, "password": self.password}
                ]

                for test_payload in payloads_to_try:
                    logger.debug(f"Trying {endpoint} with payload format")
                    response = self._session.post(url, json=test_payload, timeout=10)

                    if response.status_code == 200:
                        data = response.json()

                        # Look for user_id and token in various response formats
                        if "user_id" in data and ("token" in data or "auth_token" in data or "user_token" in data):
                            self.user_id = str(data["user_id"])
                            self.auth_token = data.get("user_token") or data.get("token") or data.get("auth_token")
                            return True
                        elif "data" in data:
                            # JSON:API format
                            data_obj = data["data"]
                            if "id" in data_obj and "attributes" in data_obj:
                                self.user_id = data_obj["id"]
                                attrs = data_obj["attributes"]
                                self.auth_token = attrs.get("user_token") or attrs.get("token") or attrs.get("auth_token")
                                if self.auth_token:
                                    return True

                    elif response.status_code != 404:
                        logger.debug(f"Endpoint {endpoint}: {response.status_code}")

            except Exception as e:
                logger.debug(f"Failed to try {endpoint}: {e}")
                continue

        return False

    def _cache_token(self) -> None:
        """Cache authentication token to file to avoid repeated auth"""
        try:
            token_data = {
                "user_id": self.user_id,
                "auth_token": self.auth_token,
                "email": self.email
            }
            with open(self.token_cache_file, "w") as f:
                json.dump(token_data, f)
            # Set restrictive permissions (owner only)
            os.chmod(self.token_cache_file, 0o600)
            logger.debug(f"Cached Skylight token to {self.token_cache_file}")
        except Exception as e:
            logger.warning(f"Failed to cache Skylight token: {e}")

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
                logger.debug("Cached Skylight token is for different email")
                return False

            self.user_id = token_data.get("user_id")
            self.auth_token = token_data.get("auth_token")

            if self.user_id and self.auth_token:
                logger.debug("Loaded cached Skylight token")
                return True

            return False

        except Exception as e:
            logger.debug(f"Failed to load cached Skylight token: {e}")
            return False

    def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated, trying cached token first"""
        if self.user_id and self.auth_token:
            return

        # Try loading cached token first
        if self._load_cached_token():
            return

        # Authenticate from scratch
        self.authenticate()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Skylight API using discovered Basic Auth format

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, etc.)
            endpoint: API endpoint (e.g., "/frames/calendar")
            data: Optional data payload for POST/PATCH

        Returns:
            Parsed JSON response

        Raises:
            HTTPError: If request fails
        """
        self._ensure_authenticated()

        url = f"{self.BASE_URL}{endpoint}"

        # Use discovered Basic Auth format: user_id:auth_token
        auth_string = f"{self.user_id}:{self.auth_token}"
        auth_header = base64.b64encode(auth_string.encode()).decode()

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_header}",
            "User-Agent": "SkylightMobile (web)",
            "Origin": "https://ourskylight.com",
        }

        try:
            response = self._session.request(method, url, json=data, headers=headers)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as e:
            # Handle token expiration (401 Unauthorized)
            if e.response.status_code == 401:
                logger.warning("Skylight token expired, re-authenticating...")
                # Clear current auth data
                self.user_id = None
                self.auth_token = None
                # Remove cached token
                if self.token_cache_file.exists():
                    self.token_cache_file.unlink()

                # Re-authenticate and retry once
                self.authenticate()

                # Update auth header with new token
                auth_string = f"{self.user_id}:{self.auth_token}"
                auth_header = base64.b64encode(auth_string.encode()).decode()
                headers["Authorization"] = f"Basic {auth_header}"

                # Retry request
                response = self._session.request(method, url, json=data, headers=headers)
                response.raise_for_status()
                return response.json()

            logger.error(f"HTTP error {e.response.status_code}: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    def get_frames(self) -> List[Dict[str, Any]]:
        """
        Get all frames for the authenticated user (discovered endpoint)

        Returns:
            List of frame dictionaries with 'id', 'attributes', etc.
        """
        if self._frames_cache is None:
            try:
                logger.debug("Fetching frames from Skylight...")
                result = self._make_request("GET", "/frames/calendar")

                # Handle JSON:API format - data is an array of frame objects
                frames_data = result.get("data", [])
                self._frames_cache = frames_data
                logger.info(f"Retrieved {len(self._frames_cache)} frames")

            except Exception as e:
                logger.error(f"Failed to get frames from Skylight: {e}")
                raise

        return self._frames_cache

    def get_lists(self) -> List[Dict[str, Any]]:
        """
        Get all lists for the configured frame (discovered endpoint structure)

        Returns:
            List of skylight list dictionaries from JSON:API format
        """
        if self._lists_cache is None:
            try:
                logger.debug(f"Fetching lists from Skylight frame: {self.frame_id}")
                result = self._make_request("GET", f"/frames/{self.frame_id}/lists/")

                # Handle JSON:API format - data is an array of list objects
                lists_data = result.get("data", [])
                self._lists_cache = lists_data

                logger.info(f"Retrieved {len(self._lists_cache)} lists")

            except Exception as e:
                logger.error(f"Failed to get lists from Skylight: {e}")
                raise

        return self._lists_cache

    def get_list_id_by_name(self, list_name: str) -> Optional[str]:
        """
        Get the ID of a list by its name (using discovered attributes structure)

        Args:
            list_name: Name of the list

        Returns:
            List ID or None if not found
        """
        lists = self.get_lists()
        for list_obj in lists:
            attributes = list_obj.get("attributes", {})
            if attributes.get("label") == list_name:  # Note: uses "label" not "name"
                return list_obj.get("id")
        return None

    def get_list_items(self, list_name: str) -> List[ListItem]:
        """
        Get all items from a specific list (using discovered structure)

        Args:
            list_name: Name of the list

        Returns:
            List of ListItem objects from the specified list
        """
        try:
            logger.debug(f"Fetching items from Skylight list: {list_name}")

            # Get the list ID
            list_id = self.get_list_id_by_name(list_name)
            if not list_id:
                logger.error(f"List '{list_name}' not found")
                raise Exception(f"List '{list_name}' not found")

            # Get the specific list with items (discovered endpoint)
            result = self._make_request("GET", f"/frames/{self.frame_id}/lists/{list_id}")

            # Handle JSON:API format - items are in "included" array
            included_data = result.get("included", [])
            items = []

            for item_data in included_data:
                if item_data.get("type") == "list_item":
                    attributes = item_data.get("attributes", {})

                    # Parse timestamp - try updated_at first, then created_at
                    timestamp = None
                    updated_at = attributes.get("updated_at") or attributes.get("modified_at") or attributes.get("last_modified_at")
                    created_at = attributes.get("created_at")

                    # Prefer updated_at if available
                    timestamp_str = updated_at or created_at
                    if timestamp_str:
                        try:
                            # Handle ISO 8601 format
                            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse timestamp for {attributes.get('label')}: {e}"
                            )

                    # Map Skylight's status to our checked boolean
                    # Based on DevTools: "completed" = checked, "pending" = unchecked
                    status = attributes.get("status", "pending")
                    checked = (status == "completed")

                    item = ListItem(
                        name=attributes.get("label", ""),  # Note: uses "label" not "name"
                        checked=checked,
                        skylight_id=str(attributes.get("id")),  # Convert to string
                        skylight_timestamp=timestamp,
                    )
                    items.append(item)

            logger.info(f"Retrieved {len(items)} items from '{list_name}'")
            return items

        except Exception as e:
            logger.error(f"Failed to get list items from Skylight: {e}")
            raise

    def add_item(self, name: str, list_name: str, checked: bool = False) -> str:
        """
        Add item to list (using discovered JSON:API structure)

        Args:
            name: Item name
            checked: Whether item is checked
            list_name: Name of the list to add to

        Returns:
            Skylight ID of created item
        """
        try:
            logger.debug(f"Adding item to Skylight list '{list_name}': {name} (checked={checked})")

            # Get the list ID
            list_id = self.get_list_id_by_name(list_name)
            if not list_id:
                logger.error(f"List '{list_name}' not found")
                raise Exception(f"List '{list_name}' not found")

            # Prepare JSON:API format request (corrected based on validation error)
            status = "completed" if checked else "pending"

            # Try different payload structures
            payloads_to_try = [
                # Standard JSON:API format
                {
                    "data": {
                        "type": "list_item",
                        "attributes": {
                            "label": name,
                            "status": status,
                            "section": None,
                            "position": 1
                        }
                    }
                },
                # Simplified format
                {
                    "list_item": {
                        "label": name,
                        "status": status
                    }
                },
                # Direct attributes
                {
                    "label": name,
                    "status": status,
                    "section": None,
                    "position": 1
                }
            ]

            for i, data in enumerate(payloads_to_try):
                try:
                    logger.debug(f"Trying payload format {i+1}: {data}")
                    result = self._make_request("POST", f"/frames/{self.frame_id}/lists/{list_id}/list_items", data)

                    # Extract the created item ID from JSON:API response
                    created_item = result.get("data", {})
                    item_id = created_item.get("id")

                    if item_id:
                        logger.info(f"Added item to Skylight '{list_name}': {name} (id={item_id})")
                        return str(item_id)

                except Exception as e:
                    logger.debug(f"Payload format {i+1} failed: {e}")
                    if i == len(payloads_to_try) - 1:  # Last attempt
                        raise

            raise Exception("All payload formats failed")

        except Exception as e:
            logger.error(f"Failed to add item to Skylight: {e}")
            raise

    def update_item(self, skylight_id: str, checked: bool, name: Optional[str] = None, list_name: str = None) -> None:
        """
        Update item (checked status or name) using discovered PUT method with explicit status

        Args:
            skylight_id: Skylight ID of the item
            checked: New checked status
            name: Optional new name for the item
            list_name: Required list name for security (will not search all lists)
        """
        try:
            logger.debug(f"Updating item in Skylight: {skylight_id} (checked={checked}, name={name})")

            if not list_name:
                raise ValueError("list_name is required - will not search all lists for security")

            # Only search in the specified list (NEVER search other lists)
            list_id = self.get_list_id_by_name(list_name)
            if not list_id:
                raise Exception(f"List '{list_name}' not found")

            # Verify item exists in this specific list
            items = self.get_list_items(list_name)
            item_found = any(item.skylight_id == skylight_id for item in items)
            if not item_found:
                raise Exception(f"Item {skylight_id} not found in list '{list_name}'")

            # Prepare the request body with explicit status value
            status = "completed" if checked else "pending"
            body = {"status": status}

            # If we need to update the name, add it to the body
            if name is not None:
                body["label"] = name

            # Use PUT with explicit status (discovered working method)
            endpoint = f"/frames/{self.frame_id}/lists/{list_id}/list_items/{skylight_id}"
            url = f"{self.BASE_URL}{endpoint}"

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Basic {base64.b64encode(f'{self.user_id}:{self.auth_token}'.encode()).decode()}",
                "User-Agent": "SkylightMobile (web)",
                "Origin": "https://ourskylight.com",
            }

            response = self._session.put(url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()
            actual_status = result.get("data", {}).get("attributes", {}).get("status")
            logger.info(f"Updated item in Skylight: {skylight_id} (new status: {actual_status})")

        except Exception as e:
            logger.error(f"Failed to update item in Skylight: {e}")
            raise

    def remove_item(self, skylight_id: str, list_name: str = None) -> None:
        """
        Remove item from list

        Args:
            skylight_id: Skylight ID of the item to remove
            list_name: Optional list name to search in (REQUIRED for security)
        """
        try:
            logger.debug(f"Removing item from Skylight: {skylight_id}")

            if not list_name:
                raise ValueError("list_name is required - will not search all lists for security")

            list_id = None

            # Only search in the specified list (NEVER search other lists)
            try:
                target_list_id = self.get_list_id_by_name(list_name)
                if not target_list_id:
                    raise Exception(f"List '{list_name}' not found")

                # Check if item exists in this specific list
                items = self.get_list_items(list_name)
                if any(item.skylight_id == skylight_id for item in items):
                    list_id = target_list_id
                    logger.debug(f"Found item {skylight_id} in target list '{list_name}'")
                else:
                    raise Exception(f"Item {skylight_id} not found in list '{list_name}'")

            except Exception as e:
                raise Exception(f"Cannot remove item {skylight_id}: {e}")

            # DELETE request
            self._make_request("DELETE", f"/frames/{self.frame_id}/lists/{list_id}/list_items/{skylight_id}")
            logger.info(f"Removed item from Skylight list '{list_name}': {skylight_id}")

        except Exception as e:
            logger.error(f"Failed to remove item from Skylight: {e}")
            raise