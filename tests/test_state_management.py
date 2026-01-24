#!/usr/bin/env python3
"""
Test suite for StateManager - State Management System

This test suite verifies all aspects of the state management system including:
- Database initialization and schema
- Item tracking and change detection
- Conflict detection and resolution
- Sync state management
"""

import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_manager import StateManager
from models import GroceryItem


def create_test_item(name: str, checked: bool = False, paprika_id: str = None, skylight_id: str = None,
                    paprika_timestamp: datetime = None, skylight_timestamp: datetime = None) -> GroceryItem:
    """Helper to create test grocery items"""
    return GroceryItem(
        name=name,
        checked=checked,
        paprika_id=paprika_id,
        skylight_id=skylight_id,
        paprika_timestamp=paprika_timestamp or datetime.now(timezone.utc),
        skylight_timestamp=skylight_timestamp or datetime.now(timezone.utc)
    )


def test_database_initialization():
    """Test database initialization and schema creation"""
    print("🧪 Testing database initialization...")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        # Initialize state manager
        with StateManager(db_path) as sm:
            # Verify database file was created
            assert Path(db_path).exists(), "Database file not created"

            # Verify schema by checking table exists
            cursor = sm.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            table_exists = cursor.fetchone() is not None
            assert table_exists, "Items table not created"

            # Verify indexes exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row[0] for row in cursor.fetchall()]
            expected_indexes = ['idx_item_name', 'idx_paprika_id', 'idx_skylight_id', 'idx_deleted', 'idx_last_synced']

            for expected in expected_indexes:
                assert expected in indexes, f"Index {expected} not created"

        print("   ✅ Database initialization successful")
        return True

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


def test_item_tracking():
    """Test adding and updating items in state tracking"""
    print("🧪 Testing item tracking...")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        with StateManager(db_path) as sm:
            # Test adding new item
            item1 = create_test_item("Milk", checked=False, paprika_id="paprika_123")
            item_id = sm.add_or_update_item(item1, paprika_list_uid="list_1")

            assert item_id > 0, "Item ID should be positive"

            # Verify item was added
            db_item = sm.get_item_by_ids(paprika_id="paprika_123")
            assert db_item is not None, "Item not found in database"
            assert db_item['item_name'] == "Milk", "Item name mismatch"
            assert db_item['checked'] == 0, "Item should be unchecked"

            # Test updating existing item
            item1.skylight_id = "skylight_456"
            item1.checked = True
            sm.add_or_update_item(item1, paprika_list_uid="list_1", skylight_list_id="list_2")

            # Verify update
            db_item = sm.get_item_by_ids(paprika_id="paprika_123")
            assert db_item['skylight_id'] == "skylight_456", "Skylight ID not updated"
            assert db_item['checked'] == 1, "Checked status not updated"

        print("   ✅ Item tracking successful")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_change_detection():
    """Test change detection between current and last known state"""
    print("🧪 Testing change detection...")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        with StateManager(db_path) as sm:
            now = datetime.now(timezone.utc)
            hour_ago = now - timedelta(hours=1)
            two_hours_ago = now - timedelta(hours=2)

            # Set up initial state (what was synced before)
            milk_item = create_test_item("Milk", paprika_id="p1", skylight_id="s1",
                                       paprika_timestamp=two_hours_ago, skylight_timestamp=two_hours_ago)
            bread_item = create_test_item("Bread", paprika_id="p2", skylight_id="s2",
                                        paprika_timestamp=two_hours_ago, skylight_timestamp=two_hours_ago)

            sm.add_or_update_item(milk_item, "plist1", "slist1")
            sm.add_or_update_item(bread_item, "plist1", "slist1")

            # Mark as synced
            sm.mark_sync_complete(["Milk", "Bread"], two_hours_ago)

            # Simulate current state with changes
            current_paprika = [
                create_test_item("Milk", checked=True, paprika_id="p1",
                               paprika_timestamp=hour_ago),  # Modified
                create_test_item("Eggs", paprika_id="p3",
                               paprika_timestamp=now),  # Added
                # Bread missing (deleted)
            ]

            current_skylight = [
                create_test_item("Milk", checked=False, skylight_id="s1",
                                skylight_timestamp=now),  # Modified (conflict!)
                create_test_item("Bread", skylight_id="s2",
                                skylight_timestamp=two_hours_ago),  # Unchanged
                create_test_item("Cheese", skylight_id="s4",
                               skylight_timestamp=now),  # Added
            ]

            # Detect changes
            changes = sm.detect_changes(current_paprika, current_skylight, "plist1", "slist1")

            # Verify additions
            assert len(changes['paprika_added']) == 1, f"Expected 1 Paprika addition, got {len(changes['paprika_added'])}"
            assert changes['paprika_added'][0].name == "Eggs", "Eggs should be added to Paprika"

            assert len(changes['skylight_added']) == 1, f"Expected 1 Skylight addition, got {len(changes['skylight_added'])}"
            assert changes['skylight_added'][0].name == "Cheese", "Cheese should be added to Skylight"

            # Verify modifications
            assert len(changes['paprika_modified']) == 1, "Should detect Milk modification in Paprika"
            assert changes['paprika_modified'][0].name == "Milk", "Milk should be modified in Paprika"

            # Verify conflicts (Milk modified in both systems)
            assert len(changes['conflicts']) == 1, "Should detect conflict for Milk"
            assert changes['conflicts'][0].name == "Milk", "Milk should be in conflicts"

            # Verify deletions
            assert len(changes['paprika_deleted']) == 1, "Should detect Bread deletion from Paprika"
            assert changes['paprika_deleted'][0].name == "Bread", "Bread should be deleted from Paprika"

        print("   ✅ Change detection successful")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_sync_statistics():
    """Test sync statistics and reporting"""
    print("🧪 Testing sync statistics...")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        with StateManager(db_path) as sm:
            # Add test items with different sync states
            items = [
                (create_test_item("Fully Synced", paprika_id="p1", skylight_id="s1"), "plist", "slist"),
                (create_test_item("Paprika Only", paprika_id="p2"), "plist", None),
                (create_test_item("Skylight Only", skylight_id="s3"), None, "slist"),
            ]

            for item, p_list, s_list in items:
                sm.add_or_update_item(item, p_list, s_list)

            # Get statistics
            stats = sm.get_sync_statistics()

            assert stats['total_items'] == 3, f"Expected 3 total items, got {stats['total_items']}"
            assert stats['fully_synced'] == 1, f"Expected 1 fully synced item, got {stats['fully_synced']}"
            assert stats['paprika_only'] == 1, f"Expected 1 Paprika-only item, got {stats['paprika_only']}"
            assert stats['skylight_only'] == 1, f"Expected 1 Skylight-only item, got {stats['skylight_only']}"
            assert stats['sync_coverage'] == 33.3, f"Expected 33.3% coverage, got {stats['sync_coverage']}"

        print("   ✅ Sync statistics successful")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_deletion_tracking():
    """Test marking and tracking deleted items"""
    print("🧪 Testing deletion tracking...")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        with StateManager(db_path) as sm:
            # Add item
            item = create_test_item("To Be Deleted", paprika_id="p1", skylight_id="s1")
            item_id = sm.add_or_update_item(item, "plist", "slist")

            # Verify item exists
            all_items = sm.get_all_active_items()
            assert len(all_items) == 1, "Should have 1 active item"

            # Mark as deleted
            sm.mark_item_deleted(item_id)

            # Verify item is no longer active
            active_items = sm.get_all_active_items()
            assert len(active_items) == 0, "Should have 0 active items after deletion"

            # But still exists in database with deleted flag
            cursor = sm.conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM items WHERE deleted = 1")
            deleted_count = cursor.fetchone()['total']
            assert deleted_count == 1, "Should have 1 deleted item"

        print("   ✅ Deletion tracking successful")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_concurrent_modifications():
    """Test handling of concurrent modifications (conflicts)"""
    print("🧪 Testing concurrent modification handling...")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        with StateManager(db_path) as sm:
            now = datetime.now(timezone.utc)
            sync_time = now - timedelta(hours=2)
            paprika_mod_time = now - timedelta(minutes=30)
            skylight_mod_time = now - timedelta(minutes=15)  # More recent

            # Initial synced state
            item = create_test_item("Conflicted Item", paprika_id="p1", skylight_id="s1",
                                  paprika_timestamp=sync_time, skylight_timestamp=sync_time)
            sm.add_or_update_item(item, "plist", "slist")
            sm.mark_sync_complete(["Conflicted Item"], sync_time)

            # Current state with modifications on both sides
            paprika_current = [create_test_item("Conflicted Item", checked=True, paprika_id="p1",
                                              paprika_timestamp=paprika_mod_time)]
            skylight_current = [create_test_item("Conflicted Item", checked=False, skylight_id="s1",
                                               skylight_timestamp=skylight_mod_time)]

            # Detect changes
            changes = sm.detect_changes(paprika_current, skylight_current, "plist", "slist")

            # Should detect conflict
            assert len(changes['conflicts']) == 1, "Should detect 1 conflict"
            conflict = changes['conflicts'][0]
            assert conflict.name == "Conflicted Item", "Conflict item name should match"

            # Skylight timestamp is more recent, so it should win in resolution
            assert conflict.skylight_timestamp > conflict.paprika_timestamp, "Skylight should be more recent"

        print("   ✅ Concurrent modification handling successful")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


def run_all_tests():
    """Run all state management tests"""
    print("🧪 State Management Test Suite")
    print("=" * 50)

    tests = [
        test_database_initialization,
        test_item_tracking,
        test_change_detection,
        test_sync_statistics,
        test_deletion_tracking,
        test_concurrent_modifications,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"   ❌ {test.__name__} failed")
        except Exception as e:
            failed += 1
            print(f"   ❌ {test.__name__} failed with exception: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All state management tests passed!")
        print("✅ Phase 3: State Management - COMPLETE")
        return True
    else:
        print(f"❌ {failed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    if success:
        print("\n🚀 Ready to proceed with Phase 4: Sync Engine")
    else:
        print("\n🔧 Fix failing tests before proceeding")

    sys.exit(0 if success else 1)