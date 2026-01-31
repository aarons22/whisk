"""
Meal Sync Engine for Whisk

Handles one-way synchronization from Paprika meal plans to Skylight calendar.
"""

import logging
from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .models import MealItem
from .paprika_client import PaprikaClient
from .skylight_client import SkylightClient
from .state_manager import StateManager
from .config import WhiskConfig

logger = logging.getLogger(__name__)


@dataclass
class MealSyncResult:
    """Result of a meal sync operation"""
    success: bool = False
    error: Optional[str] = None
    meals_created: List[str] = None
    meals_updated: List[str] = None
    meals_deleted: List[str] = None
    sync_duration: float = 0.0
    total_meals_processed: int = 0

    def __post_init__(self):
        if self.meals_created is None:
            self.meals_created = []
        if self.meals_updated is None:
            self.meals_updated = []
        if self.meals_deleted is None:
            self.meals_deleted = []

    def get_total_changes(self) -> int:
        """Get total number of changes made"""
        return len(self.meals_created) + len(self.meals_updated) + len(self.meals_deleted)


class MealSyncEngine:
    """One-way meal sync from Paprika to Skylight"""

    def __init__(self, paprika_client: PaprikaClient, skylight_client: SkylightClient,
                 config: WhiskConfig, state_manager: StateManager):
        """
        Initialize meal sync engine

        Args:
            paprika_client: Authenticated Paprika API client
            skylight_client: Authenticated Skylight API client
            config: Whisk configuration with meal sync options
            state_manager: Database state manager
        """
        self.paprika_client = paprika_client
        self.skylight_client = skylight_client
        self.config = config
        self.state_manager = state_manager

        logger.info("MealSyncEngine initialized")

    def sync_meals(self, dry_run: bool = False) -> MealSyncResult:
        """
        Main sync method - Paprika → Skylight only

        Args:
            dry_run: If True, simulate changes without applying them

        Returns:
            MealSyncResult with sync statistics
        """
        start_time = datetime.now()
        result = MealSyncResult()

        try:
            if not self.config.meal_sync_enabled:
                logger.info("Meal sync is disabled in configuration")
                result.success = True
                return result

            logger.info(f"Starting meal sync (dry_run={dry_run})")

            # Calculate date range (future meals only)
            today = date.today()
            end_date = today + timedelta(days=self.config.meal_sync_days_ahead)

            logger.debug(f"Syncing meals from {today} to {end_date}")

            # Fetch Paprika meals in date range
            logger.debug("Fetching meals from Paprika...")
            paprika_meals_data = self.paprika_client.get_meal_plans(today, end_date)
            paprika_meals = self._convert_paprika_meals(paprika_meals_data)

            # Filter meals by enabled meal types
            paprika_meals = self._filter_meals_by_type(paprika_meals)

            # Fetch existing Skylight meals in date range
            logger.debug("Fetching meals from Skylight...")
            skylight_meals_data = self.skylight_client.get_meal_sittings(today, end_date)
            skylight_meals = self._convert_skylight_meals(skylight_meals_data)

            result.total_meals_processed = len(paprika_meals)

            if not dry_run:
                # Compare with database state and apply changes
                logger.debug("Comparing with database state...")
                self._apply_meal_changes(paprika_meals, skylight_meals, result)
            else:
                # Dry run - show what would be done including meal combinations
                logger.info(f"Dry run: Would sync meals from Paprika")
                self._show_dry_run_preview(paprika_meals)

            result.success = True
            logger.info(f"✅ Meal sync completed: {result.get_total_changes()} changes, "
                       f"{result.total_meals_processed} meals processed")

        except Exception as e:
            logger.error(f"❌ Meal sync failed: {e}")
            result.error = str(e)
            result.success = False

        result.sync_duration = (datetime.now() - start_time).total_seconds()
        return result

    def _convert_paprika_meals(self, meals_data: List[Dict[str, Any]]) -> List[MealItem]:
        """Convert Paprika API meal data to MealItem objects"""
        meals = []

        for meal_data in meals_data:
            try:
                # Extract meal information
                name = meal_data.get("name", "")
                if not name:
                    # Try recipe name or summary
                    name = meal_data.get("recipe_name", meal_data.get("summary", "Unnamed Meal"))

                meal_type = meal_data.get("meal_type", "").lower()

                # Map Paprika meal types to our standard types
                meal_type_map = {
                    "breakfast": "breakfast",
                    "lunch": "lunch",
                    "dinner": "dinner",
                    "snack": "snack",
                    "dessert": "snack"  # Map dessert to snack
                }
                meal_type = meal_type_map.get(meal_type, "dinner")  # Default to dinner

                meal = MealItem(
                    name=name,
                    date=meal_data["parsed_date"],
                    meal_type=meal_type,
                    paprika_id=meal_data.get("uid"),
                    recipe_uid=meal_data.get("recipe_uid"),
                    notes=meal_data.get("notes"),
                    paprika_timestamp=meal_data.get("parsed_timestamp")
                )
                meals.append(meal)

            except Exception as e:
                logger.warning(f"Failed to convert Paprika meal data: {e}")
                continue

        logger.debug(f"Converted {len(meals)} Paprika meals")
        return meals

    def _convert_skylight_meals(self, meals_data: List[Dict[str, Any]]) -> List[MealItem]:
        """Convert Skylight API meal data to MealItem objects"""
        meals = []

        for meal_data in meals_data:
            try:
                meal = MealItem(
                    name=meal_data.get("name", ""),
                    date=meal_data["parsed_date"],
                    meal_type=meal_data.get("meal_type", "").lower(),
                    skylight_id=meal_data.get("id"),
                    skylight_timestamp=meal_data.get("parsed_timestamp")
                )
                meals.append(meal)

            except Exception as e:
                logger.warning(f"Failed to convert Skylight meal data: {e}")
                continue

        logger.debug(f"Converted {len(meals)} Skylight meals")
        return meals

    def _filter_meals_by_type(self, meals: List[MealItem]) -> List[MealItem]:
        """Filter meals based on enabled meal types in configuration"""
        enabled_types = []

        if self.config.sync_breakfast:
            enabled_types.append("breakfast")
        if self.config.sync_lunch:
            enabled_types.append("lunch")
        if self.config.sync_dinner:
            enabled_types.append("dinner")
        if self.config.sync_snacks:
            enabled_types.append("snack")

        filtered_meals = [meal for meal in meals if meal.meal_type in enabled_types]

        if len(filtered_meals) != len(meals):
            logger.debug(f"Filtered meals: {len(meals)} -> {len(filtered_meals)} "
                        f"(enabled types: {enabled_types})")

        return filtered_meals

    def _combine_paprika_meals(self, meals: List[MealItem]) -> MealItem:
        """
        Combine multiple meals of same type into single meal

        Args:
            meals: List of meals with same date and meal_type

        Returns:
            Single combined MealItem
        """
        if len(meals) == 1:
            return meals[0]

        # Sort by timestamp to get deterministic order
        sorted_meals = sorted(meals, key=lambda m: m.paprika_timestamp or datetime.min)

        # Use first meal as base
        primary = sorted_meals[0]

        # Combine names with + separator (user preference: no truncation)
        names = [meal.name for meal in sorted_meals]
        combined_name = " + ".join(names)

        # Combine notes if any
        notes_parts = []
        for meal in sorted_meals:
            if meal.notes:
                notes_parts.append(f"{meal.name}: {meal.notes}")
        combined_notes = " | ".join(notes_parts) if notes_parts else primary.notes

        # Use most recent timestamp
        latest_timestamp = max((m.paprika_timestamp for m in sorted_meals if m.paprika_timestamp),
                              default=primary.paprika_timestamp)

        logger.info(f"Combined {len(meals)} {primary.meal_type} meals for {primary.date}: {combined_name}")

        return MealItem(
            name=combined_name,
            date=primary.date,
            meal_type=primary.meal_type,
            paprika_id=primary.paprika_id,  # Keep primary ID
            recipe_uid=primary.recipe_uid,
            notes=combined_notes,
            paprika_timestamp=latest_timestamp,
            skylight_id=primary.skylight_id,
            skylight_timestamp=primary.skylight_timestamp
        )

    def _show_dry_run_preview(self, paprika_meals: List[MealItem]) -> None:
        """Show dry run preview including meal combinations"""
        # Group meals like we do in actual sync
        paprika_groups = {}
        for meal in paprika_meals:
            key = f"{meal.date}_{meal.meal_type}"
            if key not in paprika_groups:
                paprika_groups[key] = []
            paprika_groups[key].append(meal)

        total_groups = len(paprika_groups)
        total_meals = len(paprika_meals)

        if total_meals != total_groups:
            logger.info(f"Dry run: Would sync {total_meals} individual meals → {total_groups} Skylight entries")
        else:
            logger.info(f"Dry run: Would sync {total_meals} meals (no combinations needed)")

        for key, meals in sorted(paprika_groups.items()):
            if len(meals) == 1:
                meal = meals[0]
                logger.info(f"  - {meal.name} on {meal.date} ({meal.meal_type})")
            else:
                # Show combination preview
                names = [meal.name for meal in meals]
                combined_name = " + ".join(names)
                meal_date = meals[0].date
                meal_type = meals[0].meal_type
                logger.info(f"  - COMBINED: {combined_name} on {meal_date} ({meal_type}) [{len(meals)} meals]")

    def _apply_meal_changes(self, paprika_meals: List[MealItem],
                           skylight_meals: List[MealItem],
                           result: MealSyncResult) -> None:
        """
        Apply meal changes from Paprika to Skylight (one-way sync)
        Handles multiple meals per type by combining them.

        Args:
            paprika_meals: Current meals from Paprika
            skylight_meals: Current meals from Skylight
            result: Result object to update with changes
        """
        try:
            # Get existing meals from database
            today = date.today()
            end_date = today + timedelta(days=self.config.meal_sync_days_ahead)
            existing_meals = self.state_manager.get_meals(today, end_date)

            # Create lookup of existing Skylight meals by unique key (date + meal_type)
            skylight_lookup = {}
            for meal in skylight_meals:
                key = f"{meal.date}_{meal.meal_type}"
                skylight_lookup[key] = meal

            # Group Paprika meals by date + meal_type to handle multiple meals per type
            paprika_groups = {}
            for meal in paprika_meals:
                key = f"{meal.date}_{meal.meal_type}"
                if key not in paprika_groups:
                    paprika_groups[key] = []
                paprika_groups[key].append(meal)

            # Process each group (may contain multiple meals)
            processed_meals = []
            for key, meals in paprika_groups.items():
                if len(meals) == 1:
                    # Single meal - use existing logic
                    processed_meal = meals[0]
                else:
                    # Multiple meals - combine them
                    processed_meal = self._combine_paprika_meals(meals)

                processed_meals.append(processed_meal)

                # Check against existing Skylight meal
                existing_skylight = skylight_lookup.get(key)

                if existing_skylight:
                    # Check if update is needed
                    if existing_skylight.name != processed_meal.name:
                        self._update_skylight_meal(existing_skylight, processed_meal)
                        result.meals_updated.append(processed_meal.name)
                else:
                    # Create new meal in Skylight
                    self._create_skylight_meal(processed_meal)
                    result.meals_created.append(processed_meal.name)

                # Save processed meal state to database
                self.state_manager.save_meal(processed_meal)

            # Handle deleted meals (meals in Skylight but not in processed Paprika groups)
            paprika_lookup = {f"{meal.date}_{meal.meal_type}": meal for meal in processed_meals}

            for meal in skylight_meals:
                key = f"{meal.date}_{meal.meal_type}"
                if key not in paprika_lookup:
                    # This meal was deleted from Paprika, remove from Skylight
                    self._delete_skylight_meal(meal)
                    result.meals_deleted.append(meal.name)

                    # Mark as deleted in database
                    self.state_manager.mark_meal_deleted(skylight_id=meal.skylight_id)

        except Exception as e:
            logger.error(f"Failed to apply meal changes: {e}")
            raise

    def _create_skylight_meal(self, meal: MealItem) -> None:
        """Create a new meal in Skylight"""
        try:
            logger.debug(f"Creating meal in Skylight: {meal.name} on {meal.date} ({meal.meal_type})")

            skylight_id = self.skylight_client.create_meal_sitting(
                name=meal.name,
                date=meal.date,
                meal_type=meal.meal_type
            )

            # Update meal with Skylight ID
            meal.skylight_id = skylight_id

            logger.info(f"Created meal in Skylight: {meal.name}")

        except Exception as e:
            logger.error(f"Failed to create meal in Skylight: {e}")
            raise

    def _update_skylight_meal(self, skylight_meal: MealItem, paprika_meal: MealItem) -> None:
        """Update an existing meal in Skylight"""
        try:
            logger.debug(f"Updating meal in Skylight: {skylight_meal.skylight_id} -> {paprika_meal.name}")

            self.skylight_client.update_meal_sitting(
                sitting_id=skylight_meal.skylight_id,
                name=paprika_meal.name,
                date=paprika_meal.date,
                meal_type=paprika_meal.meal_type
            )

            logger.info(f"Updated meal in Skylight: {paprika_meal.name}")

        except Exception as e:
            logger.error(f"Failed to update meal in Skylight: {e}")
            raise

    def _delete_skylight_meal(self, meal: MealItem) -> None:
        """Delete a meal from Skylight"""
        try:
            logger.debug(f"Deleting meal from Skylight: {meal.skylight_id}")

            self.skylight_client.delete_meal_sitting(meal.skylight_id, meal.date)

            logger.info(f"Deleted meal from Skylight: {meal.name}")

        except Exception as e:
            logger.error(f"Failed to delete meal from Skylight: {e}")
            raise