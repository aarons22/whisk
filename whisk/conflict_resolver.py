"""Configurable conflict resolution system for Paprika ↔ Skylight sync"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from .state_manager import StateManager, ItemLink
from .paprika_client import PaprikaClient
from .skylight_client import SkylightClient

logger = logging.getLogger(__name__)


class ConflictStrategy(Enum):
    """Available conflict resolution strategies"""
    PAPRIKA_WINS = "paprika_wins"
    SKYLIGHT_WINS = "skylight_wins"
    NEWEST_WINS = "newest_wins"
    PROMPT_USER = "prompt_user"


@dataclass
class ConflictResolution:
    """Result of conflict resolution"""
    paprika_item_id: int
    skylight_item_id: int
    item_name: str
    paprika_checked: bool
    skylight_checked: bool
    winner: str
    action_taken: str
    confidence: float
    paprika_timestamp: Optional[datetime] = None
    skylight_timestamp: Optional[datetime] = None


class ConflictResolver:
    """
    Handles conflicts between Paprika and Skylight items using configurable strategies
    """

    def __init__(self, state_manager: StateManager,
                 paprika_client: PaprikaClient,
                 skylight_client: SkylightClient,
                 config: dict = None):
        """
        Initialize ConflictResolver

        Args:
            state_manager: StateManager instance
            paprika_client: PaprikaClient for applying changes
            skylight_client: SkylightClient for applying changes
            config: Configuration options
        """
        self.state = state_manager
        self.paprika = paprika_client
        self.skylight = skylight_client
        self.config = config or {}

        # Default configuration
        self.strategy = ConflictStrategy(self.config.get('strategy', 'paprika_wins'))
        self.paprika_always_wins = self.config.get('paprika_always_wins', True)
        self.timestamp_tolerance_seconds = self.config.get('timestamp_tolerance_seconds', 60)
        self.dry_run = self.config.get('dry_run', False)

        # Store pre-sync state for change detection
        self._pre_sync_states = {}

        logger.info(f"ConflictResolver initialized with strategy: {self.strategy.value}")

    def capture_pre_sync_states(self) -> None:
        """Capture the current database states before sync starts for change detection"""
        try:
            cursor = self.state.conn.cursor()
            cursor.execute("""
                SELECT p.paprika_id, p.name, p.checked as paprika_checked,
                       s.skylight_id, s.checked as skylight_checked
                FROM item_links l
                JOIN paprika_items p ON l.paprika_item_id = p.id
                JOIN skylight_items s ON l.skylight_item_id = s.id
            """)

            for row in cursor.fetchall():
                key = (row['paprika_id'], row['skylight_id'])
                self._pre_sync_states[key] = {
                    'paprika_checked': bool(row['paprika_checked']),
                    'skylight_checked': bool(row['skylight_checked']),
                    'name': row['name']
                }

            logger.debug(f"Captured pre-sync states for {len(self._pre_sync_states)} items")
        except Exception as e:
            logger.error(f"Failed to capture pre-sync states: {e}")
            self._pre_sync_states = {}

    def resolve_all_conflicts(self, paprika_list_name: str,
                             skylight_list_name: str) -> List[ConflictResolution]:
        """
        Resolve all conflicts between linked items

        Args:
            paprika_list_name: Name of Paprika list
            skylight_list_name: Name of Skylight list

        Returns:
            List of conflict resolutions applied
        """
        logger.info("Starting conflict resolution...")

        # Get all conflicts
        conflicts = self.state.get_linked_items_with_conflicts()
        logger.info(f"Found {len(conflicts)} conflicts to resolve")

        if not conflicts:
            return []

        resolutions = []
        for conflict in conflicts:
            try:
                resolution = self._resolve_single_conflict(
                    conflict, paprika_list_name, skylight_list_name
                )
                resolutions.append(resolution)

                # Log the resolution
                self.state.log_sync_operation(
                    'CONFLICT',
                    paprika_item_id=conflict.paprika_item_id,
                    skylight_item_id=conflict.skylight_item_id,
                    details=f"Resolved conflict: {resolution.winner} wins, "
                           f"action: {resolution.action_taken}"
                )

                logger.info(f"Resolved conflict for '{resolution.item_name}': "
                           f"{resolution.winner} wins ({resolution.action_taken})")

            except Exception as e:
                logger.error(f"Failed to resolve conflict for item {conflict.paprika_item.name}: {e}")
                # Continue with other conflicts

        logger.info(f"Successfully resolved {len(resolutions)}/{len(conflicts)} conflicts")
        return resolutions

    def _resolve_single_conflict(self, conflict: ItemLink,
                                paprika_list_name: str,
                                skylight_list_name: str) -> ConflictResolution:
        """
        Resolve a single conflict using the configured strategy

        Args:
            conflict: ItemLink with conflicting items
            paprika_list_name: Name of Paprika list
            skylight_list_name: Name of Skylight list

        Returns:
            ConflictResolution result
        """
        p_item = conflict.paprika_item
        s_item = conflict.skylight_item

        logger.debug(f"Resolving conflict for '{p_item.name}': "
                    f"Paprika={p_item.checked}, Skylight={s_item.checked}")

        # Determine winner based on strategy
        winner, action, confidence = self._determine_winner(p_item, s_item)

        # Apply the resolution
        if not self.dry_run:
            self._apply_resolution(
                winner, p_item, s_item,
                paprika_list_name, skylight_list_name
            )

        return ConflictResolution(
            paprika_item_id=conflict.paprika_item_id,
            skylight_item_id=conflict.skylight_item_id,
            item_name=p_item.name,
            paprika_checked=p_item.checked,
            skylight_checked=s_item.checked,
            winner=winner,
            action_taken=action,
            confidence=confidence,
            paprika_timestamp=p_item.last_modified_at,
            skylight_timestamp=s_item.skylight_updated_at
        )

    def _determine_winner(self, p_item, s_item) -> Tuple[str, str, float]:
        """
        Determine conflict winner based on strategy

        Args:
            p_item: Paprika item
            s_item: Skylight item

        Returns:
            Tuple of (winner, action_description, confidence)
        """
        if self.strategy == ConflictStrategy.PAPRIKA_WINS:
            return "Paprika", f"Update Skylight to {p_item.checked}", 1.0

        elif self.strategy == ConflictStrategy.SKYLIGHT_WINS:
            return "Skylight", f"Update Paprika to {s_item.checked}", 1.0

        elif self.strategy == ConflictStrategy.NEWEST_WINS:
            return self._resolve_by_timestamp(p_item, s_item)

        elif self.strategy == ConflictStrategy.PROMPT_USER:
            # For now, fall back to Paprika wins
            # In a real implementation, this would prompt the user
            logger.warning("User prompt not implemented, falling back to Paprika wins")
            return "Paprika (fallback)", f"Update Skylight to {p_item.checked}", 0.8

        else:
            # Default fallback
            return "Paprika (default)", f"Update Skylight to {p_item.checked}", 0.7

    def _resolve_by_timestamp(self, p_item, s_item) -> Tuple[str, str, float]:
        """
        Resolve conflict by comparing timestamps, with fallback to change detection

        Since Skylight doesn't provide updated timestamps, we also check which
        system actually changed since the last sync.

        Args:
            p_item: Paprika item with synthetic timestamps
            s_item: Skylight item with real timestamps (but only created_at)

        Returns:
            Tuple of (winner, action_description, confidence)
        """
        p_timestamp = p_item.last_modified_at
        s_timestamp = s_item.skylight_updated_at

        # First, try to detect which system actually changed by checking our database
        # If we can determine the source of change, that should win regardless of timestamps
        change_source = self._detect_change_source(p_item, s_item)
        if change_source:
            system, confidence = change_source
            if system == "skylight":
                return "Skylight (changed)", f"Update Paprika to {s_item.checked}", confidence
            elif system == "paprika":
                return "Paprika (changed)", f"Update Skylight to {p_item.checked}", confidence

        # Fallback to timestamp-based resolution if we can't detect change source
        if not p_timestamp and not s_timestamp:
            # No timestamps available - fallback based on config
            if self.paprika_always_wins:
                return "Paprika (no timestamps)", f"Update Skylight to {p_item.checked}", 0.6
            else:
                return "Skylight (no timestamps)", f"Update Paprika to {s_item.checked}", 0.6

        elif not s_timestamp:
            # Only Paprika has timestamp
            return "Paprika (only timestamp)", f"Update Skylight to {p_item.checked}", 0.8

        elif not p_timestamp:
            # Only Skylight has timestamp
            return "Skylight (only timestamp)", f"Update Paprika to {s_item.checked}", 0.8

        else:
            # Both have timestamps - compare
            time_diff = (p_timestamp - s_timestamp).total_seconds()

            # DEBUG: Log actual timestamps for debugging
            logger.debug(f"Timestamp comparison for '{p_item.name}': "
                        f"Paprika={p_timestamp}, Skylight={s_timestamp}, "
                        f"diff={time_diff:.1f}s")

            if abs(time_diff) <= self.timestamp_tolerance_seconds:
                # Timestamps are very close - use Paprika as tiebreaker
                return "Paprika (tie)", f"Update Skylight to {p_item.checked}", 0.7

            elif time_diff > 0:
                # Paprika is newer
                return "Paprika (newer)", f"Update Skylight to {p_item.checked}", 0.9

            else:
                # Skylight is newer
                return "Skylight (newer)", f"Update Paprika to {s_item.checked}", 0.9

    def _detect_change_source(self, p_item, s_item) -> Optional[Tuple[str, float]]:
        """
        Detect which system actually changed by comparing with pre-sync state

        Args:
            p_item: Current Paprika item
            s_item: Current Skylight item

        Returns:
            Tuple of (system_name, confidence) or None if can't determine
        """
        try:
            # Look up pre-sync state
            key = (p_item.paprika_id, s_item.skylight_id)
            pre_sync_state = self._pre_sync_states.get(key)

            if not pre_sync_state:
                logger.debug(f"No pre-sync state found for {p_item.name} (key: {key})")
                return None

            # Get the states before sync started
            last_paprika_checked = pre_sync_state['paprika_checked']
            last_skylight_checked = pre_sync_state['skylight_checked']

            # Current states
            current_paprika_checked = p_item.checked
            current_skylight_checked = s_item.checked

            # Detect changes from pre-sync state
            paprika_changed = (last_paprika_checked != current_paprika_checked)
            skylight_changed = (last_skylight_checked != current_skylight_checked)

            logger.debug(f"Change detection for '{p_item.name}': "
                       f"Paprika {last_paprika_checked}→{current_paprika_checked} (changed={paprika_changed}), "
                       f"Skylight {last_skylight_checked}→{current_skylight_checked} (changed={skylight_changed})")

            if skylight_changed and not paprika_changed:
                return ("skylight", 0.95)  # High confidence - only Skylight changed
            elif paprika_changed and not skylight_changed:
                return ("paprika", 0.95)   # High confidence - only Paprika changed
            elif paprika_changed and skylight_changed:
                # Both changed - can't determine source, fall back to timestamps
                logger.debug(f"Both systems changed for '{p_item.name}', falling back to timestamps")
                return None
            else:
                # Neither changed according to our records - this shouldn't happen in a conflict
                logger.warning(f"Conflict detected but no changes found for '{p_item.name}'")
                return None

        except Exception as e:
            logger.error(f"Error detecting change source for {p_item.name}: {e}")
            return None

    def _apply_resolution(self, winner: str, p_item, s_item,
                         paprika_list_name: str, skylight_list_name: str) -> None:
        """
        Apply the conflict resolution by updating the losing system

        Args:
            winner: Winner identifier
            p_item: Paprika item
            s_item: Skylight item
            paprika_list_name: Name of Paprika list
            skylight_list_name: Name of Skylight list
        """
        try:
            if winner.startswith("Paprika"):
                # Paprika wins - update Skylight
                self.skylight.update_item(s_item.skylight_id, p_item.checked, list_name=skylight_list_name)
                logger.debug(f"Updated Skylight item {s_item.name} to checked={p_item.checked}")

                # IMPORTANT: Update our database record for Skylight to reflect the change
                # This ensures future change detection works correctly
                self._update_skylight_database_state(s_item.skylight_id, p_item.checked)

            elif winner.startswith("Skylight"):
                # Skylight wins - update Paprika
                self.paprika.update_item(p_item.paprika_id, s_item.checked)
                logger.debug(f"Updated Paprika item {p_item.name} to checked={s_item.checked}")

                # IMPORTANT: Update our database record for Paprika to reflect the change
                # This ensures future change detection works correctly
                self._update_paprika_database_state(p_item.paprika_id, s_item.checked)

            else:
                logger.warning(f"Unknown winner format: {winner}")

        except Exception as e:
            logger.error(f"Failed to apply resolution for {p_item.name}: {e}")
            raise

    def _update_skylight_database_state(self, skylight_id: str, new_checked_state: bool) -> None:
        """Update Skylight item's checked state in our database"""
        try:
            cursor = self.state.conn.cursor()
            cursor.execute("""
                UPDATE skylight_items
                SET checked = ?
                WHERE skylight_id = ?
            """, (new_checked_state, skylight_id))
            self.state.conn.commit()
            logger.debug(f"Updated Skylight database state: {skylight_id} checked={new_checked_state}")
        except Exception as e:
            logger.error(f"Failed to update Skylight database state: {e}")

    def _update_paprika_database_state(self, paprika_id: str, new_checked_state: bool) -> None:
        """Update Paprika item's checked state in our database"""
        try:
            cursor = self.state.conn.cursor()
            cursor.execute("""
                UPDATE paprika_items
                SET checked = ?
                WHERE paprika_id = ?
            """, (new_checked_state, paprika_id))
            self.state.conn.commit()
            logger.debug(f"Updated Paprika database state: {paprika_id} checked={new_checked_state}")
        except Exception as e:
            logger.error(f"Failed to update Paprika database state: {e}")

    def get_conflict_summary(self) -> Dict[str, Any]:
        """
        Get summary of current conflicts

        Returns:
            Dictionary with conflict analysis
        """
        try:
            conflicts = self.state.get_linked_items_with_conflicts()

            # Analyze conflict patterns
            paprika_true_conflicts = 0
            skylight_true_conflicts = 0

            conflict_details = []
            for conflict in conflicts:
                p_item = conflict.paprika_item
                s_item = conflict.skylight_item

                if p_item.checked and not s_item.checked:
                    paprika_true_conflicts += 1
                elif not p_item.checked and s_item.checked:
                    skylight_true_conflicts += 1

                # Predict resolution
                winner, action, confidence = self._determine_winner(p_item, s_item)

                conflict_details.append({
                    'item_name': p_item.name,
                    'paprika_checked': p_item.checked,
                    'skylight_checked': s_item.checked,
                    'predicted_winner': winner,
                    'predicted_action': action,
                    'confidence': confidence,
                    'link_confidence': conflict.confidence_score
                })

            return {
                'total_conflicts': len(conflicts),
                'paprika_checked_conflicts': paprika_true_conflicts,
                'skylight_checked_conflicts': skylight_true_conflicts,
                'strategy': self.strategy.value,
                'dry_run': self.dry_run,
                'conflict_details': conflict_details
            }

        except Exception as e:
            logger.error(f"Failed to get conflict summary: {e}")
            return {'error': str(e)}

    def set_strategy(self, strategy: ConflictStrategy) -> None:
        """
        Change the conflict resolution strategy

        Args:
            strategy: New strategy to use
        """
        old_strategy = self.strategy
        self.strategy = strategy
        logger.info(f"Changed conflict resolution strategy from {old_strategy.value} to {strategy.value}")

    def set_dry_run(self, dry_run: bool) -> None:
        """
        Enable or disable dry-run mode

        Args:
            dry_run: True to enable dry-run mode
        """
        self.dry_run = dry_run
        logger.info(f"Set dry-run mode to {dry_run}")

# Utility function for configuration
def create_conflict_resolver_config(
    strategy: str = "paprika_wins",
    paprika_always_wins: bool = True,
    timestamp_tolerance_seconds: int = 60,
    dry_run: bool = False
) -> dict:
    """
    Create a configuration dictionary for ConflictResolver

    Args:
        strategy: Conflict resolution strategy
        paprika_always_wins: Whether Paprika wins ties
        timestamp_tolerance_seconds: Time difference tolerance for "newest wins"
        dry_run: Whether to simulate changes only

    Returns:
        Configuration dictionary
    """
    return {
        'strategy': strategy,
        'paprika_always_wins': paprika_always_wins,
        'timestamp_tolerance_seconds': timestamp_tolerance_seconds,
        'dry_run': dry_run
    }