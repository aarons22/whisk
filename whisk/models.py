"""Data models for list sync"""

from dataclasses import dataclass
from datetime import datetime, timezone, date
from typing import Optional


@dataclass
class ListItem:
    """Represents a list item that can exist in both Paprika and Skylight"""

    name: str
    checked: bool = False
    paprika_id: Optional[str] = None
    skylight_id: Optional[str] = None
    paprika_timestamp: Optional[datetime] = None
    skylight_timestamp: Optional[datetime] = None

    @property
    def latest_timestamp(self) -> datetime:
        """Return most recent timestamp from either system"""
        timestamps = [t for t in [self.paprika_timestamp, self.skylight_timestamp] if t]
        return max(timestamps) if timestamps else datetime.now(timezone.utc)

    @property
    def exists_in_paprika(self) -> bool:
        """Check if item exists in Paprika"""
        return self.paprika_id is not None

    @property
    def exists_in_skylight(self) -> bool:
        """Check if item exists in Skylight"""
        return self.skylight_id is not None

    def __repr__(self) -> str:
        status = "✓" if self.checked else " "
        systems = []
        if self.exists_in_paprika:
            systems.append("P")
        if self.exists_in_skylight:
            systems.append("S")
        system_str = "+".join(systems) if systems else "none"
        return f"ListItem([{status}] {self.name} - {system_str})"


@dataclass
class MealItem:
    """Represents a meal that can exist in both Paprika and Skylight"""

    name: str
    date: date
    meal_type: str  # breakfast, lunch, dinner, snack
    paprika_id: Optional[str] = None
    skylight_id: Optional[str] = None
    recipe_uid: Optional[str] = None
    paprika_recipe_hash: Optional[str] = None
    skylight_recipe_id: Optional[str] = None
    recipe_description: Optional[str] = None
    notes: Optional[str] = None
    paprika_timestamp: Optional[datetime] = None
    skylight_timestamp: Optional[datetime] = None

    @property
    def latest_timestamp(self) -> datetime:
        """Return most recent timestamp"""
        timestamps = [t for t in [self.paprika_timestamp, self.skylight_timestamp] if t]
        return max(timestamps) if timestamps else datetime.now(timezone.utc)

    @property
    def exists_in_paprika(self) -> bool:
        """Check if meal exists in Paprika"""
        return self.paprika_id is not None

    @property
    def exists_in_skylight(self) -> bool:
        """Check if meal exists in Skylight"""
        return self.skylight_id is not None

    def __repr__(self) -> str:
        systems = []
        if self.exists_in_paprika:
            systems.append("P")
        if self.exists_in_skylight:
            systems.append("S")
        system_str = "+".join(systems) if systems else "none"
        return f"MealItem({self.name} on {self.date} ({self.meal_type}) - {system_str})"


@dataclass
class RecipeSyncLink:
    """Persistent mapping between Paprika recipes and Skylight meal recipes"""

    paprika_recipe_uid: str
    skylight_recipe_id: str
    paprika_hash: Optional[str] = None
    last_synced_at: Optional[datetime] = None
