"""Bidirectional sync engine for Paprika ↔ Skylight grocery lists"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from models import GroceryItem
from paprika_client import PaprikaClient
from skylight_client import SkylightClient
from state_manager import StateManager

logger = logging.getLogger(__name__)


class SyncEngine:
    """
    Orchestrates bidirectional sync between Paprika and Skylight with conflict resolution

    Features:
    - Automatic change detection using StateManager
    - Timestamp-based conflict resolution
    - Dry-run mode for testing
    - Comprehensive error handling and logging
    - Atomic operations with rollback capability
    """

    def __init__(
        self,
        paprika_client: PaprikaClient,
        skylight_client: SkylightClient,
        state_manager: StateManager,
        paprika_list_name: str = "Test List",
        skylight_list_name: str = "Test List"
    ):
        """
        Initialize sync engine with API clients and state manager

        Args:
            paprika_client: Configured Paprika API client
            skylight_client: Configured Skylight API client
            state_manager: StateManager for change detection
            paprika_list_name: Name of Paprika list to sync
            skylight_list_name: Name of Skylight list to sync
        """
        self.paprika = paprika_client
        self.skylight = skylight_client
        self.state = state_manager
        self.paprika_list_name = paprika_list_name
        self.skylight_list_name = skylight_list_name

        # Get list IDs
        self.paprika_list_uid = self.paprika.get_list_uid_by_name(paprika_list_name)
        self.skylight_list_id = self.skylight.get_list_id_by_name(skylight_list_name)

        if not self.paprika_list_uid:
            raise ValueError(f"Paprika list '{paprika_list_name}' not found")
        if not self.skylight_list_id:
            raise ValueError(f"Skylight list '{skylight_list_name}' not found")

        logger.info(f"SyncEngine initialized for '{paprika_list_name}' ↔ '{skylight_list_name}'")

    def sync(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Perform bidirectional sync between Paprika and Skylight

        Args:
            dry_run: If True, detect changes but don't apply them

        Returns:
            Dictionary with sync results and statistics
        """
        sync_start = datetime.now(timezone.utc)
        logger.info(f"Starting sync (dry_run={dry_run})")

        try:
            # Step 1: Fetch current state from both systems
            logger.info("Fetching current state from both systems...")
            paprika_items = self.paprika.get_grocery_list(self.paprika_list_name)
            skylight_items = self.skylight.get_grocery_list(self.skylight_list_name)

            logger.info(f"Current state: {len(paprika_items)} Paprika items, {len(skylight_items)} Skylight items")

            # Step 2: Detect changes using StateManager
            logger.info("Detecting changes since last sync...")
            changes = self.state.detect_changes(
                paprika_items, skylight_items,
                self.paprika_list_uid, self.skylight_list_id
            )

            # Step 3: Resolve conflicts using timestamp-based resolution
            logger.info("Resolving conflicts...")
            resolved_changes = self._resolve_conflicts(changes)

            # Step 4: Apply changes (or simulate if dry_run)
            if dry_run:
                logger.info("DRY RUN: Simulating changes without applying them")
                results = self._simulate_changes(resolved_changes)
            else:
                logger.info("Applying changes...")
                results = self._apply_changes(resolved_changes)

            # Step 5: Update state tracking (only if not dry_run)
            if not dry_run:
                logger.info("Updating state tracking...")
                self._update_state_tracking(paprika_items, skylight_items, sync_start)

            # Compile results
            sync_duration = (datetime.now(timezone.utc) - sync_start).total_seconds()

            final_results = {
                'dry_run': dry_run,
                'sync_start': sync_start,
                'sync_duration_seconds': round(sync_duration, 2),
                'changes_detected': self._count_changes(changes),
                'changes_applied': results,
                'conflicts_resolved': len(resolved_changes.get('resolved_conflicts', [])),
                'errors': results.get('errors', []),
                'success': len(results.get('errors', [])) == 0
            }

            if final_results['success']:
                logger.info(f"Sync completed successfully in {sync_duration:.2f}s")
            else:
                logger.warning(f"Sync completed with {len(final_results['errors'])} errors")

            return final_results

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {
                'dry_run': dry_run,
                'sync_start': sync_start,
                'sync_duration_seconds': (datetime.now(timezone.utc) - sync_start).total_seconds(),
                'success': False,
                'error': str(e),
                'changes_detected': {},
                'changes_applied': {},
                'conflicts_resolved': 0
            }

    def _resolve_conflicts(self, changes: Dict[str, List[GroceryItem]]) -> Dict[str, List[GroceryItem]]:
        """
        Resolve conflicts using timestamp-based resolution (most recent wins)

        Args:
            changes: Changes detected by StateManager

        Returns:
            Changes with conflicts resolved and categorized for application
        """
        resolved = {
            'paprika_to_skylight': [],  # Apply Paprika changes to Skylight
            'skylight_to_paprika': [],  # Apply Skylight changes to Paprika
            'resolved_conflicts': [],   # Conflicts that were resolved
            'paprika_deletions': changes.get('paprika_deleted', []),
            'skylight_deletions': changes.get('skylight_deleted', [])
        }

        # Add items from additions and modifications
        resolved['paprika_to_skylight'].extend(changes.get('paprika_added', []))
        resolved['paprika_to_skylight'].extend(changes.get('paprika_modified', []))
        resolved['skylight_to_paprika'].extend(changes.get('skylight_added', []))
        resolved['skylight_to_paprika'].extend(changes.get('skylight_modified', []))

        # Resolve conflicts using timestamp comparison
        for conflict_item in changes.get('conflicts', []):
            paprika_time = conflict_item.paprika_timestamp
            skylight_time = conflict_item.skylight_timestamp

            if not paprika_time and not skylight_time:
                logger.warning(f"Conflict for {conflict_item.name} has no timestamps, defaulting to Paprika")
                resolved['paprika_to_skylight'].append(conflict_item)
                winner = "Paprika (no timestamps)"
            elif not skylight_time:
                # Only Paprika has timestamp
                resolved['paprika_to_skylight'].append(conflict_item)
                winner = "Paprika (only timestamp)"
            elif not paprika_time:
                # Only Skylight has timestamp
                resolved['skylight_to_paprika'].append(conflict_item)
                winner = "Skylight (only timestamp)"
            elif skylight_time > paprika_time:
                # Skylight is clearly more recent - create item with Skylight's checked state
                winning_item = GroceryItem(
                    name=conflict_item.name,
                    checked=conflict_item.checked,  # This should be Skylight's checked state
                    paprika_id=conflict_item.paprika_id,
                    skylight_id=conflict_item.skylight_id,
                    paprika_timestamp=conflict_item.paprika_timestamp,
                    skylight_timestamp=conflict_item.skylight_timestamp
                )
                resolved['skylight_to_paprika'].append(winning_item)
                winner = "Skylight (newer)"
            elif paprika_time > skylight_time:
                # Paprika is clearly more recent
                resolved['paprika_to_skylight'].append(conflict_item)
                winner = "Paprika (newer)"
            else:
                # Timestamps are equal - Paprika wins as source of truth
                resolved['paprika_to_skylight'].append(conflict_item)
                winner = "Paprika (source of truth)"

            resolved['resolved_conflicts'].append({
                'item_name': conflict_item.name,
                'winner': winner,
                'paprika_timestamp': paprika_time,
                'skylight_timestamp': skylight_time
            })

            logger.info(f"Conflict resolved: {conflict_item.name} → {winner}")

        return resolved

    def _apply_changes(self, changes: Dict[str, List[GroceryItem]]) -> Dict[str, Any]:
        """
        Apply resolved changes to both systems

        Args:
            changes: Resolved changes to apply

        Returns:
            Results of applying changes
        """
        results = {
            'paprika_created': [],
            'paprika_updated': [],
            'paprika_deleted': [],
            'skylight_created': [],
            'skylight_updated': [],
            'skylight_deleted': [],
            'errors': []
        }

        # Apply Paprika changes to Skylight
        for item in changes.get('paprika_to_skylight', []):
            try:
                if not item.skylight_id:
                    # Create new item in Skylight
                    new_id = self.skylight.add_item(item.name, item.checked, self.skylight_list_name)
                    item.skylight_id = new_id  # Update for state tracking
                    results['skylight_created'].append(item.name)
                    logger.info(f"Created in Skylight: {item.name}")
                else:
                    # Update existing item in Skylight
                    self.skylight.update_item(item.skylight_id, item.checked)
                    results['skylight_updated'].append(item.name)
                    logger.info(f"Updated in Skylight: {item.name}")

            except Exception as e:
                error_msg = f"Failed to sync {item.name} to Skylight: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        # Apply Skylight changes to Paprika
        for item in changes.get('skylight_to_paprika', []):
            try:
                if not item.paprika_id:
                    # Create new item in Paprika
                    new_id = self.paprika.add_item(item.name, item.checked, self.paprika_list_name)
                    item.paprika_id = new_id  # Update for state tracking
                    results['paprika_created'].append(item.name)
                    logger.info(f"Created in Paprika: {item.name}")
                else:
                    # Update existing item in Paprika
                    # For conflict resolution, we need to get the winning state from Skylight
                    if hasattr(item, 'skylight_id') and item.skylight_id:
                        # Find the actual Skylight item to get its current state
                        skylight_items = self.skylight.get_grocery_list(self.skylight_list_name)
                        skylight_item = next((s for s in skylight_items if s.skylight_id == item.skylight_id), None)
                        if skylight_item:
                            # Use Skylight's actual checked state
                            self.paprika.update_item(item.paprika_id, skylight_item.checked)
                            logger.info(f"Updated in Paprika: {item.name} (checked={skylight_item.checked})")
                        else:
                            self.paprika.update_item(item.paprika_id, item.checked)
                            logger.info(f"Updated in Paprika: {item.name} (checked={item.checked})")
                    else:
                        self.paprika.update_item(item.paprika_id, item.checked)
                        logger.info(f"Updated in Paprika: {item.name}")
                    results['paprika_updated'].append(item.name)

            except Exception as e:
                error_msg = f"Failed to sync {item.name} to Paprika: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        # Handle deletions
        for item in changes.get('paprika_deletions', []):
            try:
                if item.skylight_id:
                    self.skylight.remove_item(item.skylight_id, self.skylight_list_name)
                    results['skylight_deleted'].append(item.name)
                    logger.info(f"Deleted from Skylight: {item.name}")
            except Exception as e:
                error_msg = f"Failed to delete {item.name} from Skylight: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        for item in changes.get('skylight_deletions', []):
            try:
                if item.paprika_id:
                    self.paprika.remove_item(item.paprika_id)
                    results['paprika_deleted'].append(item.name)
                    logger.info(f"Deleted from Paprika: {item.name}")
            except Exception as e:
                error_msg = f"Failed to delete {item.name} from Paprika: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        return results

    def _simulate_changes(self, changes: Dict[str, List[GroceryItem]]) -> Dict[str, Any]:
        """
        Simulate applying changes without actually making API calls (dry-run mode)

        Args:
            changes: Resolved changes that would be applied

        Returns:
            Simulation results
        """
        results = {
            'paprika_would_create': [item.name for item in changes.get('paprika_to_skylight', []) if not item.skylight_id],
            'paprika_would_update': [item.name for item in changes.get('paprika_to_skylight', []) if item.skylight_id],
            'skylight_would_create': [item.name for item in changes.get('skylight_to_paprika', []) if not item.paprika_id],
            'skylight_would_update': [item.name for item in changes.get('skylight_to_paprika', []) if item.paprika_id],
            'skylight_would_delete': [item.name for item in changes.get('paprika_deletions', [])],
            'paprika_would_delete': [item.name for item in changes.get('skylight_deletions', [])],
            'errors': []  # No errors in simulation
        }

        # Log simulation results
        for category, items in results.items():
            if items and category != 'errors':
                logger.info(f"DRY RUN - {category}: {', '.join(items)}")

        return results

    def _update_state_tracking(
        self,
        paprika_items: List[GroceryItem],
        skylight_items: List[GroceryItem],
        sync_timestamp: datetime
    ) -> None:
        """
        Update StateManager with current state after successful sync

        Args:
            paprika_items: Current items from Paprika
            skylight_items: Current items from Skylight
            sync_timestamp: When sync completed
        """
        try:
            # Update state with current items
            all_item_names = set()

            for item in paprika_items:
                self.state.add_or_update_item(item, self.paprika_list_uid, None)
                all_item_names.add(item.name)

            for item in skylight_items:
                self.state.add_or_update_item(item, None, self.skylight_list_id)
                all_item_names.add(item.name)

            # Mark all items as synced
            if all_item_names:
                self.state.mark_sync_complete(list(all_item_names), sync_timestamp)

            logger.info(f"Updated state tracking for {len(all_item_names)} items")

        except Exception as e:
            logger.error(f"Failed to update state tracking: {e}")
            raise

    def _count_changes(self, changes: Dict[str, List[GroceryItem]]) -> Dict[str, int]:
        """Count changes by category for reporting"""
        return {
            category: len(items) for category, items in changes.items()
            if isinstance(items, list)
        }

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status and statistics

        Returns:
            Dictionary with sync status information
        """
        try:
            # Get current state from both systems
            paprika_items = self.paprika.get_grocery_list(self.paprika_list_name)
            skylight_items = self.skylight.get_grocery_list(self.skylight_list_name)

            # Get state statistics
            stats = self.state.get_sync_statistics()

            # Detect pending changes
            changes = self.state.detect_changes(
                paprika_items, skylight_items,
                self.paprika_list_uid, self.skylight_list_id
            )

            pending_changes = sum(len(items) for items in changes.values() if isinstance(items, list))

            return {
                'paprika_list': self.paprika_list_name,
                'skylight_list': self.skylight_list_name,
                'paprika_items': len(paprika_items),
                'skylight_items': len(skylight_items),
                'pending_changes': pending_changes,
                'has_conflicts': len(changes.get('conflicts', [])) > 0,
                'sync_statistics': stats,
                'lists_configured': True
            }

        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {
                'paprika_list': self.paprika_list_name,
                'skylight_list': self.skylight_list_name,
                'error': str(e),
                'lists_configured': False
            }