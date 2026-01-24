"""Skylight API client using actual API structure discovered via browser DevTools"""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import requests

from models import GroceryItem

logger = logging.getLogger(__name__)


class SkylightClient:
    """Client for interacting with Skylight grocery lists via discovered API structure"""

    BASE_URL = "https://app.ourskylight.com/api"

    def __init__(self, email: str, password: str, frame_id: str):
        """
        Initialize Skylight client with credentials

        Args:
            email: Skylight account email
            password: Skylight account password
            frame_id: Skylight frame ID (e.g., "4878053")
        """
        self.email = email
        self.password = password
        self.frame_id = frame_id
        self.user_id: Optional[str] = None
        self.auth_token: Optional[str] = None
        self._session = requests.Session()
        self._user_data: Optional[Dict[str, Any]] = None
        self._frames_cache: Optional[List[Dict[str, Any]]] = None
        self._lists_cache: Optional[List[Dict[str, Any]]] = None

    def authenticate(self) -> None:
        """Authenticate with Skylight API using discovered two-step process"""
        try:
            logger.info("Authenticating with Skylight...")

            # Step 1: Try to get auth token with email/password (need to find the endpoint)
            # Common endpoints to try for login
            login_endpoints = [
                "/sessions",
                "/auth/login",
                "/login",
                "/user/login",
                "/authenticate"
            ]

            auth_token = None
            user_id = None

            for endpoint in login_endpoints:
                try:
                    url = f"{self.BASE_URL}{endpoint}"
                    payload = {
                        "user": {
                            "email": self.email,
                            "password": self.password
                        }
                    }

                    # Try with various payload formats
                    payloads_to_try = [
                        payload,
                        {"email": self.email, "password": self.password},
                        {"username": self.email, "password": self.password}
                    ]

                    for test_payload in payloads_to_try:
                        logger.debug(f"Trying {endpoint} with payload format")
                        response = self._session.post(url, json=test_payload, timeout=10)

                        if response.status_code == 200:
                            data = response.json()
                            logger.debug(f"Login response: {data}")

                            # Look for user_id and token in various response formats
                            if "user_id" in data and ("token" in data or "auth_token" in data):
                                user_id = str(data["user_id"])
                                auth_token = data.get("token") or data.get("auth_token")
                                break
                            elif "data" in data:
                                # JSON:API format
                                data_obj = data["data"]
                                if "id" in data_obj and "attributes" in data_obj:
                                    user_id = data_obj["id"]
                                    attrs = data_obj["attributes"]
                                    auth_token = attrs.get("token") or attrs.get("auth_token")
                                    if auth_token:
                                        break

                        elif response.status_code != 404:
                            logger.debug(f"Endpoint {endpoint}: {response.status_code}")

                    if auth_token and user_id:
                        break

                except Exception as e:
                    logger.debug(f"Failed to try {endpoint}: {e}")
                    continue

            if not auth_token or not user_id:
                # If we can't find a login endpoint, we might need to manually set the token
                # For now, let's try using the discovered pattern from DevTools
                logger.warning("Could not find login endpoint. You may need to extract the auth token manually from DevTools.")
                raise Exception("Authentication failed - no login endpoint found. Check DevTools for auth token.")

            self.user_id = user_id
            self.auth_token = auth_token
            logger.info(f"Successfully authenticated with Skylight (user_id: {self.user_id})")

        except Exception as e:
            logger.error(f"Failed to authenticate with Skylight: {e}")
            raise

    def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated"""
        if not self.user_id or not hasattr(self, 'auth_token'):
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
            List of grocery list dictionaries from JSON:API format
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

    def get_grocery_list(self, list_name: str = "Test List") -> List[GroceryItem]:
        """
        Get all items from a specific grocery list (using discovered structure)

        Args:
            list_name: Name of the grocery list

        Returns:
            List of GroceryItem objects from the specified list
        """
        try:
            logger.debug(f"Fetching grocery items from Skylight list: {list_name}")

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

                    # Parse timestamp
                    timestamp = None
                    created_at = attributes.get("created_at")
                    if created_at:
                        try:
                            # Handle ISO 8601 format
                            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse timestamp for {attributes.get('label')}: {e}"
                            )

                    # Map Skylight's status to our checked boolean
                    # Based on DevTools: "completed" = checked, "pending" = unchecked
                    status = attributes.get("status", "pending")
                    checked = (status == "completed")

                    item = GroceryItem(
                        name=attributes.get("label", ""),  # Note: uses "label" not "name"
                        checked=checked,
                        skylight_id=str(attributes.get("id")),  # Convert to string
                        skylight_timestamp=timestamp,
                    )
                    items.append(item)

            logger.info(f"Retrieved {len(items)} items from '{list_name}'")
            return items

        except Exception as e:
            logger.error(f"Failed to get grocery list from Skylight: {e}")
            raise

    def add_item(self, name: str, checked: bool = False, list_name: str = "Test List") -> str:
        """
        Add item to grocery list (using discovered JSON:API structure)

        Args:
            name: Item name
            checked: Whether item is checked
            list_name: Name of the grocery list to add to

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

    def update_item(self, skylight_id: str, checked: bool, name: Optional[str] = None) -> None:
        """
        Update item (checked status or name) using discovered PUT method with explicit status

        Args:
            skylight_id: Skylight ID of the item
            checked: New checked status
            name: Optional new name for the item
        """
        try:
            logger.debug(f"Updating item in Skylight: {skylight_id} (checked={checked}, name={name})")

            # We need to find which list this item belongs to
            lists = self.get_lists()
            list_id = None

            # Find the item across all lists
            for lst in lists:
                try:
                    list_name = lst.get("attributes", {}).get("label", "")
                    items = self.get_grocery_list(list_name)
                    for item in items:
                        if item.skylight_id == skylight_id:
                            list_id = lst.get("id")
                            break
                    if list_id:
                        break
                except Exception:
                    continue  # Skip lists we can't access

            if not list_id:
                raise Exception(f"Item {skylight_id} not found in any list")

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

    def remove_item(self, skylight_id: str) -> None:
        """
        Remove item from grocery list

        Args:
            skylight_id: Skylight ID of the item to remove
        """
        try:
            logger.debug(f"Removing item from Skylight: {skylight_id}")

            # We need to find which list this item belongs to
            lists = self.get_lists()
            list_id = None

            # Find the item across all lists
            for lst in lists:
                try:
                    list_name = lst.get("attributes", {}).get("label", "")
                    items = self.get_grocery_list(list_name)
                    for item in items:
                        if item.skylight_id == skylight_id:
                            list_id = lst.get("id")
                            break
                    if list_id:
                        break
                except Exception:
                    continue  # Skip lists we can't access

            if not list_id:
                raise Exception(f"Item {skylight_id} not found in any list")

            # DELETE request - typically no body needed
            self._make_request("DELETE", f"/frames/{self.frame_id}/lists/{list_id}/list_items/{skylight_id}")
            logger.info(f"Removed item from Skylight: {skylight_id}")

        except Exception as e:
            logger.error(f"Failed to remove item from Skylight: {e}")
            raise