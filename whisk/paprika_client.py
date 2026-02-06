"""Paprika API client using reverse-engineered REST API"""

import gzip
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

from .models import ListItem

logger = logging.getLogger(__name__)


class PaprikaClient:
    """Client for interacting with Paprika grocery lists and recipes via reverse-engineered API"""

    BASE_URL = "https://www.paprikaapp.com/api"

    def __init__(self, email: str, password: str, token_cache_file: str = "paprika_token"):
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

    def get_grocery_list(self, list_name: str) -> List[ListItem]:
        """
        Get all items from a specific list

        Args:
            list_name: Name of the list to filter by

        Returns:
            List of ListItem objects from the specified list
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
                        logger.warning(f"Failed to parse timestamp for {grocery.get('name')}: {e}")

                item = ListItem(
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

    def add_item(self, name: str, list_name: str, checked: bool = False) -> str:
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

    def update_item(
        self, paprika_id: str, checked: bool, list_name: str, name: Optional[str] = None
    ) -> None:
        """
        Update item (checked status or name)

        Args:
            paprika_id: Paprika UID of the item
            checked: New checked status
            list_name: Name of the grocery list containing the item
            name: Optional new name for the item
        """
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

    def get_meal_plans(self, start_date, end_date):
        """
        Get meal plans for a date range from Paprika

        Args:
            start_date: datetime.date object for start of range
            end_date: datetime.date object for end of range

        Returns:
            List of meal plan dictionaries
        """
        try:
            logger.debug(f"Fetching meal plans from Paprika: {start_date} to {end_date}")

            # Try the most likely endpoint based on existing patterns
            result = self._make_request("GET", "/v2/sync/meals/")
            meals = result.get("result", [])

            # Filter meals by date range
            filtered_meals = []
            for meal in meals:
                meal_date_str = meal.get("date")
                if meal_date_str:
                    try:
                        # Parse date string - handle both YYYY-MM-DD and YYYY-MM-DD HH:MM:SS formats
                        date_str = meal_date_str.split(" ")[0]  # Take only the date part
                        meal_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                        # Check if meal is within date range
                        if start_date <= meal_date <= end_date:
                            # Parse timestamp if available
                            timestamp = None
                            updated_at = meal.get("updated_at") or meal.get("created_at")
                            if updated_at:
                                try:
                                    timestamp_str = updated_at.replace("Z", "+00:00")
                                    timestamp = datetime.fromisoformat(timestamp_str)
                                except Exception as e:
                                    logger.warning(f"Failed to parse meal timestamp: {e}")

                            # Map numeric type to meal type string
                            # Based on Paprika API: 0=breakfast, 1=lunch, 2=dinner, 3=snack
                            type_to_meal_type = {
                                0: "breakfast",
                                1: "lunch",
                                2: "dinner",
                                3: "snack",
                            }
                            numeric_type = meal.get("type", 2)  # Default to dinner (type 2)
                            meal_type = type_to_meal_type.get(numeric_type, "dinner")

                            # Add parsed fields to meal data
                            meal_copy = meal.copy()
                            meal_copy["parsed_timestamp"] = timestamp
                            meal_copy["parsed_date"] = meal_date
                            meal_copy["meal_type"] = meal_type  # Add the meal type field
                            filtered_meals.append(meal_copy)

                    except ValueError as e:
                        logger.warning(f"Failed to parse meal date '{meal_date_str}': {e}")

            logger.info(f"Retrieved {len(filtered_meals)} meal plans from Paprika")
            return filtered_meals

        except Exception as e:
            logger.error(f"Failed to get meal plans from Paprika: {e}")
            raise

    def list_recipes(self) -> List[Dict[str, str]]:
        """
        Get lightweight list of all recipes (only UIDs and hashes)

        This is the efficient way to check for recipe changes without downloading
        full recipe data. Compare hashes against cached values to detect changes.

        Returns:
            List of dictionaries with 'uid' and 'hash' keys
            Example: [{"uid": "ABC-123", "hash": "a1b2c3..."}]
        """
        try:
            logger.debug("Fetching recipe list from Paprika...")
            result = self._make_request("GET", "/v2/sync/recipes/")
            recipes = result.get("result", [])
            logger.info(f"Retrieved {len(recipes)} recipes from Paprika")
            return recipes

        except Exception as e:
            logger.error(f"Failed to get recipe list from Paprika: {e}")
            raise

    def get_recipe(self, uid: str) -> Dict[str, Any]:
        """
        Get full recipe details by UID

        Args:
            uid: Recipe unique identifier

        Returns:
            Dictionary containing full recipe data with all fields
        """
        try:
            logger.debug(f"Fetching recipe {uid} from Paprika...")
            result = self._make_request("GET", f"/v2/sync/recipe/{uid}/")
            recipe = result.get("result", {})

            if not recipe:
                raise Exception(f"Recipe {uid} not found")

            logger.info(f"Retrieved recipe: {recipe.get('name', uid)}")
            return recipe

        except Exception as e:
            logger.error(f"Failed to get recipe {uid} from Paprika: {e}")
            raise

    def _generate_recipe_hash(self) -> str:
        """
        Generate a 64-character hexadecimal hash for a recipe

        The API accepts any 64-char hex string. This uses a UUID as the base.

        Returns:
            64-character hex string
        """
        # Generate a unique hash based on UUID and current timestamp
        unique_str = f"{uuid.uuid4()}{datetime.now(timezone.utc).isoformat()}"
        return hashlib.sha256(unique_str.encode()).hexdigest()

    def _create_default_recipe(self, uid: str, name: str) -> Dict[str, Any]:
        """
        Create a recipe object with all required fields and defaults

        Args:
            uid: Recipe unique identifier (UUID4 uppercase)
            name: Recipe name/title

        Returns:
            Dictionary with all recipe fields initialized to defaults
        """
        return {
            "uid": uid,
            "name": name,
            "ingredients": "",
            "directions": "",
            "description": "",
            "notes": "",
            "nutritional_info": "",
            "servings": "",
            "difficulty": "",
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "rating": 0,
            "categories": [],
            "source": "",
            "source_url": "",
            "image_url": "",
            "photo": "",
            "photo_hash": "",
            "photo_large": None,
            "photo_url": None,
            "hash": "",  # Hash will be generated by create_recipe/update_recipe
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "on_favorites": False,
            "on_grocery_list": None,
            "in_trash": False,
            "is_pinned": False,
            "scale": None,
        }

    def create_recipe(self, recipe_data: Dict[str, Any]) -> str:
        """
        Create a new recipe

        Args:
            recipe_data: Dictionary with recipe fields. Must include at least 'name'.
                        Other fields are optional and will use defaults if not provided.
                        If 'uid' is not provided, one will be generated.

        Returns:
            Recipe UID

        Example:
            recipe = {
                "name": "Chocolate Chip Cookies",
                "ingredients": "2 cups flour\\n1 cup sugar\\n1 cup chocolate chips",
                "directions": "1. Mix ingredients\\n2. Bake at 350F for 12 minutes",
                "prep_time": "15 min",
                "cook_time": "12 min",
                "categories": ["Desserts", "Cookies"]
            }
            uid = client.create_recipe(recipe)
        """
        try:
            # Generate UID if not provided
            uid = recipe_data.get("uid", str(uuid.uuid4()).upper())

            # Get recipe name (required)
            name = recipe_data.get("name")
            if not name:
                raise ValueError("Recipe name is required")

            logger.debug(f"Creating recipe in Paprika: {name}")

            # Start with defaults, then update with provided data
            recipe = self._create_default_recipe(uid, name)
            recipe.update(recipe_data)
            recipe["uid"] = uid  # Ensure UID is set

            # Ensure hash is generated if not provided
            if not recipe.get("hash"):
                recipe["hash"] = self._generate_recipe_hash()

            # Send as gzipped form data (individual endpoint, not bulk)
            result = self._make_request(
                "POST", f"/v2/sync/recipe/{uid}/", data=recipe, gzip_form_data=True
            )
            logger.debug(f"Create response: {result}")

            # Check for success
            if result.get("error"):
                error_msg = result.get("error", {}).get("message", "Unknown error")
                raise Exception(f"API error: {error_msg}")

            if not result.get("result"):
                raise Exception("Create operation did not return success")

            logger.info(f"Created recipe in Paprika: {name} (uid={uid})")
            return uid

        except Exception as e:
            logger.error(f"Failed to create recipe in Paprika: {e}")
            raise

    def update_recipe(self, uid: str, recipe_data: Dict[str, Any]) -> None:
        """
        Update an existing recipe

        Args:
            uid: Recipe unique identifier
            recipe_data: Dictionary with recipe fields. Must include ALL fields
                        (partial updates not supported). Use get_recipe() first to
                        get current data, then modify and update.
                        Note: The 'uid' and 'hash' fields are automatically managed
                        and don't need to be included in recipe_data.

        Example:
            # Get current recipe
            recipe = client.get_recipe("ABC-123")
            # Modify fields
            recipe["name"] = "Updated Recipe Name"
            recipe["rating"] = 5
            # Save changes (uid and hash automatically set)
            client.update_recipe("ABC-123", recipe)
        """
        try:
            logger.debug(f"Updating recipe in Paprika: {uid}")

            # Ensure UID matches
            recipe_data["uid"] = uid

            # Update hash to indicate changes
            recipe_data["hash"] = self._generate_recipe_hash()

            # Send as gzipped form data
            result = self._make_request(
                "POST", f"/v2/sync/recipe/{uid}/", data=recipe_data, gzip_form_data=True
            )

            if not result.get("result"):
                raise Exception("Update operation did not return success")

            logger.info(f"Updated recipe in Paprika: {recipe_data.get('name', uid)}")

        except Exception as e:
            logger.error(f"Failed to update recipe in Paprika: {e}")
            raise

    def delete_recipe(self, uid: str) -> None:
        """
        Delete a recipe (soft delete - sets in_trash=True)

        Note: Paprika doesn't support true deletion. This marks the recipe as
        deleted by setting in_trash=True.

        Args:
            uid: Recipe unique identifier
        """
        try:
            logger.debug(f"Deleting recipe from Paprika: {uid}")

            # Get current recipe data
            recipe = self.get_recipe(uid)

            # Mark as deleted
            recipe["in_trash"] = True
            recipe["hash"] = self._generate_recipe_hash()

            # Update the recipe
            result = self._make_request(
                "POST", f"/v2/sync/recipe/{uid}/", data=recipe, gzip_form_data=True
            )

            if not result.get("result"):
                raise Exception("Delete operation did not return success")

            logger.info(f"Deleted recipe from Paprika: {recipe.get('name', uid)}")

        except Exception as e:
            logger.error(f"Failed to delete recipe from Paprika: {e}")
            raise
