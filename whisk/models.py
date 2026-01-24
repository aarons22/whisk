"""Data models for list sync"""

from dataclasses import dataclass
from datetime import datetime, timezone
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
