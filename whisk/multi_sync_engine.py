"""
Multi-List Sync Engine for Whisk

Handles bidirectional synchronization between multiple Paprika ↔ Skylight list pairs
with independent conflict resolution and state management per pair.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from .models import ListItem
from .paprika_client import PaprikaClient
from .skylight_client import SkylightClient
from .state_manager import StateManager
from .item_linker import ItemLinker
from .conflict_resolver import ConflictResolver, create_conflict_resolver_config
from .config import WhiskConfig, ListPairConfig

logger = logging.getLogger(__name__)


class ListPairSyncResult:
    """Result of syncing a single list pair"""

    def __init__(self, pair_config: ListPairConfig):
        self.pair_config = pair_config
        self.success = False
        self.error: Optional[str] = None
        self.changes_applied: Dict[str, List[str]] = {
            'paprika_created': [],
            'paprika_updated': [],
            'paprika_deleted': [],
            'skylight_created': [],
            'skylight_updated': [],
            'skylight_deleted': []
        }
        self.conflicts_resolved = 0
        self.items_processed = 0
        self.sync_duration = 0.0

    def add_change(self, category: str, item_name: str):
        """Add a change to the results"""
        if category in self.changes_applied:
            self.changes_applied[category].append(item_name)

    def get_total_changes(self) -> int:
        """Get total number of changes made"""
        return sum(len(changes) for changes in self.changes_applied.values())


class MultiListSyncResult:
    """Result of syncing all configured list pairs"""

    def __init__(self):
        self.success = False
        self.pair_results: List[ListPairSyncResult] = []
        self.total_pairs = 0
        self.successful_pairs = 0
        self.failed_pairs = 0
        self.total_changes = 0
        self.total_conflicts_resolved = 0
        self.sync_duration = 0.0
        self.errors: List[str] = []

    def add_pair_result(self, pair_result: ListPairSyncResult):
        """Add result from a list pair sync"""
        self.pair_results.append(pair_result)
        self.total_pairs += 1

        if pair_result.success:
            self.successful_pairs += 1
            self.total_changes += pair_result.get_total_changes()
            self.total_conflicts_resolved += pair_result.conflicts_resolved
        else:
            self.failed_pairs += 1
            if pair_result.error:
                self.errors.append(f"{pair_result.pair_config.paprika_list} ↔ {pair_result.pair_config.skylight_list}: {pair_result.error}")

        # Update overall success - true if at least one pair succeeded
        self.success = self.successful_pairs > 0


class WhiskSyncEngine:
    """
    Multi-list sync engine for Whisk

    Handles synchronization of multiple Paprika ↔ Skylight list pairs
    with independent conflict resolution and state management per pair.
    """

    def __init__(self, config: WhiskConfig, config_dir: Optional[Path] = None):
        """
        Initialize multi-list sync engine

        Args:
            config: Whisk configuration with list pairs and credentials
            config_dir: Directory for database and cache files
        """
        self.config = config
        self.config_dir = config_dir or Path.cwd()

        # Initialize API clients
        self._init_clients()

        # Initialize state manager with config directory
        db_path = self.config_dir / config.database_path
        self.state_manager = StateManager(str(db_path))

        logger.info(f"WhiskSyncEngine initialized with {len(config.list_pairs)} list pairs")

    def _init_clients(self):
        """Initialize Paprika and Skylight API clients"""
        # Initialize Paprika client with config directory for token cache
        paprika_token_cache = self.config_dir / self.config.paprika_token_cache
        self.paprika_client = PaprikaClient(
            email=self.config.paprika_email,
            password=self.config.paprika_password,
            token_cache_file=str(paprika_token_cache)
        )

        # Initialize Skylight client with config directory for token cache
        skylight_token_cache = self.config_dir / self.config.skylight_token_cache
        self.skylight_client = SkylightClient(
            email=self.config.skylight_email,
            password=self.config.skylight_password,
            frame_id=self.config.skylight_frame_id,
            token_cache_file=str(skylight_token_cache)
        )

    def sync_all_pairs(self, dry_run: bool = False) -> MultiListSyncResult:
        """
        Sync all configured list pairs

        Args:
            dry_run: If True, simulate changes without applying them

        Returns:
            MultiListSyncResult with results from all pairs
        """
        start_time = datetime.now()
        result = MultiListSyncResult()

        logger.info(f"Starting sync of {len(self.config.list_pairs)} list pairs (dry_run={dry_run})")

        # Authenticate clients upfront
        try:
            logger.debug("Authenticating with Paprika...")
            self.paprika_client.authenticate()
            logger.debug("Authenticating with Skylight...")
            self.skylight_client.authenticate()
        except Exception as e:
            logger.error(f"Failed to authenticate API clients: {e}")
            result.errors.append(f"Authentication failed: {e}")
            result.sync_duration = (datetime.now() - start_time).total_seconds()
            return result

        # Sync each list pair independently
        for i, pair in enumerate(self.config.list_pairs, 1):
            if not pair.enabled:
                logger.info(f"Skipping disabled pair {i}: {pair.paprika_list} ↔ {pair.skylight_list}")
                continue

            logger.info(f"Syncing pair {i}/{len(self.config.list_pairs)}: {pair.paprika_list} ↔ {pair.skylight_list}")

            pair_result = self._sync_single_pair(pair, dry_run)
            result.add_pair_result(pair_result)

        # Calculate final timing
        result.sync_duration = (datetime.now() - start_time).total_seconds()

        # Log summary
        if result.success:
            logger.info(f"✅ Sync completed: {result.successful_pairs}/{result.total_pairs} pairs successful, "
                       f"{result.total_changes} changes, {result.total_conflicts_resolved} conflicts resolved "
                       f"({result.sync_duration:.1f}s)")
        else:
            logger.error(f"❌ Sync failed: {result.failed_pairs}/{result.total_pairs} pairs failed")

        return result

    def sync_single_pair(self, paprika_list: str, skylight_list: str, dry_run: bool = False) -> ListPairSyncResult:
        """
        Sync a specific list pair

        Args:
            paprika_list: Name of Paprika list
            skylight_list: Name of Skylight list
            dry_run: If True, simulate changes without applying them

        Returns:
            ListPairSyncResult for this pair
        """
        # Find the list pair config
        pair = None
        for config_pair in self.config.list_pairs:
            if (config_pair.paprika_list == paprika_list and
                config_pair.skylight_list == skylight_list):
                pair = config_pair
                break

        if not pair:
            # Create a temporary pair config with default settings
            pair = ListPairConfig(
                paprika_list=paprika_list,
                skylight_list=skylight_list,
                enabled=True
            )

        # Authenticate clients
        try:
            self.paprika_client.authenticate()
            self.skylight_client.authenticate()
        except Exception as e:
            logger.error(f"Failed to authenticate for pair sync: {e}")
            result = ListPairSyncResult(pair)
            result.error = f"Authentication failed: {e}"
            return result

        return self._sync_single_pair(pair, dry_run)

    def _sync_single_pair(self, pair: ListPairConfig, dry_run: bool = False) -> ListPairSyncResult:
        """
        Internal method to sync a single list pair

        Args:
            pair: List pair configuration
            dry_run: If True, simulate changes without applying them

        Returns:
            ListPairSyncResult for this pair
        """
        start_time = datetime.now()
        result = ListPairSyncResult(pair)

        try:
            # Create pair-specific identifier for database isolation
            pair_id = f"{pair.paprika_list}___{pair.skylight_list}"

            # Create conflict resolver config for this pair
            resolver_config = create_conflict_resolver_config(
                timestamp_tolerance_seconds=self.config.timestamp_tolerance_seconds
            )

            # Create components for this pair
            item_linker_config = {
                'fuzzy_threshold': self.config.fuzzy_threshold,
                'case_sensitive': self.config.case_sensitive
            }
            item_linker = ItemLinker(
                state_manager=self.state_manager,
                config=item_linker_config
            )

            conflict_resolver = ConflictResolver(
                state_manager=self.state_manager,
                paprika_client=self.paprika_client,
                skylight_client=self.skylight_client,
                config=resolver_config
            )

            # CRITICAL: Capture pre-sync states BEFORE any API calls or database updates
            if not dry_run:
                logger.debug("Capturing pre-sync states for change detection...")
                conflict_resolver.capture_pre_sync_states()

            # Get current items from both services
            logger.debug(f"Fetching items from {pair.paprika_list} (Paprika)")
            paprika_items = self.paprika_client.get_grocery_list(pair.paprika_list)
            logger.debug(f"Fetched {len(paprika_items)} items from Paprika")

            logger.debug(f"Fetching items from {pair.skylight_list} (Skylight)")
            skylight_items = self.skylight_client.get_list_items(pair.skylight_list)
            logger.debug(f"Fetched {len(skylight_items)} items from Skylight")

            result.items_processed = len(paprika_items) + len(skylight_items)

            if not dry_run:
                # Store items in database for linking and change detection
                logger.debug("Storing items in database...")
                self._store_items_in_database(paprika_items, skylight_items, pair_id)

                # Link items using fuzzy matching
                logger.debug("Linking items between services...")
                item_linker.link_all_items()

                # Detect and apply all changes
                logger.debug("Detecting and applying changes...")
                changes = self._detect_and_apply_changes(
                    pair, paprika_items, skylight_items, conflict_resolver
                )

                # Update result with applied changes
                for change_type, item_names in changes.items():
                    result.changes_applied[change_type] = item_names

                result.conflicts_resolved = len(changes.get('conflicts_resolved', []))

            # Mark as successful
            result.success = True

        except Exception as e:
            logger.error(f"Failed to sync pair {pair.paprika_list} ↔ {pair.skylight_list}: {e}")
            result.error = str(e)
            result.success = False

        # Calculate timing
        result.sync_duration = (datetime.now() - start_time).total_seconds()

        return result

    def get_enabled_pairs(self) -> List[ListPairConfig]:
        """Get list of enabled list pairs"""
        return [pair for pair in self.config.list_pairs if pair.enabled]

    def get_pair_status(self) -> List[Dict[str, Any]]:
        """Get status information for all configured pairs"""
        status_list = []

        for pair in self.config.list_pairs:
            try:
                # Get basic info about the lists
                paprika_items = self.paprika_client.get_grocery_list(pair.paprika_list)
                skylight_items = self.skylight_client.get_list_items(pair.skylight_list)

                status = {
                    'paprika_list': pair.paprika_list,
                    'skylight_list': pair.skylight_list,
                    'enabled': pair.enabled,
                    'paprika_count': len(paprika_items),
                    'skylight_count': len(skylight_items),
                    'status': 'ready' if pair.enabled else 'disabled'
                }

            except Exception as e:
                status = {
                    'paprika_list': pair.paprika_list,
                    'skylight_list': pair.skylight_list,
                    'enabled': pair.enabled,
                    'status': 'error',
                    'error': str(e)
                }

            status_list.append(status)

        return status_list

    def _store_items_in_database(self, paprika_items: List[ListItem],
                                 skylight_items: List[ListItem],
                                 pair_id: str) -> None:
        """
        Store current items in database for linking and change detection

        Args:
            paprika_items: Current items from Paprika
            skylight_items: Current items from Skylight
            pair_id: Unique identifier for this list pair
        """
        try:
            # Store Paprika items
            for item in paprika_items:
                # The state manager expects the list_uid to be available
                list_uid = getattr(item, 'list_uid', pair_id.split('___')[0])
                self.state_manager.upsert_paprika_item(item, list_uid)

            # Store Skylight items
            for item in skylight_items:
                # The state manager expects the list_id to be available
                list_id = getattr(item, 'list_id', pair_id.split('___')[1])
                self.state_manager.upsert_skylight_item(item, list_id)

            logger.debug(f"Stored {len(paprika_items)} Paprika and {len(skylight_items)} Skylight items")

        except Exception as e:
            logger.error(f"Failed to store items in database: {e}")
            raise

    def _detect_and_apply_changes(self, pair: ListPairConfig,
                                  paprika_items: List[ListItem],
                                  skylight_items: List[ListItem],
                                  conflict_resolver) -> Dict[str, List[str]]:
        """
        Detect all types of changes and apply them

        Args:
            pair: List pair configuration
            paprika_items: Current Paprika items
            skylight_items: Current Skylight items
            conflict_resolver: Configured conflict resolver

        Returns:
            Dictionary of changes made, categorized by type
        """
        changes = {
            'paprika_created': [],
            'paprika_updated': [],
            'paprika_deleted': [],
            'skylight_created': [],
            'skylight_updated': [],
            'skylight_deleted': [],
            'conflicts_resolved': []
        }

        try:
            # 1. Handle conflicts first (items that exist in both but differ)
            logger.debug("Resolving conflicts...")
            conflict_resolutions = conflict_resolver.resolve_all_conflicts(
                paprika_list_name=pair.paprika_list,
                skylight_list_name=pair.skylight_list
            )

            for resolution in conflict_resolutions:
                changes['conflicts_resolved'].append(resolution.item_name)
                logger.info(f"Resolved conflict for '{resolution.item_name}': {resolution.winner}")

            # 2. Handle new items (exist in one service but not the other)
            self._handle_new_items(pair, changes)

            # 3. Handle deleted items (exist in database but missing from API)
            self._handle_deleted_items(pair, paprika_items, skylight_items, changes)

            # 4. Handle other updates (name changes, etc.)
            self._handle_item_updates(pair, changes)

            logger.info(f"Applied changes for {pair.paprika_list} ↔ {pair.skylight_list}: "
                       f"P+{len(changes['paprika_created'])} P~{len(changes['paprika_updated'])} P-{len(changes['paprika_deleted'])} "
                       f"S+{len(changes['skylight_created'])} S~{len(changes['skylight_updated'])} S-{len(changes['skylight_deleted'])} "
                       f"Conflicts:{len(changes['conflicts_resolved'])}")

        except Exception as e:
            logger.error(f"Failed to detect and apply changes: {e}")
            raise

        return changes

    def _handle_new_items(self, pair: ListPairConfig, changes: Dict[str, List[str]]) -> None:
        """Handle items that exist in one service but not the other"""
        try:
            # Get unlinked items (items that haven't been paired between services)
            unlinked_paprika = self.state_manager.get_unlinked_paprika_items()
            unlinked_skylight = self.state_manager.get_unlinked_skylight_items()

            # Create missing items in Skylight (from unlinked Paprika items)
            for p_item in unlinked_paprika:
                try:
                    skylight_id = self.skylight_client.add_item(
                        name=p_item.name,
                        checked=p_item.checked,
                        list_name=pair.skylight_list
                    )

                    # Create a new ListItem to store in database
                    from .models import ListItem
                    new_skylight_item = ListItem(
                        id=skylight_id,
                        name=p_item.name,
                        checked=p_item.checked
                    )

                    # Store the new Skylight item in database
                    s_db_item = self.state_manager.upsert_skylight_item(new_skylight_item, pair.skylight_list)

                    # Link the items
                    self.state_manager.create_item_link(p_item.id, s_db_item.id, confidence_score=1.0)

                    changes['skylight_created'].append(p_item.name)
                    logger.info(f"Created '{p_item.name}' in {pair.skylight_list}")

                except Exception as e:
                    logger.error(f"Failed to create '{p_item.name}' in Skylight: {e}")

            # Create missing items in Paprika (from unlinked Skylight items)
            for s_item in unlinked_skylight:
                try:
                    paprika_id = self.paprika_client.add_item(
                        name=s_item.name,
                        checked=s_item.checked,
                        list_name=pair.paprika_list
                    )

                    # Create a new ListItem to store in database
                    from .models import ListItem
                    new_paprika_item = ListItem(
                        id=paprika_id,
                        name=s_item.name,
                        checked=s_item.checked
                    )

                    # Store the new Paprika item in database
                    p_db_item = self.state_manager.upsert_paprika_item(new_paprika_item, pair.paprika_list)

                    # Link the items
                    self.state_manager.create_item_link(p_db_item.id, s_item.id, confidence_score=1.0)

                    changes['paprika_created'].append(s_item.name)
                    logger.info(f"Created '{s_item.name}' in {pair.paprika_list}")

                except Exception as e:
                    logger.error(f"Failed to create '{s_item.name}' in Paprika: {e}")

        except Exception as e:
            logger.error(f"Failed to handle new items: {e}")
            raise

    def _handle_deleted_items(self, pair: ListPairConfig,
                              paprika_items: List[ListItem],
                              skylight_items: List[ListItem],
                              changes: Dict[str, List[str]]) -> None:
        """Handle items that were deleted from one of the services"""
        # For now, we'll implement a simplified version that focuses on core functionality
        # This can be enhanced later to handle deletion detection more robustly
        try:
            logger.debug("Deletion handling is simplified in this version")
            # TODO: Implement robust deletion detection
            # This would require tracking which items existed in previous sync
            # and comparing with current state
        except Exception as e:
            logger.error(f"Failed to handle deleted items: {e}")
            raise

    def _handle_item_updates(self, pair: ListPairConfig, changes: Dict[str, List[str]]) -> None:
        """Handle other types of updates like name changes"""
        # This is a placeholder for handling name changes and other updates
        # For now, we focus on the core sync functionality
        # Future enhancement: detect name changes and update accordingly
        logger.debug("Item updates handling is placeholder in this version")