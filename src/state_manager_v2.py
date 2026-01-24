"""State management for grocery list sync using SQLite - Version 2 Architecture

This version implements the redesigned 3-table schema to handle:
- Duplicate item names properly
- Synthetic timestamp management for Paprika items
- Foreign key relationships between systems
- Comprehensive audit logging
"""

import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, NamedTuple
from dataclasses import dataclass

from models import GroceryItem

logger = logging.getLogger(__name__)


@dataclass
class PaprikaItem:
    """Paprika item with synthetic timestamp management"""
    id: Optional[int]
    paprika_id: str
    list_uid: str
    name: str
    checked: bool
    aisle: Optional[str] = None
    ingredient: Optional[str] = None
    # Synthetic timestamp management
    created_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_modified_at: Optional[datetime] = None
    # Sync state
    is_deleted: bool = False
    last_synced_at: Optional[datetime] = None


@dataclass
class SkylightItem:
    """Skylight item with real API timestamps"""
    id: Optional[int]
    skylight_id: str
    list_id: str
    name: str
    checked: bool
    # Real timestamps from API
    skylight_created_at: Optional[datetime] = None
    skylight_updated_at: Optional[datetime] = None
    # Sync state
    last_synced_at: Optional[datetime] = None


@dataclass
class ItemLink:
    """Link between Paprika and Skylight items"""
    id: Optional[int]
    paprika_item_id: int
    skylight_item_id: int
    linked_at: datetime
    confidence_score: float = 1.0
    paprika_item: Optional[PaprikaItem] = None
    skylight_item: Optional[SkylightItem] = None


@dataclass
class SyncLogEntry:
    """Audit log entry for sync operations"""
    id: Optional[int]
    operation: str  # 'CREATE', 'UPDATE', 'DELETE', 'CONFLICT', 'LINK'
    paprika_item_id: Optional[int]
    skylight_item_id: Optional[int]
    details: str  # JSON string
    created_at: datetime


class StateManagerV2:
    """Manages sync state using 3-table architecture with proper relationships"""

    def __init__(self, db_path: str = "sync_state_v2.db"):
        """
        Initialize StateManagerV2 with SQLite database

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize SQLite database with new 3-table schema"""
        try:
            logger.info(f"Initializing StateManagerV2 database at {self.db_path}")

            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Enable dict-like access
            self.conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints

            # Create tables
            self._create_paprika_items_table()
            self._create_skylight_items_table()
            self._create_item_links_table()
            self._create_sync_log_table()

            self.conn.commit()
            logger.info("StateManagerV2 database initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize StateManagerV2 database: {e}")
            raise

    def _create_paprika_items_table(self) -> None:
        """Create Paprika items table with synthetic timestamp management"""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS paprika_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paprika_id TEXT NOT NULL UNIQUE,
            list_uid TEXT NOT NULL,
            name TEXT NOT NULL,
            checked INTEGER DEFAULT 0,  -- purchased field from API
            aisle TEXT,
            ingredient TEXT,
            -- Synthetic timestamp management
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_modified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            -- Sync state
            is_deleted INTEGER DEFAULT 0,
            last_synced_at DATETIME
        );

        CREATE INDEX IF NOT EXISTS idx_paprika_id ON paprika_items(paprika_id);
        CREATE INDEX IF NOT EXISTS idx_paprika_list_uid ON paprika_items(list_uid);
        CREATE INDEX IF NOT EXISTS idx_paprika_name ON paprika_items(name);
        CREATE INDEX IF NOT EXISTS idx_paprika_deleted ON paprika_items(is_deleted);
        CREATE INDEX IF NOT EXISTS idx_paprika_last_modified ON paprika_items(last_modified_at);
        """
        self.conn.executescript(schema_sql)

    def _create_skylight_items_table(self) -> None:
        """Create Skylight items table with real API timestamps"""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS skylight_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skylight_id TEXT NOT NULL UNIQUE,
            list_id TEXT NOT NULL,
            name TEXT NOT NULL,
            checked INTEGER DEFAULT 0,
            -- Real timestamps from API
            skylight_created_at DATETIME,
            skylight_updated_at DATETIME,
            -- Sync state
            last_synced_at DATETIME
        );

        CREATE INDEX IF NOT EXISTS idx_skylight_id ON skylight_items(skylight_id);
        CREATE INDEX IF NOT EXISTS idx_skylight_list_id ON skylight_items(list_id);
        CREATE INDEX IF NOT EXISTS idx_skylight_name ON skylight_items(name);
        CREATE INDEX IF NOT EXISTS idx_skylight_updated ON skylight_items(skylight_updated_at);
        """
        self.conn.executescript(schema_sql)

    def _create_item_links_table(self) -> None:
        """Create foreign key relationships between items"""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS item_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paprika_item_id INTEGER NOT NULL REFERENCES paprika_items(id) ON DELETE CASCADE,
            skylight_item_id INTEGER NOT NULL REFERENCES skylight_items(id) ON DELETE CASCADE,
            linked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            confidence_score REAL DEFAULT 1.0,  -- For fuzzy name matching
            UNIQUE(paprika_item_id, skylight_item_id)
        );

        CREATE INDEX IF NOT EXISTS idx_links_paprika ON item_links(paprika_item_id);
        CREATE INDEX IF NOT EXISTS idx_links_skylight ON item_links(skylight_item_id);
        CREATE INDEX IF NOT EXISTS idx_links_confidence ON item_links(confidence_score);
        """
        self.conn.executescript(schema_sql)

    def _create_sync_log_table(self) -> None:
        """Create sync operations log for debugging"""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation TEXT NOT NULL,  -- 'CREATE', 'UPDATE', 'DELETE', 'CONFLICT', 'LINK'
            paprika_item_id INTEGER REFERENCES paprika_items(id),
            skylight_item_id INTEGER REFERENCES skylight_items(id),
            details TEXT,  -- JSON with before/after states
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_sync_log_operation ON sync_log(operation);
        CREATE INDEX IF NOT EXISTS idx_sync_log_created ON sync_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_sync_log_paprika ON sync_log(paprika_item_id);
        CREATE INDEX IF NOT EXISTS idx_sync_log_skylight ON sync_log(skylight_item_id);
        """
        self.conn.executescript(schema_sql)

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("StateManagerV2 database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # Paprika Items Operations
    def upsert_paprika_item(self, item: GroceryItem, list_uid: str) -> PaprikaItem:
        """
        Insert or update Paprika item with synthetic timestamp management

        Args:
            item: GroceryItem from Paprika API
            list_uid: Paprika list UID

        Returns:
            PaprikaItem with synthetic timestamps
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now(timezone.utc)

            # Check if item already exists
            cursor.execute("""
                SELECT * FROM paprika_items WHERE paprika_id = ?
            """, (item.paprika_id,))
            existing = cursor.fetchone()

            if existing:
                # Update existing item - check if changed
                changed = (
                    existing['checked'] != item.checked or
                    existing['name'] != item.name
                )

                last_modified_at = now if changed else existing['last_modified_at']

                cursor.execute("""
                    UPDATE paprika_items
                    SET name = ?, checked = ?, aisle = ?, ingredient = ?,
                        last_seen_at = ?, last_modified_at = ?, is_deleted = 0
                    WHERE paprika_id = ?
                """, (
                    item.name, item.checked, getattr(item, 'aisle', None),
                    item.name.lower(), now, last_modified_at, item.paprika_id
                ))

                paprika_item = PaprikaItem(
                    id=existing['id'],
                    paprika_id=item.paprika_id,
                    list_uid=list_uid,
                    name=item.name,
                    checked=item.checked,
                    aisle=getattr(item, 'aisle', None),
                    ingredient=item.name.lower(),
                    created_at=self._parse_datetime(existing['created_at']),
                    last_seen_at=now,
                    last_modified_at=last_modified_at,
                    is_deleted=False,
                    last_synced_at=self._parse_datetime(existing['last_synced_at'])
                )

                if changed:
                    self.log_sync_operation('UPDATE', paprika_item_id=existing['id'],
                                          details=f"Updated Paprika item: {item.name}")

            else:
                # Insert new item
                cursor.execute("""
                    INSERT INTO paprika_items
                    (paprika_id, list_uid, name, checked, aisle, ingredient,
                     created_at, last_seen_at, last_modified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.paprika_id, list_uid, item.name, item.checked,
                    getattr(item, 'aisle', None), item.name.lower(),
                    now, now, now
                ))

                paprika_item = PaprikaItem(
                    id=cursor.lastrowid,
                    paprika_id=item.paprika_id,
                    list_uid=list_uid,
                    name=item.name,
                    checked=item.checked,
                    aisle=getattr(item, 'aisle', None),
                    ingredient=item.name.lower(),
                    created_at=now,
                    last_seen_at=now,
                    last_modified_at=now,
                    is_deleted=False,
                    last_synced_at=None
                )

                self.log_sync_operation('CREATE', paprika_item_id=paprika_item.id,
                                      details=f"Created Paprika item: {item.name}")

            self.conn.commit()
            return paprika_item

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to upsert Paprika item: {e}")
            raise

    def upsert_skylight_item(self, item: GroceryItem, list_id: str) -> SkylightItem:
        """
        Insert or update Skylight item with real API timestamps

        Args:
            item: GroceryItem from Skylight API
            list_id: Skylight list ID

        Returns:
            SkylightItem with real timestamps
        """
        try:
            cursor = self.conn.cursor()

            # Check if item already exists
            cursor.execute("""
                SELECT * FROM skylight_items WHERE skylight_id = ?
            """, (item.skylight_id,))
            existing = cursor.fetchone()

            if existing:
                # Update existing item
                cursor.execute("""
                    UPDATE skylight_items
                    SET name = ?, checked = ?, skylight_created_at = ?,
                        skylight_updated_at = ?
                    WHERE skylight_id = ?
                """, (
                    item.name, item.checked, item.skylight_timestamp,
                    item.skylight_timestamp, item.skylight_id
                ))

                skylight_item = SkylightItem(
                    id=existing['id'],
                    skylight_id=item.skylight_id,
                    list_id=list_id,
                    name=item.name,
                    checked=item.checked,
                    skylight_created_at=item.skylight_timestamp,
                    skylight_updated_at=item.skylight_timestamp,
                    last_synced_at=self._parse_datetime(existing['last_synced_at'])
                )

                self.log_sync_operation('UPDATE', skylight_item_id=existing['id'],
                                      details=f"Updated Skylight item: {item.name}")

            else:
                # Insert new item
                cursor.execute("""
                    INSERT INTO skylight_items
                    (skylight_id, list_id, name, checked, skylight_created_at, skylight_updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item.skylight_id, list_id, item.name, item.checked,
                    item.skylight_timestamp, item.skylight_timestamp
                ))

                skylight_item = SkylightItem(
                    id=cursor.lastrowid,
                    skylight_id=item.skylight_id,
                    list_id=list_id,
                    name=item.name,
                    checked=item.checked,
                    skylight_created_at=item.skylight_timestamp,
                    skylight_updated_at=item.skylight_timestamp,
                    last_synced_at=None
                )

                self.log_sync_operation('CREATE', skylight_item_id=skylight_item.id,
                                      details=f"Created Skylight item: {item.name}")

            self.conn.commit()
            return skylight_item

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to upsert Skylight item: {e}")
            raise

    def mark_unseen_paprika_items_as_deleted(self, cutoff_time: datetime = None) -> int:
        """
        Mark Paprika items not seen recently as potentially deleted

        Args:
            cutoff_time: Items not seen after this time are marked deleted
                        (default: 1 minute ago)
        Returns:
            Number of items marked as deleted
        """
        if cutoff_time is None:
            cutoff_time = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE paprika_items
                SET is_deleted = 1
                WHERE last_seen_at < ? AND is_deleted = 0
            """, (cutoff_time,))

            deleted_count = cursor.rowcount
            self.conn.commit()

            if deleted_count > 0:
                logger.info(f"Marked {deleted_count} Paprika items as deleted (not seen since {cutoff_time})")

            return deleted_count

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to mark unseen Paprika items: {e}")
            raise

    def get_unlinked_paprika_items(self) -> List[PaprikaItem]:
        """Get Paprika items that are not linked to any Skylight items"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT p.* FROM paprika_items p
                LEFT JOIN item_links l ON p.id = l.paprika_item_id
                WHERE l.paprika_item_id IS NULL AND p.is_deleted = 0
            """)

            items = []
            for row in cursor.fetchall():
                items.append(self._row_to_paprika_item(row))

            return items

        except Exception as e:
            logger.error(f"Failed to get unlinked Paprika items: {e}")
            raise

    def get_unlinked_skylight_items(self) -> List[SkylightItem]:
        """Get Skylight items that are not linked to any Paprika items"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT s.* FROM skylight_items s
                LEFT JOIN item_links l ON s.id = l.skylight_item_id
                WHERE l.skylight_item_id IS NULL
            """)

            items = []
            for row in cursor.fetchall():
                items.append(self._row_to_skylight_item(row))

            return items

        except Exception as e:
            logger.error(f"Failed to get unlinked Skylight items: {e}")
            raise

    def create_item_link(self, paprika_item_id: int, skylight_item_id: int,
                        confidence_score: float = 1.0) -> ItemLink:
        """
        Create a link between Paprika and Skylight items

        Args:
            paprika_item_id: ID of Paprika item
            skylight_item_id: ID of Skylight item
            confidence_score: Confidence in the match (0.0-1.0)

        Returns:
            Created ItemLink
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now(timezone.utc)

            cursor.execute("""
                INSERT INTO item_links (paprika_item_id, skylight_item_id, linked_at, confidence_score)
                VALUES (?, ?, ?, ?)
            """, (paprika_item_id, skylight_item_id, now, confidence_score))

            link = ItemLink(
                id=cursor.lastrowid,
                paprika_item_id=paprika_item_id,
                skylight_item_id=skylight_item_id,
                linked_at=now,
                confidence_score=confidence_score
            )

            self.conn.commit()

            self.log_sync_operation('LINK', paprika_item_id=paprika_item_id,
                                  skylight_item_id=skylight_item_id,
                                  details=f"Linked items with confidence {confidence_score}")

            return link

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to create item link: {e}")
            raise

    def get_linked_items_with_conflicts(self) -> List[ItemLink]:
        """Get linked items where Paprika and Skylight have different checked states"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT l.*,
                       p.name as p_name, p.checked as p_checked, p.last_modified_at as p_modified,
                       p.paprika_id as p_paprika_id, p.list_uid as p_list_uid,
                       s.name as s_name, s.checked as s_checked, s.skylight_updated_at as s_updated,
                       s.skylight_id as s_skylight_id, s.list_id as s_list_id
                FROM item_links l
                JOIN paprika_items p ON l.paprika_item_id = p.id
                JOIN skylight_items s ON l.skylight_item_id = s.id
                WHERE p.checked != s.checked AND p.is_deleted = 0
            """)

            links = []
            for row in cursor.fetchall():
                link = ItemLink(
                    id=row['id'],
                    paprika_item_id=row['paprika_item_id'],
                    skylight_item_id=row['skylight_item_id'],
                    linked_at=self._parse_datetime(row['linked_at']),
                    confidence_score=row['confidence_score']
                )

                # Attach item details for conflict resolution
                link.paprika_item = PaprikaItem(
                    id=row['paprika_item_id'],
                    paprika_id=row['p_paprika_id'],  # Use actual paprika_id from DB
                    list_uid=row['p_list_uid'],      # Use actual list_uid from DB
                    name=row['p_name'],
                    checked=bool(row['p_checked']),
                    last_modified_at=self._parse_datetime(row['p_modified'])
                )

                link.skylight_item = SkylightItem(
                    id=row['skylight_item_id'],
                    skylight_id=row['s_skylight_id'], # Use actual skylight_id from DB
                    list_id=row['s_list_id'],         # Use actual list_id from DB
                    name=row['s_name'],
                    checked=bool(row['s_checked']),
                    skylight_updated_at=self._parse_datetime(row['s_updated'])
                )

                links.append(link)

            return links

        except Exception as e:
            logger.error(f"Failed to get linked items with conflicts: {e}")
            raise

    def log_sync_operation(self, operation: str, paprika_item_id: int = None,
                          skylight_item_id: int = None, details: str = "") -> None:
        """
        Log a sync operation for debugging and audit trail

        Args:
            operation: Type of operation ('CREATE', 'UPDATE', 'DELETE', 'CONFLICT', 'LINK')
            paprika_item_id: Optional Paprika item ID
            skylight_item_id: Optional Skylight item ID
            details: Additional details about the operation
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now(timezone.utc)

            cursor.execute("""
                INSERT INTO sync_log (operation, paprika_item_id, skylight_item_id, details, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (operation, paprika_item_id, skylight_item_id, details, now))

            self.conn.commit()
            logger.debug(f"Logged sync operation: {operation} - {details}")

        except Exception as e:
            logger.error(f"Failed to log sync operation: {e}")
            # Don't raise - logging failures shouldn't break sync

    # Utility methods
    def _parse_datetime(self, dt_str) -> Optional[datetime]:
        """Parse datetime string to datetime object"""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except:
            return None

    def _row_to_paprika_item(self, row) -> PaprikaItem:
        """Convert database row to PaprikaItem"""
        return PaprikaItem(
            id=row['id'],
            paprika_id=row['paprika_id'],
            list_uid=row['list_uid'],
            name=row['name'],
            checked=bool(row['checked']),
            aisle=row['aisle'],
            ingredient=row['ingredient'],
            created_at=self._parse_datetime(row['created_at']),
            last_seen_at=self._parse_datetime(row['last_seen_at']),
            last_modified_at=self._parse_datetime(row['last_modified_at']),
            is_deleted=bool(row['is_deleted']),
            last_synced_at=self._parse_datetime(row['last_synced_at'])
        )

    def _row_to_skylight_item(self, row) -> SkylightItem:
        """Convert database row to SkylightItem"""
        return SkylightItem(
            id=row['id'],
            skylight_id=row['skylight_id'],
            list_id=row['list_id'],
            name=row['name'],
            checked=bool(row['checked']),
            skylight_created_at=self._parse_datetime(row['skylight_created_at']),
            skylight_updated_at=self._parse_datetime(row['skylight_updated_at']),
            last_synced_at=self._parse_datetime(row['last_synced_at'])
        )

    def get_sync_statistics(self) -> Dict[str, Any]:
        """Get statistics about the sync state"""
        try:
            cursor = self.conn.cursor()

            # Get counts
            cursor.execute("SELECT COUNT(*) FROM paprika_items WHERE is_deleted = 0")
            paprika_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM skylight_items")
            skylight_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM item_links")
            linked_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM paprika_items WHERE is_deleted = 1")
            deleted_count = cursor.fetchone()[0]

            # Get recent sync activity
            cursor.execute("""
                SELECT operation, COUNT(*) as count
                FROM sync_log
                WHERE created_at > datetime('now', '-1 hour')
                GROUP BY operation
            """)
            recent_ops = dict(cursor.fetchall())

            return {
                'paprika_items': paprika_count,
                'skylight_items': skylight_count,
                'linked_items': linked_count,
                'deleted_items': deleted_count,
                'unlinked_paprika': paprika_count - linked_count,
                'unlinked_skylight': skylight_count - linked_count,
                'recent_operations': recent_ops,
                'database_path': str(self.db_path)
            }

        except Exception as e:
            logger.error(f"Failed to get sync statistics: {e}")
            return {'error': str(e)}