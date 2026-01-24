"""State management for grocery list sync using SQLite"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from models import GroceryItem

logger = logging.getLogger(__name__)


class StateManager:
    """Manages sync state tracking using SQLite database"""

    def __init__(self, db_path: str = "sync_state.db"):
        """
        Initialize StateManager with SQLite database

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize SQLite database with schema"""
        try:
            logger.info(f"Initializing database at {self.db_path}")

            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Enable dict-like access to rows

            # Create schema
            schema_sql = """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                paprika_id TEXT,
                paprika_list_uid TEXT,
                skylight_id TEXT,
                skylight_list_id TEXT,
                checked INTEGER DEFAULT 0,  -- 0=unchecked, 1=checked
                deleted INTEGER DEFAULT 0,  -- 0=active, 1=deleted
                paprika_timestamp TEXT,     -- ISO 8601 format
                skylight_timestamp TEXT,    -- ISO 8601 format
                last_synced_at TEXT,        -- ISO 8601 format
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(item_name, paprika_list_uid, skylight_list_id)
            );

            CREATE INDEX IF NOT EXISTS idx_item_name ON items(item_name);
            CREATE INDEX IF NOT EXISTS idx_paprika_id ON items(paprika_id);
            CREATE INDEX IF NOT EXISTS idx_skylight_id ON items(skylight_id);
            CREATE INDEX IF NOT EXISTS idx_deleted ON items(deleted);
            CREATE INDEX IF NOT EXISTS idx_last_synced ON items(last_synced_at);

            -- Trigger to update updated_at timestamp
            CREATE TRIGGER IF NOT EXISTS update_items_timestamp
                AFTER UPDATE ON items
                FOR EACH ROW
            BEGIN
                UPDATE items SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;
            """

            self.conn.executescript(schema_sql)
            self.conn.commit()

            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _datetime_to_iso(self, dt: Optional[datetime]) -> Optional[str]:
        """Convert datetime to ISO 8601 string"""
        if dt is None:
            return None
        return dt.isoformat()

    def _iso_to_datetime(self, iso_str: Optional[str]) -> Optional[datetime]:
        """Convert ISO 8601 string to datetime"""
        if not iso_str:
            return None
        try:
            return datetime.fromisoformat(iso_str)
        except Exception as e:
            logger.warning(f"Failed to parse datetime '{iso_str}': {e}")
            return None

    def add_or_update_item(
        self,
        item: GroceryItem,
        paprika_list_uid: Optional[str] = None,
        skylight_list_id: Optional[str] = None
    ) -> int:
        """
        Add or update item in state tracking

        Args:
            item: GroceryItem to track
            paprika_list_uid: Paprika list UID (if item exists in Paprika)
            skylight_list_id: Skylight list ID (if item exists in Skylight)

        Returns:
            Database row ID of the item
        """
        try:
            cursor = self.conn.cursor()

            # Check if item already exists (by name and list combination)
            cursor.execute("""
                SELECT id FROM items
                WHERE item_name = ?
                AND (paprika_list_uid = ? OR paprika_list_uid IS NULL)
                AND (skylight_list_id = ? OR skylight_list_id IS NULL)
                AND deleted = 0
            """, (item.name, paprika_list_uid, skylight_list_id))

            existing = cursor.fetchone()

            if existing:
                # Update existing item
                cursor.execute("""
                    UPDATE items SET
                        paprika_id = COALESCE(?, paprika_id),
                        paprika_list_uid = COALESCE(?, paprika_list_uid),
                        skylight_id = COALESCE(?, skylight_id),
                        skylight_list_id = COALESCE(?, skylight_list_id),
                        checked = ?,
                        paprika_timestamp = ?,
                        skylight_timestamp = ?
                    WHERE id = ?
                """, (
                    item.paprika_id,
                    paprika_list_uid,
                    item.skylight_id,
                    skylight_list_id,
                    1 if item.checked else 0,
                    self._datetime_to_iso(item.paprika_timestamp),
                    self._datetime_to_iso(item.skylight_timestamp),
                    existing['id']
                ))

                self.conn.commit()
                logger.debug(f"Updated item: {item.name}")
                return existing['id']

            else:
                # Insert new item
                cursor.execute("""
                    INSERT INTO items (
                        item_name, paprika_id, paprika_list_uid, skylight_id, skylight_list_id,
                        checked, paprika_timestamp, skylight_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.name,
                    item.paprika_id,
                    paprika_list_uid,
                    item.skylight_id,
                    skylight_list_id,
                    1 if item.checked else 0,
                    self._datetime_to_iso(item.paprika_timestamp),
                    self._datetime_to_iso(item.skylight_timestamp)
                ))

                self.conn.commit()
                item_id = cursor.lastrowid
                logger.debug(f"Added new item: {item.name} (id={item_id})")
                return item_id

        except Exception as e:
            logger.error(f"Failed to add/update item {item.name}: {e}")
            raise

    def get_item_by_ids(
        self,
        paprika_id: Optional[str] = None,
        skylight_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get item by Paprika or Skylight ID

        Args:
            paprika_id: Paprika UID to search for
            skylight_id: Skylight ID to search for

        Returns:
            Dictionary with item data or None if not found
        """
        if not paprika_id and not skylight_id:
            return None

        try:
            cursor = self.conn.cursor()

            if paprika_id:
                cursor.execute("SELECT * FROM items WHERE paprika_id = ? AND deleted = 0", (paprika_id,))
            else:
                cursor.execute("SELECT * FROM items WHERE skylight_id = ? AND deleted = 0", (skylight_id,))

            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get item by IDs: {e}")
            raise

    def mark_item_deleted(self, item_id: int) -> None:
        """
        Mark item as deleted in state tracking

        Args:
            item_id: Database row ID of item to mark as deleted
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE items SET deleted = 1 WHERE id = ?", (item_id,))
            self.conn.commit()
            logger.debug(f"Marked item {item_id} as deleted")

        except Exception as e:
            logger.error(f"Failed to mark item {item_id} as deleted: {e}")
            raise

    def get_all_active_items(self) -> List[Dict[str, Any]]:
        """
        Get all active (non-deleted) items from state tracking

        Returns:
            List of dictionaries with item data
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM items WHERE deleted = 0 ORDER BY item_name")
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get active items: {e}")
            raise

    def detect_changes(
        self,
        paprika_items: List[GroceryItem],
        skylight_items: List[GroceryItem],
        paprika_list_uid: str,
        skylight_list_id: str
    ) -> Dict[str, List[GroceryItem]]:
        """
        Detect changes between current state and last known state

        Args:
            paprika_items: Current items from Paprika
            skylight_items: Current items from Skylight
            paprika_list_uid: Paprika list UID being synced
            skylight_list_id: Skylight list ID being synced

        Returns:
            Dictionary with change categories:
            {
                'paprika_added': [...],
                'paprika_modified': [...],
                'paprika_deleted': [...],
                'skylight_added': [...],
                'skylight_modified': [...],
                'skylight_deleted': [...],
                'conflicts': [...]
            }
        """
        try:
            logger.info("Detecting changes between current and last known state")

            changes = {
                'paprika_added': [],
                'paprika_modified': [],
                'paprika_deleted': [],
                'skylight_added': [],
                'skylight_modified': [],
                'skylight_deleted': [],
                'conflicts': []
            }

            # Get current database state
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM items
                WHERE paprika_list_uid = ? OR skylight_list_id = ?
                ORDER BY item_name
            """, (paprika_list_uid, skylight_list_id))

            db_items = {row['item_name']: dict(row) for row in cursor.fetchall()}

            # Create lookup dictionaries for current items
            paprika_lookup = {item.name: item for item in paprika_items}
            skylight_lookup = {item.name: item for item in skylight_items}

            # Check Paprika items for additions and modifications
            for item in paprika_items:
                db_item = db_items.get(item.name)

                if not db_item:
                    # New item in Paprika
                    changes['paprika_added'].append(item)
                else:
                    # Check for modifications
                    db_timestamp = self._iso_to_datetime(db_item.get('paprika_timestamp'))
                    if item.paprika_timestamp and db_timestamp:
                        if item.paprika_timestamp > db_timestamp:
                            changes['paprika_modified'].append(item)

            # Check Skylight items for additions and modifications
            for item in skylight_items:
                db_item = db_items.get(item.name)

                if not db_item:
                    # New item in Skylight
                    changes['skylight_added'].append(item)
                else:
                    # Check for modifications
                    db_timestamp = self._iso_to_datetime(db_item.get('skylight_timestamp'))
                    if item.skylight_timestamp and db_timestamp:
                        if item.skylight_timestamp > db_timestamp:
                            changes['skylight_modified'].append(item)

            # Check for deletions
            for name, db_item in db_items.items():
                if db_item['deleted']:
                    continue  # Already marked as deleted

                paprika_missing = name not in paprika_lookup and db_item['paprika_id']
                skylight_missing = name not in skylight_lookup and db_item['skylight_id']

                if paprika_missing:
                    # Item was deleted from Paprika
                    deleted_item = GroceryItem(
                        name=name,
                        paprika_id=db_item['paprika_id'],
                        skylight_id=db_item['skylight_id']
                    )
                    changes['paprika_deleted'].append(deleted_item)

                if skylight_missing:
                    # Item was deleted from Skylight
                    deleted_item = GroceryItem(
                        name=name,
                        paprika_id=db_item['paprika_id'],
                        skylight_id=db_item['skylight_id']
                    )
                    changes['skylight_deleted'].append(deleted_item)

            # Check for conflicts (item modified in both systems since last sync)
            for name in set(paprika_lookup.keys()) & set(skylight_lookup.keys()):
                db_item = db_items.get(name)
                if not db_item:
                    continue

                paprika_item = paprika_lookup[name]
                skylight_item = skylight_lookup[name]

                # Check if both have been modified since last sync
                last_synced = self._iso_to_datetime(db_item.get('last_synced_at'))
                paprika_modified = (paprika_item.paprika_timestamp and last_synced and
                                  paprika_item.paprika_timestamp > last_synced)
                skylight_modified = (skylight_item.skylight_timestamp and last_synced and
                                   skylight_item.skylight_timestamp > last_synced)

                if paprika_modified and skylight_modified:
                    # Conflict detected
                    conflict_item = GroceryItem(
                        name=name,
                        checked=paprika_item.checked,  # Will be resolved by timestamp
                        paprika_id=paprika_item.paprika_id,
                        skylight_id=skylight_item.skylight_id,
                        paprika_timestamp=paprika_item.paprika_timestamp,
                        skylight_timestamp=skylight_item.skylight_timestamp
                    )
                    changes['conflicts'].append(conflict_item)

            # Log summary
            logger.info(f"Change detection complete:")
            for category, items in changes.items():
                if items:
                    logger.info(f"  {category}: {len(items)} items")

            return changes

        except Exception as e:
            logger.error(f"Failed to detect changes: {e}")
            raise

    def mark_sync_complete(self, item_names: List[str], sync_timestamp: Optional[datetime] = None) -> None:
        """
        Mark items as successfully synced

        Args:
            item_names: Names of items that were synced
            sync_timestamp: Timestamp of sync completion (defaults to now)
        """
        if not item_names:
            return

        try:
            if sync_timestamp is None:
                sync_timestamp = datetime.now(timezone.utc)

            cursor = self.conn.cursor()
            sync_iso = self._datetime_to_iso(sync_timestamp)

            placeholders = ','.join('?' for _ in item_names)
            cursor.execute(f"""
                UPDATE items
                SET last_synced_at = ?
                WHERE item_name IN ({placeholders}) AND deleted = 0
            """, [sync_iso] + item_names)

            self.conn.commit()
            logger.info(f"Marked {len(item_names)} items as synced at {sync_iso}")

        except Exception as e:
            logger.error(f"Failed to mark sync complete: {e}")
            raise

    def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about sync state

        Returns:
            Dictionary with sync statistics
        """
        try:
            cursor = self.conn.cursor()

            # Total items
            cursor.execute("SELECT COUNT(*) as total FROM items WHERE deleted = 0")
            total = cursor.fetchone()['total']

            # Items with both IDs (fully synced)
            cursor.execute("""
                SELECT COUNT(*) as synced FROM items
                WHERE deleted = 0 AND paprika_id IS NOT NULL AND skylight_id IS NOT NULL
            """)
            synced = cursor.fetchone()['synced']

            # Items only in Paprika
            cursor.execute("""
                SELECT COUNT(*) as paprika_only FROM items
                WHERE deleted = 0 AND paprika_id IS NOT NULL AND skylight_id IS NULL
            """)
            paprika_only = cursor.fetchone()['paprika_only']

            # Items only in Skylight
            cursor.execute("""
                SELECT COUNT(*) as skylight_only FROM items
                WHERE deleted = 0 AND paprika_id IS NULL AND skylight_id IS NOT NULL
            """)
            skylight_only = cursor.fetchone()['skylight_only']

            # Recently synced (last 24 hours)
            cursor.execute("""
                SELECT COUNT(*) as recent FROM items
                WHERE deleted = 0 AND last_synced_at > datetime('now', '-24 hours')
            """)
            recent = cursor.fetchone()['recent']

            return {
                'total_items': total,
                'fully_synced': synced,
                'paprika_only': paprika_only,
                'skylight_only': skylight_only,
                'recently_synced': recent,
                'sync_coverage': round(synced / total * 100, 1) if total > 0 else 0
            }

        except Exception as e:
            logger.error(f"Failed to get sync statistics: {e}")
            raise