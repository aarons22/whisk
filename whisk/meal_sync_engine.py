"""
Meal Sync Engine for Whisk

Handles one-way synchronization from Paprika meal plans to Skylight calendar.
Paprika is the authoritative source for all meal and recipe data.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .config import WhiskConfig
from .models import MealItem
from .paprika_client import PaprikaClient
from .skylight_client import SkylightClient
from .state_manager import StateManager

logger = logging.getLogger(__name__)


@dataclass
class MealSyncResult:
    """Result of a meal sync operation."""

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
        """Get total number of changes made."""
        return len(self.meals_created) + len(self.meals_updated) + len(self.meals_deleted)


class MealSyncEngine:
    """One-way meal sync from Paprika to Skylight."""

    def __init__(
        self,
        paprika_client: PaprikaClient,
        skylight_client: SkylightClient,
        config: WhiskConfig,
        state_manager: StateManager,
    ):
        self.paprika_client = paprika_client
        self.skylight_client = skylight_client
        self.config = config
        self.state_manager = state_manager
        logger.info("MealSyncEngine initialized")

    def sync_meals(self, dry_run: bool = False) -> MealSyncResult:
        """
        Main sync method - Paprika -> Skylight only.

        Args:
            dry_run: If True, simulate changes without applying them
        """
        start_time = datetime.now()
        result = MealSyncResult()

        try:
            if not self.config.meal_sync_enabled:
                logger.info("Meal sync is disabled in configuration")
                result.success = True
                return result

            today = date.today()
            end_date = today + timedelta(days=self.config.meal_sync_days_ahead)
            logger.info(f"Starting meal sync (dry_run={dry_run}) for {today}..{end_date}")

            paprika_meals_data = self.paprika_client.get_meal_plans(today, end_date)
            paprika_meals = self._filter_meals_by_type(self._convert_paprika_meals(paprika_meals_data))

            skylight_meals_data = self.skylight_client.get_meal_sittings(today, end_date)
            skylight_meals = self._convert_skylight_meals(skylight_meals_data)

            result.total_meals_processed = len(paprika_meals)

            if dry_run:
                self._show_dry_run_preview(paprika_meals)
            else:
                self._sync_recipes_for_meals(paprika_meals)
                self._apply_meal_changes(paprika_meals, skylight_meals, today, end_date, result)

            result.success = True
            logger.info(
                f"Meal sync completed: {result.get_total_changes()} changes, "
                f"{result.total_meals_processed} meals processed"
            )

        except Exception as e:
            logger.error(f"Meal sync failed: {e}")
            result.error = str(e)
            result.success = False

        result.sync_duration = (datetime.now() - start_time).total_seconds()
        return result

    def _convert_paprika_meals(self, meals_data: List[Dict[str, Any]]) -> List[MealItem]:
        """Convert Paprika API meal data to MealItem objects."""
        meals: List[MealItem] = []
        meal_type_map = {
            "breakfast": "breakfast",
            "lunch": "lunch",
            "dinner": "dinner",
            "snack": "snack",
            "dessert": "snack",
        }

        for meal_data in meals_data:
            try:
                paprika_id = meal_data.get("uid")
                if not paprika_id:
                    continue

                name = meal_data.get("name") or meal_data.get("recipe_name") or meal_data.get("summary") or "Unnamed Meal"
                meal_type = meal_type_map.get(str(meal_data.get("meal_type", "")).lower(), "dinner")

                meals.append(
                    MealItem(
                        name=name,
                        date=meal_data["parsed_date"],
                        meal_type=meal_type,
                        paprika_id=paprika_id,
                        recipe_uid=meal_data.get("recipe_uid"),
                        notes=meal_data.get("notes"),
                        paprika_timestamp=meal_data.get("parsed_timestamp"),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to convert Paprika meal data: {e}")

        logger.debug(f"Converted {len(meals)} Paprika meals")
        return meals

    def _convert_skylight_meals(self, meals_data: List[Dict[str, Any]]) -> List[MealItem]:
        """Convert Skylight API meal data to MealItem objects."""
        meals: List[MealItem] = []
        for meal_data in meals_data:
            try:
                parsed_date = meal_data.get("parsed_date")
                if not parsed_date:
                    continue

                meals.append(
                    MealItem(
                        name=meal_data.get("name", ""),
                        date=parsed_date,
                        meal_type=meal_data.get("meal_type", "").lower(),
                        skylight_id=meal_data.get("id"),
                        skylight_recipe_id=meal_data.get("meal_recipe_id"),
                        skylight_timestamp=meal_data.get("parsed_timestamp"),
                        notes=meal_data.get("note"),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to convert Skylight meal data: {e}")

        logger.debug(f"Converted {len(meals)} Skylight meals")
        return meals

    def _filter_meals_by_type(self, meals: List[MealItem]) -> List[MealItem]:
        """Filter meals based on enabled meal types in configuration."""
        enabled_types: List[str] = []
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
            logger.debug(f"Filtered meals {len(meals)} -> {len(filtered_meals)} (enabled={enabled_types})")
        return filtered_meals

    def _show_dry_run_preview(self, paprika_meals: List[MealItem]) -> None:
        """Show dry-run preview. One Paprika meal maps to one Skylight sitting."""
        logger.info(f"Dry run: Would sync {len(paprika_meals)} Paprika meal entries to Skylight meal sittings")
        for meal in sorted(paprika_meals, key=lambda m: (m.date, m.meal_type, m.name)):
            recipe_info = f" recipe_uid={meal.recipe_uid}" if meal.recipe_uid else " text-only"
            logger.info(f"  - {meal.date} {meal.meal_type}: {meal.name} ({recipe_info})")

    def _sync_recipes_for_meals(self, meals: List[MealItem]) -> None:
        """Ensure each Paprika recipe meal has a corresponding up-to-date Skylight meal recipe."""
        recipe_uids = {meal.recipe_uid for meal in meals if meal.recipe_uid}
        if not recipe_uids:
            return

        recipe_index = {row["uid"]: row.get("hash") for row in self.paprika_client.get_recipe_index() if row.get("uid")}
        recipe_links = self.state_manager.get_all_recipe_links()

        for meal in meals:
            if not meal.recipe_uid:
                meal.skylight_recipe_id = None
                meal.paprika_recipe_hash = None
                continue

            recipe_uid = meal.recipe_uid
            paprika_hash = recipe_index.get(recipe_uid)
            link = recipe_links.get(recipe_uid)
            needs_refresh = link is None or link.paprika_hash != paprika_hash

            if needs_refresh:
                recipe = self.paprika_client.get_recipe_details(recipe_uid)
                summary, description = self._format_recipe_for_skylight(recipe)

                if link:
                    self.skylight_client.update_meal_recipe(
                        recipe_id=link.skylight_recipe_id,
                        summary=summary,
                        description=description,
                        meal_type=meal.meal_type,
                    )
                    skylight_recipe_id = link.skylight_recipe_id
                else:
                    skylight_recipe_id = self.skylight_client.create_meal_recipe(
                        summary=summary,
                        description=description,
                        meal_type=meal.meal_type,
                    )

                link = self.state_manager.upsert_recipe_link(
                    paprika_recipe_uid=recipe_uid,
                    skylight_recipe_id=skylight_recipe_id,
                    paprika_hash=paprika_hash,
                )
                recipe_links[recipe_uid] = link

            meal.skylight_recipe_id = link.skylight_recipe_id
            meal.paprika_recipe_hash = paprika_hash

    def _format_recipe_for_skylight(self, recipe: Dict[str, Any]) -> Tuple[str, str]:
        """Map Paprika recipe object to Skylight meal_recipe summary + description."""
        summary = (recipe.get("name") or "Untitled Recipe").strip()

        sections: List[str] = []
        description = (recipe.get("description") or "").strip()
        ingredients = (recipe.get("ingredients") or "").strip()
        directions = (recipe.get("directions") or "").strip()
        notes = (recipe.get("notes") or "").strip()
        source = (recipe.get("source") or "").strip()
        source_url = (recipe.get("source_url") or "").strip()
        servings = (recipe.get("servings") or "").strip()
        total_time = (recipe.get("total_time") or "").strip()
        prep_time = (recipe.get("prep_time") or "").strip()
        cook_time = (recipe.get("cook_time") or "").strip()
        paprika_uid = (recipe.get("uid") or "").strip()

        if description:
            sections.append(f"Summary\n{description}")
        if servings or total_time or prep_time or cook_time:
            meta_lines = []
            if servings:
                meta_lines.append(f"Servings: {servings}")
            if prep_time:
                meta_lines.append(f"Prep: {prep_time}")
            if cook_time:
                meta_lines.append(f"Cook: {cook_time}")
            if total_time:
                meta_lines.append(f"Total: {total_time}")
            sections.append("Details\n" + "\n".join(meta_lines))
        if ingredients:
            sections.append(f"Ingredients\n{ingredients}")
        if directions:
            sections.append(f"Directions\n{directions}")
        if notes:
            sections.append(f"Notes\n{notes}")
        if source or source_url:
            source_parts = [part for part in [source, source_url] if part]
            sections.append("Source\n" + "\n".join(source_parts))
        if paprika_uid:
            sections.append(f"Paprika\nRecipe UID: {paprika_uid}")

        return summary, "\n\n".join(section for section in sections if section).strip()

    def _apply_meal_changes(
        self,
        paprika_meals: List[MealItem],
        skylight_meals: List[MealItem],
        today: date,
        end_date: date,
        result: MealSyncResult,
    ) -> None:
        """Apply one-way meal updates from Paprika to Skylight."""
        persisted_meals = self.state_manager.get_active_paprika_meals_in_range(today, end_date)
        paprika_by_id = {meal.paprika_id: meal for meal in paprika_meals if meal.paprika_id}
        skylight_by_id = {meal.skylight_id: meal for meal in skylight_meals if meal.skylight_id}

        for meal in paprika_meals:
            prior = persisted_meals.get(meal.paprika_id)
            linked_skylight_id = prior.get("linked_skylight_id") if prior else None
            existing_skylight = skylight_by_id.get(linked_skylight_id) if linked_skylight_id else None

            if existing_skylight:
                needs_update = self._meal_requires_update(existing_skylight, meal)
                meal.skylight_id = linked_skylight_id
                if needs_update:
                    self._update_skylight_meal(meal)
                    result.meals_updated.append(meal.name)
            else:
                self._create_skylight_meal(meal)
                result.meals_created.append(meal.name)

            self.state_manager.save_meal(meal)

        for paprika_id, prior in persisted_meals.items():
            if paprika_id in paprika_by_id:
                continue

            linked_skylight_id = prior.get("linked_skylight_id")
            if linked_skylight_id:
                prior_date = datetime.strptime(prior["meal_date"], "%Y-%m-%d").date()
                self.skylight_client.delete_meal_sitting(linked_skylight_id, prior_date)
                self.state_manager.mark_meal_deleted(skylight_id=linked_skylight_id)
                self.state_manager.clear_meal_link_by_skylight_id(linked_skylight_id)

            self.state_manager.mark_meal_deleted(paprika_id=paprika_id)
            result.meals_deleted.append(prior.get("meal_name") or paprika_id)

    def _meal_requires_update(self, skylight_meal: MealItem, paprika_meal: MealItem) -> bool:
        """Determine if Skylight meal sitting should be overwritten from Paprika."""
        return (
            skylight_meal.name != paprika_meal.name
            or skylight_meal.date != paprika_meal.date
            or skylight_meal.meal_type != paprika_meal.meal_type
            or skylight_meal.skylight_recipe_id != paprika_meal.skylight_recipe_id
            or (skylight_meal.notes or "") != (paprika_meal.notes or "")
        )

    def _create_skylight_meal(self, meal: MealItem) -> None:
        """Create a new meal sitting in Skylight."""
        meal.skylight_id = self.skylight_client.create_meal_sitting(
            name=meal.name,
            date=meal.date,
            meal_type=meal.meal_type,
            meal_recipe_id=meal.skylight_recipe_id,
            note=meal.notes,
            description=None,
        )

    def _update_skylight_meal(self, meal: MealItem) -> None:
        """Update an existing meal sitting in Skylight."""
        if not meal.skylight_id:
            raise Exception("Cannot update Skylight meal without skylight_id")
        self.skylight_client.update_meal_sitting(
            sitting_id=meal.skylight_id,
            name=meal.name,
            date=meal.date,
            meal_type=meal.meal_type,
            meal_recipe_id=meal.skylight_recipe_id,
            note=meal.notes,
            description=None,
        )
