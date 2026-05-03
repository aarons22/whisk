"""Skylight API client with OAuth2 Bearer token authentication"""

import json
import logging
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

from .models import ListItem

logger = logging.getLogger(__name__)


class SkylightClient:
    """Client for interacting with Skylight API using OAuth2 Bearer tokens"""

    BASE_URL = "https://app.ourskylight.com/api"
    AUTH_BASE = "https://app.ourskylight.com"
    OAUTH_URL = "https://app.ourskylight.com/oauth/token"
    CLIENT_ID = "skylight-mobile"
    REDIRECT_URI = "https://ourskylight.com/welcome"

    def __init__(self, email: str, password: str, frame_id: str, token_cache_file: str = "skylight_token"):
        self.email = email
        self.password = password
        self.frame_id = frame_id
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self.token_cache_file = Path(token_cache_file)
        self._session = requests.Session()
        self._user_data: Optional[Dict[str, Any]] = None
        self._frames_cache: Optional[List[Dict[str, Any]]] = None
        self._lists_cache: Optional[List[Dict[str, Any]]] = None

    def authenticate(self) -> None:
        """Authenticate with Skylight, using cached token or full OAuth login."""
        if self._load_cached_token():
            logger.debug("Using cached Skylight token")
            return
        logger.info("Authenticating with Skylight via OAuth...")
        self._do_login()
        logger.info("Skylight authenticated successfully")

    def _do_login(self) -> None:
        """Full 4-step OAuth Authorization Code flow."""
        login_session = requests.Session()

        # Step 1: fetch login page for CSRF token
        resp = login_session.get(
            f"{self.AUTH_BASE}/auth/session/new",
            headers={"User-Agent": "SkylightMobile (web)"},
            timeout=15,
        )
        resp.raise_for_status()
        match = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text)
        if not match:
            raise Exception("Could not extract CSRF token from Skylight login page")
        csrf_token = match.group(1)

        # Step 2: submit credentials (form-encoded)
        resp = login_session.post(
            f"{self.AUTH_BASE}/auth/session",
            data={
                "authenticity_token": csrf_token,
                "email": self.email,
                "password": self.password,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "SkylightMobile (web)",
                "Referer": f"{self.AUTH_BASE}/auth/session/new",
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            raise Exception(f"Skylight login failed ({resp.status_code}): check email and password")

        # Step 3: exchange session cookie for authorization code
        authorize_url = f"{self.AUTH_BASE}/oauth/authorize?" + urllib.parse.urlencode({
            "client_id": self.CLIENT_ID,
            "redirect_uri": self.REDIRECT_URI,
            "response_type": "code",
            "scope": "everything",
        })
        resp = login_session.get(
            authorize_url,
            headers={"User-Agent": "SkylightMobile (web)"},
            allow_redirects=False,
            timeout=15,
        )
        location = resp.headers.get("Location", "")
        parsed = urllib.parse.urlparse(location)
        code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
        if not code:
            raise Exception(f"No authorization code in OAuth redirect: {location!r}")

        # Step 4: exchange code for bearer + refresh tokens
        self._exchange_code(code)
        self._cache_token()

    def _exchange_code(self, code: str) -> None:
        """Exchange an authorization code for access + refresh tokens."""
        resp = requests.post(
            self.OAUTH_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": self.CLIENT_ID,
                "code": code,
                "redirect_uri": self.REDIRECT_URI,
                "scope": "everything",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "SkylightMobile (web)",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200)

    def _do_token_refresh(self) -> bool:
        """Refresh access token using the stored refresh token. Returns True on success."""
        if not self.refresh_token:
            return False
        try:
            resp = requests.post(
                self.OAUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.CLIENT_ID,
                    "refresh_token": self.refresh_token,
                    "scope": "everything",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "SkylightMobile (web)",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            self._token_expires_at = time.time() + data.get("expires_in", 7200)
            self._cache_token()
            logger.debug("Skylight token refreshed")
            return True
        except Exception as e:
            logger.warning(f"Skylight token refresh failed: {e}")
            return False

    def _cache_token(self) -> None:
        """Persist current tokens to cache file."""
        try:
            token_data = {
                "email": self.email,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self._token_expires_at,
            }
            with open(self.token_cache_file, "w") as f:
                json.dump(token_data, f)
            os.chmod(self.token_cache_file, 0o600)
            logger.debug(f"Cached Skylight token to {self.token_cache_file}")
        except Exception as e:
            logger.warning(f"Failed to cache Skylight token: {e}")

    def _load_cached_token(self) -> bool:
        """Load cached token. Refreshes automatically if expired. Returns True if usable."""
        try:
            if not self.token_cache_file.exists():
                return False
            with open(self.token_cache_file, "r") as f:
                data = json.load(f)
            if data.get("email") != self.email:
                logger.debug("Cached Skylight token is for a different email")
                return False
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            expires_at = float(data.get("expires_at", 0))
            if not access_token or not refresh_token:
                return False
            self.refresh_token = refresh_token
            # Refresh proactively if within 60s of expiry
            if time.time() >= expires_at - 60:
                logger.debug("Cached token near/past expiry, refreshing...")
                return self._do_token_refresh()
            self.access_token = access_token
            self._token_expires_at = expires_at
            logger.debug("Loaded cached Skylight token")
            return True
        except Exception as e:
            logger.debug(f"Failed to load cached Skylight token: {e}")
            return False

    def _ensure_authenticated(self) -> None:
        """Ensure a valid access token is present."""
        if self.access_token and time.time() < self._token_expires_at - 60:
            return
        if self.refresh_token and self._do_token_refresh():
            return
        self.authenticate()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the Skylight API."""
        self._ensure_authenticated()

        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "SkylightMobile (web)",
        }

        try:
            response = self._session.request(method, url, json=data, headers=headers)

            if response.status_code == 401:
                logger.warning("Skylight 401 — attempting token refresh...")
                if self._do_token_refresh():
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    response = self._session.request(method, url, json=data, headers=headers)
                else:
                    # Refresh failed — do full login and retry once
                    self.access_token = None
                    self.refresh_token = None
                    if self.token_cache_file.exists():
                        self.token_cache_file.unlink()
                    self._do_login()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    response = self._session.request(method, url, json=data, headers=headers)

            response.raise_for_status()

            if not response.text.strip():
                return {}
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

            self._ensure_authenticated()
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": "SkylightMobile (web)",
            }

            response = self._session.put(url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()
            actual_status = result.get("data", {}).get("attributes", {}).get("status")
            logger.info(f"Updated item in Skylight: {skylight_id} (new status: {actual_status})")

        except Exception as e:
            logger.error(f"Failed to update item in Skylight: {e}")
            raise

    def bulk_delete_items(self, skylight_ids: List[str], list_name: str) -> None:
        """
        Remove multiple items from list using bulk destroy endpoint

        Args:
            skylight_ids: List of Skylight IDs of items to remove
            list_name: Name of the list to remove items from (REQUIRED for security)
        """
        try:
            if not skylight_ids:
                logger.debug("No items to delete")
                return

            logger.debug(f"Bulk removing {len(skylight_ids)} items from Skylight list '{list_name}': {skylight_ids}")

            if not list_name:
                raise ValueError("list_name is required - will not search all lists for security")

            # Get the list ID
            list_id = self.get_list_id_by_name(list_name)
            if not list_id:
                raise Exception(f"List '{list_name}' not found")

            # Verify all items exist in this specific list (optional validation)
            existing_items = self.get_list_items(list_name)
            existing_ids = {item.skylight_id for item in existing_items}

            # Filter out items that don't exist (log warning but don't fail)
            valid_ids = []
            for skylight_id in skylight_ids:
                if skylight_id in existing_ids:
                    valid_ids.append(skylight_id)
                else:
                    logger.warning(f"Item {skylight_id} not found in list '{list_name}' - skipping")

            if not valid_ids:
                logger.info("No valid items to delete after validation")
                return

            # Use bulk destroy endpoint - the only working deletion method
            endpoint = f"/frames/{self.frame_id}/lists/{list_id}/list_items/bulk_destroy"
            payload = {"ids": valid_ids}

            self._make_request("DELETE", endpoint, payload)
            logger.info(f"Bulk removed {len(valid_ids)} items from Skylight list '{list_name}': {valid_ids}")

        except Exception as e:
            logger.error(f"Failed to bulk remove items from Skylight: {e}")
            raise

    def remove_item(self, skylight_id: str, list_name: str = None) -> None:
        """
        Remove single item from list (wrapper around bulk delete)

        Args:
            skylight_id: Skylight ID of the item to remove
            list_name: Name of the list to search in (REQUIRED for security)
        """
        try:
            logger.debug(f"Removing single item from Skylight: {skylight_id}")

            # Use bulk delete for single item (since individual delete doesn't work)
            self.bulk_delete_items([skylight_id], list_name)

        except Exception as e:
            logger.error(f"Failed to remove item from Skylight: {e}")
            raise

    def get_meal_recipes(self) -> List[Dict[str, Any]]:
        """
        Get meal recipes from Skylight frame.

        Returns:
            List of meal recipe dictionaries
        """
        try:
            endpoint = f"/frames/{self.frame_id}/meals/recipes?include=meal_category"
            result = self._make_request("GET", endpoint)
            if result is None:
                return []

            data = result.get("data", []) if isinstance(result, dict) else []
            included = result.get("included", []) if isinstance(result, dict) else []
            meal_categories = {item["id"]: item for item in included if item.get("type") == "meal_category"}
            recipes: List[Dict[str, Any]] = []

            for item in data:
                if item.get("type") != "meal_recipe":
                    continue

                attrs = item.get("attributes", {})
                rel = item.get("relationships", {})
                category_data = rel.get("meal_category", {}).get("data")
                category_id = category_data.get("id") if isinstance(category_data, dict) else None
                category_label = None
                if category_id and category_id in meal_categories:
                    category_label = meal_categories[category_id].get("attributes", {}).get("label")

                recipes.append({
                    "id": item.get("id"),
                    "summary": attrs.get("summary") or "",
                    "description": attrs.get("description") or "",
                    "meal_category_id": category_id,
                    "meal_category": category_label,
                })

            logger.info(f"Retrieved {len(recipes)} meal recipes from Skylight")
            return recipes

        except Exception as e:
            logger.error(f"Failed to get meal recipes from Skylight: {e}")
            raise

    def create_meal_recipe(self, summary: str, description: str, meal_type: str) -> str:
        """
        Create a meal recipe in Skylight.

        Args:
            summary: Recipe title
            description: Recipe body text
            meal_type: Meal category type

        Returns:
            Skylight meal recipe ID
        """
        try:
            meal_category_id = self._get_meal_category_id(meal_type)
            if not meal_category_id:
                raise Exception(f"Could not find meal category for type: {meal_type}")

            payload = {
                "summary": summary,
                "description": description,
                "meal_category_id": meal_category_id
            }

            endpoint = f"/frames/{self.frame_id}/meals/recipes?include=meal_category"
            result = self._make_request("POST", endpoint, payload)
            recipe_id = self._extract_jsonapi_id(result)
            if not recipe_id:
                raise Exception("No recipe ID returned from create meal recipe request")

            logger.info(f"Created Skylight meal recipe: {summary} (id={recipe_id})")
            return recipe_id

        except Exception as e:
            logger.error(f"Failed to create meal recipe in Skylight: {e}")
            raise

    def update_meal_recipe(self, recipe_id: str, summary: str, description: str, meal_type: str) -> None:
        """
        Update an existing meal recipe in Skylight.

        Args:
            recipe_id: Skylight meal recipe ID
            summary: Recipe title
            description: Recipe body text
            meal_type: Meal category type
        """
        try:
            meal_category_id = self._get_meal_category_id(meal_type)
            if not meal_category_id:
                raise Exception(f"Could not find meal category for type: {meal_type}")

            payload = {
                "summary": summary,
                "description": description,
                "meal_category_id": meal_category_id
            }

            endpoint = f"/frames/{self.frame_id}/meals/recipes/{recipe_id}?include=meal_category"
            # Docs indicate PUT; PATCH is used elsewhere in this codebase and should also work.
            try:
                self._make_request("PUT", endpoint, payload)
            except Exception:
                self._make_request("PATCH", endpoint, payload)

            logger.info(f"Updated Skylight meal recipe: {recipe_id}")

        except Exception as e:
            logger.error(f"Failed to update meal recipe in Skylight: {e}")
            raise

    def get_meal_sittings(self, start_date, end_date):
        """
        Get meal sittings for a date range from Skylight calendar

        Args:
            start_date: datetime.date object for start of range
            end_date: datetime.date object for end of range

        Returns:
            List of meal sitting dictionaries
        """
        try:
            logger.debug(f"Fetching meal sittings from Skylight: {start_date} to {end_date}")

            # Use the correct meal sittings endpoint with date range parameters
            params_str = f"?date_min={start_date.isoformat()}&date_max={end_date.isoformat()}&include=meal_category%2Cmeal_recipe"
            endpoint = f"/frames/{self.frame_id}/meals/sittings{params_str}"

            result = self._make_request("GET", endpoint)

            # Handle case where result might be None
            if result is None:
                logger.warning("Meal sittings API returned None response")
                return []

            # Handle JSON:API format response
            data = result.get("data", [])
            included = result.get("included", [])
            meals = []

            # Create lookup for included data
            meal_categories = {item["id"]: item for item in included if item["type"] == "meal_category"}
            meal_recipes = {item["id"]: item for item in included if item["type"] == "meal_recipe"}

            for item in data:
                if item.get("type") == "meal_sitting":
                    attributes = item.get("attributes", {})
                    relationships = item.get("relationships", {})

                    # Get meal category info
                    meal_category_rel = relationships.get("meal_category", {})
                    meal_category_data = meal_category_rel.get("data") if meal_category_rel else None
                    meal_category_id = None
                    if meal_category_data:
                        if isinstance(meal_category_data, dict):
                            meal_category_id = meal_category_data.get("id")
                        elif isinstance(meal_category_data, list) and meal_category_data:
                            # Handle case where data is a list
                            meal_category_id = meal_category_data[0].get("id") if isinstance(meal_category_data[0], dict) else None
                        else:
                            logger.warning(f"Unexpected meal_category_data type: {type(meal_category_data)}")

                    meal_category_label = None
                    if meal_category_id and meal_category_id in meal_categories:
                        meal_category_label = meal_categories[meal_category_id]["attributes"]["label"]

                    # Get meal recipe info
                    meal_recipe_rel = relationships.get("meal_recipe", {})
                    meal_recipe_data = meal_recipe_rel.get("data") if meal_recipe_rel else None
                    meal_recipe_id = None
                    if meal_recipe_data:
                        if isinstance(meal_recipe_data, dict):
                            meal_recipe_id = meal_recipe_data.get("id")
                        elif isinstance(meal_recipe_data, list) and meal_recipe_data:
                            # Handle case where data is a list
                            meal_recipe_id = meal_recipe_data[0].get("id") if isinstance(meal_recipe_data[0], dict) else None
                        else:
                            logger.warning(f"Unexpected meal_recipe_data type: {type(meal_recipe_data)}")

                    meal_recipe_summary = None
                    if meal_recipe_id and meal_recipe_id in meal_recipes:
                        meal_recipe_summary = meal_recipes[meal_recipe_id]["attributes"]["summary"]

                    # Extract date from instances
                    instances = attributes.get("instances", [])
                    meal_date = instances[0] if instances else None

                    # Parse date
                    parsed_date = None
                    if meal_date:
                        try:
                            parsed_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
                        except ValueError as e:
                            logger.warning(f"Failed to parse meal date '{meal_date}': {e}")

                    meal_data = {
                        "id": item.get("id"),
                        "name": meal_recipe_summary or attributes.get("summary", ""),
                        "date": meal_date,
                        "meal_category": meal_category_label,
                        "meal_type": meal_category_label.lower() if meal_category_label else "",
                        "meal_recipe_id": meal_recipe_id,
                        "description": attributes.get("description"),
                        "note": attributes.get("note"),
                        "parsed_date": parsed_date,
                        "attributes": attributes,
                        "relationships": relationships
                    }
                    meals.append(meal_data)

            logger.info(f"Retrieved {len(meals)} meal sittings from Skylight")
            return meals

        except Exception as e:
            logger.error(f"Failed to get meal sittings from Skylight: {e}")
            raise

    def create_meal_sitting(
        self,
        name: str,
        date,
        meal_type: str,
        meal_recipe_id: Optional[str] = None,
        note: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """
        Create a meal sitting in Skylight calendar

        Args:
            name: Meal name
            date: datetime.date object for the meal date
            meal_type: Meal category (breakfast, lunch, dinner, snack)

        Returns:
            Skylight ID of created meal sitting
        """
        try:
            logger.debug(f"Creating meal sitting in Skylight: {name} on {date} ({meal_type})")

            # Get correct meal category ID from API
            meal_category_id = self._get_meal_category_id(meal_type)
            if not meal_category_id:
                raise Exception(f"Could not find meal category for type: {meal_type}")

            # Use the payload format discovered from browser inspection
            sitting_data = {
                "meal_recipe_id": meal_recipe_id,
                "meal_category_id": meal_category_id,
                "add_to_grocery_list": False,
                "date": date.isoformat(),
                "note": note,
                "rrule": None,
                "description": description,
                "saveToRecipeBox": False
            }
            # Skylight requires summary to be blank when meal_recipe_id is set.
            if meal_recipe_id:
                sitting_data["summary"] = None
            else:
                sitting_data["summary"] = name

            # Use the correct endpoint with date range parameters (as seen in browser)
            params_str = f"?date_min={date.isoformat()}&date_max={date.isoformat()}&include=meal_category%2Cmeal_recipe"
            endpoint = f"/frames/{self.frame_id}/meals/sittings{params_str}"

            result = self._make_request("POST", endpoint, sitting_data)

            # Log the response to understand the format
            logger.debug(f"Meal creation response: {result} (type: {type(result)})")

            # Extract created meal ID from response
            meal_id = self._extract_jsonapi_id(result)
            if meal_id:
                logger.info(f"Created meal sitting in Skylight: {name} (id={meal_id})")
                return meal_id

            # Log the full response to understand the format
            logger.warning(f"Unexpected response format from meal creation: {result}")

            raise Exception("No meal ID returned from create request")

        except Exception as e:
            logger.error(f"Failed to create meal sitting in Skylight: {e}")
            raise

    def _get_meal_category_id(self, meal_type: str):
        """Get meal category ID for the given meal type using dedicated categories API"""
        try:
            # Use the dedicated meal categories endpoint
            result = self._make_request("GET", f"/frames/{self.frame_id}/meals/categories")

            logger.debug(f"Categories API response: {result} (type: {type(result)})")

            # Handle both dict and list response formats
            categories_data = []
            if isinstance(result, dict):
                categories_data = result.get("data", [])
            elif isinstance(result, list):
                categories_data = result
            else:
                logger.error(f"Unexpected categories response type: {type(result)}")
                return None

            # Extract meal categories from response data
            meal_categories = {}
            for item in categories_data:
                # Debug: Check what type each item is
                logger.debug(f"Processing categories item: {item} (type: {type(item)})")

                # Ensure item is a dictionary before calling .get()
                if not isinstance(item, dict):
                    logger.warning(f"Expected dict but got {type(item)} for categories item: {item}")
                    continue

                if item.get("type") == "meal_category":
                    try:
                        label = item["attributes"]["label"].lower()
                        meal_categories[label] = item["id"]
                    except KeyError as e:
                        logger.warning(f"Missing required field in meal category item: {e}")
                        continue

            logger.debug(f"Available meal categories: {meal_categories}")

            # If no categories found, return None to trigger error
            if not meal_categories:
                logger.error("No meal categories found in Skylight frame")
                return None

            # Map meal type to category
            meal_type_lower = meal_type.lower()
            if meal_type_lower in meal_categories:
                logger.debug(f"Found exact match for meal type '{meal_type}': {meal_categories[meal_type_lower]}")
                return meal_categories[meal_type_lower]

            # Try some common mappings
            type_mapping = {
                "snack": "snacks",  # Sometimes it's plural
            }

            mapped_type = type_mapping.get(meal_type_lower, meal_type_lower)
            if mapped_type in meal_categories:
                logger.warning(f"Meal type '{meal_type}' not found, using '{mapped_type}' category")
                return meal_categories[mapped_type]

            # Use any available category as last resort
            default_id = list(meal_categories.values())[0]
            default_label = list(meal_categories.keys())[0]
            logger.warning(f"Meal type '{meal_type}' not found, using available category '{default_label}' (ID: {default_id})")
            return default_id

        except Exception as e:
            logger.error(f"Failed to get meal category ID: {e}")
            return None

    def update_meal_sitting(
        self,
        sitting_id: str,
        name: str,
        date,
        meal_type: str,
        meal_recipe_id: Optional[str] = None,
        note: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """
        Update a meal sitting in Skylight calendar

        Args:
            sitting_id: Skylight ID of the meal sitting
            name: New meal name
            date: datetime.date object for the meal date
            meal_type: Meal category (breakfast, lunch, dinner, snack)
        """
        try:
            logger.debug(f"Updating meal sitting in Skylight: {sitting_id}")

            meal_category_id = self._get_meal_category_id(meal_type)
            if not meal_category_id:
                raise Exception(f"Could not find meal category for type: {meal_type}")

            # Use the same payload format as creation (discovered from browser)
            sitting_data = {
                "meal_recipe_id": meal_recipe_id,
                "meal_category_id": meal_category_id,
                "add_to_grocery_list": False,
                "date": date.isoformat(),
                "note": note,
                "rrule": None,
                "description": description,
                "saveToRecipeBox": False
            }
            # Skylight requires summary to be blank when meal_recipe_id is set.
            if meal_recipe_id:
                sitting_data["summary"] = None
            else:
                sitting_data["summary"] = name

            # Try instance-based update first (similar to delete endpoint)
            try:
                date_params = f"?date_min={date.isoformat()}&date_max={date.isoformat()}&include=meal_category%2Cmeal_recipe"
                endpoint = f"/frames/{self.frame_id}/meals/sittings/{sitting_id}/instances/{date.isoformat()}{date_params}"
                result = self._make_request("PATCH", endpoint, sitting_data)
                logger.info(f"Updated meal sitting instance in Skylight: {sitting_id}")
                return
            except Exception as e:
                logger.warning(f"Instance-based update failed: {e}, trying direct update")

            # Fallback to simple endpoint for updates
            endpoint = f"/frames/{self.frame_id}/meals/sittings/{sitting_id}"
            result = self._make_request("PATCH", endpoint, sitting_data)
            logger.info(f"Updated meal sitting in Skylight: {sitting_id}")

        except Exception as e:
            logger.error(f"Failed to update meal sitting in Skylight: {e}")
            raise

    def _extract_jsonapi_id(self, result: Any) -> Optional[str]:
        """Extract first resource ID from common JSON:API response shapes."""
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                resource_id = data.get("id")
                return str(resource_id) if resource_id else None
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and first.get("id"):
                    return str(first["id"])
            if result.get("id"):
                return str(result["id"])
        elif isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and first.get("id"):
                return str(first["id"])
        return None

    def delete_meal_sitting(self, sitting_id: str, date=None):
        """
        Delete a meal sitting from Skylight calendar

        Args:
            sitting_id: Skylight ID of the meal sitting to delete
            date: Optional date of the meal sitting (for specific instance deletion)
        """
        try:
            logger.debug(f"Deleting meal sitting from Skylight: {sitting_id}")

            if date:
                # Delete specific instance (date-specific meal) - using discovered format
                date_params = f"?date_min={date.isoformat()}&date_max={date.isoformat()}&include=meal_category%2Cmeal_recipe"
                endpoint = f"/frames/{self.frame_id}/meals/sittings/{sitting_id}/instances/{date.isoformat()}{date_params}"
            else:
                # Delete entire meal sitting
                endpoint = f"/frames/{self.frame_id}/meals/sittings/{sitting_id}"

            self._make_request("DELETE", endpoint)
            logger.info(f"Deleted meal sitting from Skylight: {sitting_id}")

        except Exception as e:
            logger.error(f"Failed to delete meal sitting from Skylight: {e}")
            raise
