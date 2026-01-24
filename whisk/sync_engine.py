"""Sync Engine using Phase 6 Architecture

This version uses:
- StateManager: 3-table schema with proper relationships
- ItemLinker: Intelligent fuzzy matching with confidence scoring
- ConflictResolver: Configurable strategies with timestamp logic
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .models import GroceryItem
from .paprika_client import PaprikaClient
from .skylight_client import SkylightClient
from .state_manager import StateManager
from .item_linker import ItemLinker
from .conflict_resolver import ConflictResolver, create_conflict_resolver_config

logger = logging.getLogger(__name__)


class SyncEngine:
    """
    Phase 6 Sync Engine using new architecture with proper duplicate handling,
    synthetic timestamps, and configurable conflict resolution
    """

    def __init__(
        self,
        paprika_client: PaprikaClient,
        skylight_client: SkylightClient,
        state_manager: StateManager,
        paprika_list_name: str,
        skylight_list_name: str,
        config: dict = None
    ):
        """
        Initialize SyncEngine with Phase 6 components

        Args:
            paprika_client: Configured Paprika API client
            skylight_client: Configured Skylight API client
            state_manager: StateManager for 3-table architecture
            paprika_list_name: Name of Paprika list to sync
            skylight_list_name: Name of Skylight list to sync
            config: Configuration for linking and conflict resolution
        """
        self.paprika = paprika_client
        self.skylight = skylight_client
        self.state = state_manager
        self.paprika_list_name = paprika_list_name
        self.skylight_list_name = skylight_list_name
        self.config = config or {}

        # Get list IDs
        self.paprika_list_uid = self.paprika.get_list_uid_by_name(paprika_list_name)
        self.skylight_list_id = self.skylight.get_list_id_by_name(skylight_list_name)

        if not self.paprika_list_uid:
            raise ValueError(f"Paprika list '{paprika_list_name}' not found")
        if not self.skylight_list_id:
            raise ValueError(f"Skylight list '{skylight_list_name}' not found")

        # Initialize Phase 6 components
        linker_config = self.config.get('linking', {})
        self.item_linker = ItemLinker(self.state, linker_config)

        resolver_config = create_conflict_resolver_config(
            strategy=self.config.get('conflict_strategy', 'paprika_wins'),
            paprika_always_wins=self.config.get('paprika_always_wins', True),
            timestamp_tolerance_seconds=self.config.get('timestamp_tolerance', 60),
            dry_run=False  # Will be set per sync call
        )
        self.conflict_resolver = ConflictResolver(
            self.state, self.paprika, self.skylight, resolver_config
        )

        logger.info(f"SyncEngine initialized for '{paprika_list_name}' ↔ '{skylight_list_name}'")
        logger.info(f"Using conflict strategy: {resolver_config['strategy']}")

    def sync(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Perform bidirectional sync using Phase 6 architecture

        Args:
            dry_run: If True, simulate changes without applying them

        Returns:
            Dictionary with comprehensive sync results
        """
        sync_start = datetime.now(timezone.utc)
        logger.info(f"Starting SyncEngine sync (dry_run={dry_run})")

        try:
            # Capture pre-sync database states for change detection
            self.conflict_resolver.capture_pre_sync_states()

            # Phase 1: Data Collection with Synthetic Timestamps
            logger.info("Phase 1: Collecting data from both systems...")
            paprika_items = self.paprika.get_grocery_list(self.paprika_list_name)
            skylight_items = self.skylight.get_grocery_list(self.skylight_list_name)

            logger.info(f"Retrieved: {len(paprika_items)} Paprika items, {len(skylight_items)} Skylight items")

            # Update state with current items (this handles synthetic timestamps)
            paprika_db_items = []
            for item in paprika_items:
                db_item = self.state.upsert_paprika_item(item, self.paprika_list_uid)
                paprika_db_items.append(db_item)

            skylight_db_items = []
            for item in skylight_items:
                db_item = self.state.upsert_skylight_item(item, self.skylight_list_id)
                skylight_db_items.append(db_item)

            # Mark items not seen as potentially deleted (Paprika as source of truth)
            deleted_count = self.state.mark_unseen_paprika_items_as_deleted()
            if deleted_count > 0:
                logger.info(f"Marked {deleted_count} unseen Paprika items as deleted")

            # Phase 2: Intelligent Item Linking
            logger.info("Phase 2: Linking items between systems...")
            linking_summary = self.item_linker.get_linking_summary()
            logger.info(f"Pre-linking: {linking_summary['unlinked_paprika']} unlinked Paprika, "
                       f"{linking_summary['unlinked_skylight']} unlinked Skylight")

            matches = self.item_linker.link_all_items()
            logger.info(f"Linked {len(matches)} items with intelligent matching")

            # Show linking results
            exact_matches = sum(1 for m in matches if m.confidence_score == 1.0)
            fuzzy_matches = len(matches) - exact_matches
            if matches:
                logger.info(f"Linking quality: {exact_matches} exact, {fuzzy_matches} fuzzy")

            # Phase 3: Handle New Items (Create in other system)
            logger.info("Phase 3: Creating items in other systems...")
            create_results = self._handle_new_items(dry_run)

            # Phase 4: Conflict Resolution
            logger.info("Phase 4: Resolving conflicts...")
            self.conflict_resolver.set_dry_run(dry_run)

            conflict_summary = self.conflict_resolver.get_conflict_summary()
            logger.info(f"Found {conflict_summary['total_conflicts']} conflicts to resolve")

            if conflict_summary['total_conflicts'] > 0:
                resolutions = self.conflict_resolver.resolve_all_conflicts(
                    self.paprika_list_name, self.skylight_list_name
                )
                logger.info(f"Resolved {len(resolutions)} conflicts using {conflict_summary['strategy']} strategy")
            else:
                resolutions = []

            # Phase 5: Final Statistics
            sync_duration = (datetime.now(timezone.utc) - sync_start).total_seconds()
            final_stats = self.state.get_sync_statistics()

            results = {
                'dry_run': dry_run,
                'sync_start': sync_start,
                'sync_duration_seconds': round(sync_duration, 2),
                'paprika_items': len(paprika_items),
                'skylight_items': len(skylight_items),
                'items_linked': len(matches),
                'exact_matches': exact_matches,
                'fuzzy_matches': fuzzy_matches,
                'new_items_created': create_results,
                'conflicts_resolved': len(resolutions),
                'final_statistics': final_stats,
                'success': True,
                'errors': []
            }

            logger.info(f"SyncEngine completed successfully in {sync_duration:.2f}s")
            logger.info(f"Results: {results['items_linked']} linked, "
                       f"{sum(create_results.values())} created, "
                       f"{results['conflicts_resolved']} conflicts resolved")

            return results

        except Exception as e:
            logger.error(f"SyncEngine sync failed: {e}")
            sync_duration = (datetime.now(timezone.utc) - sync_start).total_seconds()
            return {
                'dry_run': dry_run,
                'sync_start': sync_start,
                'sync_duration_seconds': sync_duration,
                'success': False,
                'error': str(e),
                'paprika_items': 0,
                'skylight_items': 0,
                'items_linked': 0,
                'conflicts_resolved': 0
            }

    def _handle_new_items(self, dry_run: bool) -> Dict[str, int]:
        """
        Handle creation of items that exist in one system but not the other

        Args:
            dry_run: If True, simulate without creating items

        Returns:
            Dictionary with creation counts
        """
        results = {
            'paprika_created': 0,
            'skylight_created': 0
        }

        # Get unlinked items
        unlinked_paprika = self.state.get_unlinked_paprika_items()
        unlinked_skylight = self.state.get_unlinked_skylight_items()

        # Create Skylight items for unlinked Paprika items
        for p_item in unlinked_paprika:
            try:
                if not dry_run:
                    # Create in Skylight
                    skylight_id = self.skylight.add_item(p_item.name, p_item.checked, self.skylight_list_name)

                    # Create Skylight database entry
                    skylight_item = GroceryItem(
                        name=p_item.name,
                        checked=p_item.checked,
                        skylight_id=skylight_id,
                        skylight_timestamp=datetime.now(timezone.utc)
                    )
                    s_db_item = self.state.upsert_skylight_item(skylight_item, self.skylight_list_id)

                    # Link the items
                    self.state.create_item_link(p_item.id, s_db_item.id, confidence_score=1.0)

                    logger.info(f"Created '{p_item.name}' in Skylight (ID: {skylight_id}) and linked")
                else:
                    logger.info(f"DRY RUN: Would create '{p_item.name}' in Skylight")

                results['skylight_created'] += 1

            except Exception as e:
                logger.error(f"Failed to create '{p_item.name}' in Skylight: {e}")

        # Create Paprika items for unlinked Skylight items
        for s_item in unlinked_skylight:
            try:
                if not dry_run:
                    # Create in Paprika
                    paprika_id = self.paprika.add_item(s_item.name, s_item.checked, self.paprika_list_name)

                    # Create Paprika database entry
                    paprika_item = GroceryItem(
                        name=s_item.name,
                        checked=s_item.checked,
                        paprika_id=paprika_id
                    )
                    p_db_item = self.state.upsert_paprika_item(paprika_item, self.paprika_list_uid)

                    # Link the items
                    self.state.create_item_link(p_db_item.id, s_item.id, confidence_score=1.0)

                    logger.info(f"Created '{s_item.name}' in Paprika (ID: {paprika_id}) and linked")
                else:
                    logger.info(f"DRY RUN: Would create '{s_item.name}' in Paprika")

                results['paprika_created'] += 1

            except Exception as e:
                logger.error(f"Failed to create '{s_item.name}' in Paprika: {e}")

        return results

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status using Phase 6 architecture

        Returns:
            Dictionary with comprehensive sync status
        """
        try:
            # Get linking summary
            linking_summary = self.item_linker.get_linking_summary()

            # Get conflict summary
            conflict_summary = self.conflict_resolver.get_conflict_summary()

            # Get database statistics
            db_stats = self.state.get_sync_statistics()

            return {
                'paprika_list': self.paprika_list_name,
                'skylight_list': self.skylight_list_name,
                'paprika_list_uid': self.paprika_list_uid,
                'skylight_list_id': self.skylight_list_id,
                'database_statistics': db_stats,
                'linking_summary': linking_summary,
                'conflict_summary': conflict_summary,
                'architecture_version': 'Phase 6 (StateManager + ItemLinker + ConflictResolver)',
                'lists_configured': True
            }

        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {
                'paprika_list': self.paprika_list_name,
                'skylight_list': self.skylight_list_name,
                'error': str(e),
                'lists_configured': False,
                'architecture_version': 'Phase 6 (Error)'
            }