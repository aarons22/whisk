#!/usr/bin/env python3
"""
Comprehensive test suite for SyncEngine

Tests all aspects of bidirectional sync including:
- Basic sync operations
- Conflict resolution
- Dry-run mode
- Error handling
- State management integration
"""

import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sync_engine import SyncEngine
from state_manager import StateManager
from models import GroceryItem


class MockPaprikaClient:
    """Mock Paprika client for testing"""

    def __init__(self):
        self.items = {}
        self.list_uid = "paprika_list_1"

    def get_list_uid_by_name(self, name):
        return self.list_uid

    def get_grocery_list(self, list_name):
        return list(self.items.values())

    def add_item(self, name, checked, list_name):
        item_id = f"p{len(self.items) + 1}"
        item = GroceryItem(
            name=name,
            checked=checked,
            paprika_id=item_id,
            paprika_timestamp=datetime.now(timezone.utc)
        )
        self.items[item_id] = item
        return item_id

    def update_item(self, paprika_id, checked, name=None):
        if paprika_id in self.items:
            self.items[paprika_id].checked = checked
            if name:
                self.items[paprika_id].name = name
            self.items[paprika_id].paprika_timestamp = datetime.now(timezone.utc)

    def remove_item(self, paprika_id):
        if paprika_id in self.items:
            del self.items[paprika_id]


class MockSkylightClient:
    """Mock Skylight client for testing"""

    def __init__(self):
        self.items = {}
        self.list_id = "skylight_list_1"

    def get_list_id_by_name(self, name):
        return self.list_id

    def get_grocery_list(self, list_name):
        return list(self.items.values())

    def add_item(self, name, checked, list_name):
        item_id = f"s{len(self.items) + 1}"
        item = GroceryItem(
            name=name,
            checked=checked,
            skylight_id=item_id,
            skylight_timestamp=datetime.now(timezone.utc)
        )
        self.items[item_id] = item
        return item_id

    def update_item(self, skylight_id, checked, name=None):
        if skylight_id in self.items:
            self.items[skylight_id].checked = checked
            if name:
                self.items[skylight_id].name = name
            self.items[skylight_id].skylight_timestamp = datetime.now(timezone.utc)

    def remove_item(self, skylight_id):
        if skylight_id in self.items:
            del self.items[skylight_id]


def create_test_sync_engine():
    """Create SyncEngine with mock clients for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    paprika_client = MockPaprikaClient()
    skylight_client = MockSkylightClient()
    state_manager = StateManager(db_path)

    sync_engine = SyncEngine(
        paprika_client=paprika_client,
        skylight_client=skylight_client,
        state_manager=state_manager,
        paprika_list_name="Test List",
        skylight_list_name="Test List"
    )

    # Return everything for cleanup
    return sync_engine, paprika_client, skylight_client, state_manager, db_path


def test_basic_sync():
    """Test basic bidirectional sync without conflicts"""
    print("🧪 Testing basic bidirectional sync...")

    sync_engine, paprika, skylight, state, db_path = create_test_sync_engine()

    try:
        # Set up initial state
        paprika.add_item("Milk", checked=False, list_name="Test List")
        skylight.add_item("Bread", checked=True, list_name="Test List")

        # Perform sync
        results = sync_engine.sync(dry_run=False)

        assert results['success'], f"Sync should succeed, got: {results}"
        assert results['changes_applied']['skylight_created'] == ["Milk"], "Milk should be created in Skylight"
        assert results['changes_applied']['paprika_created'] == ["Bread"], "Bread should be created in Paprika"

        # Verify items exist in both systems
        paprika_items = paprika.get_grocery_list("Test List")
        skylight_items = skylight.get_grocery_list("Test List")

        paprika_names = {item.name for item in paprika_items}
        skylight_names = {item.name for item in skylight_items}

        assert "Milk" in paprika_names and "Milk" in skylight_names, "Milk should be in both systems"
        assert "Bread" in paprika_names and "Bread" in skylight_names, "Bread should be in both systems"

        print("   ✅ Basic sync successful")
        return True

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


def test_conflict_resolution():
    """Test timestamp-based conflict resolution"""
    print("🧪 Testing conflict resolution...")

    sync_engine, paprika, skylight, state, db_path = create_test_sync_engine()

    try:
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        thirty_min_ago = now - timedelta(minutes=30)

        # Create conflicting items (same name, different checked status)
        milk_paprika = GroceryItem(
            name="Milk",
            checked=True,  # Checked in Paprika
            paprika_id="p1",
            paprika_timestamp=hour_ago  # Older
        )

        milk_skylight = GroceryItem(
            name="Milk",
            checked=False,  # Unchecked in Skylight
            skylight_id="s1",
            skylight_timestamp=thirty_min_ago  # Newer - should win
        )

        paprika.items["p1"] = milk_paprika
        skylight.items["s1"] = milk_skylight

        # Add to state as if previously synced
        state.add_or_update_item(milk_paprika, paprika.list_uid, None)
        state.add_or_update_item(milk_skylight, None, skylight.list_id)
        state.mark_sync_complete(["Milk"], hour_ago - timedelta(hours=1))

        # Perform sync
        results = sync_engine.sync(dry_run=False)

        assert results['success'], f"Sync should succeed, got: {results}"
        assert results['conflicts_resolved'] == 1, "Should resolve 1 conflict"

        # Skylight timestamp is newer, so Skylight should win in conflict resolution
        final_paprika_milk = paprika.items["p1"]
        assert not final_paprika_milk.checked, "Paprika item should be unchecked (Skylight won)"

        print("   ✅ Conflict resolution successful")
        return True

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


def test_dry_run_mode():
    """Test dry-run mode doesn't make actual changes"""
    print("🧪 Testing dry-run mode...")

    sync_engine, paprika, skylight, state, db_path = create_test_sync_engine()

    try:
        # Set up state with items to sync
        paprika.add_item("Eggs", checked=False, list_name="Test List")
        skylight.add_item("Butter", checked=True, list_name="Test List")

        # Record initial counts
        initial_paprika_count = len(paprika.items)
        initial_skylight_count = len(skylight.items)

        # Perform dry-run sync
        results = sync_engine.sync(dry_run=True)

        assert results['dry_run'], "Should be marked as dry run"
        assert results['success'], "Dry run should succeed"

        # Check that simulation results are present
        changes = results['changes_applied']
        assert 'paprika_would_create' in changes, "Should have simulation results"
        assert 'skylight_would_create' in changes, "Should have simulation results"

        # Verify no actual changes were made
        final_paprika_count = len(paprika.items)
        final_skylight_count = len(skylight.items)

        assert final_paprika_count == initial_paprika_count, "Paprika items shouldn't change in dry run"
        assert final_skylight_count == initial_skylight_count, "Skylight items shouldn't change in dry run"

        print("   ✅ Dry-run mode successful")
        return True

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


def test_deletion_sync():
    """Test syncing item deletions"""
    print("🧪 Testing deletion sync...")

    sync_engine, paprika, skylight, state, db_path = create_test_sync_engine()

    try:
        # Set up initial synced state
        cheese_item = GroceryItem(
            name="Cheese",
            paprika_id="p1",
            skylight_id="s1",
            paprika_timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            skylight_timestamp=datetime.now(timezone.utc) - timedelta(hours=2)
        )

        paprika.items["p1"] = cheese_item
        skylight.items["s1"] = cheese_item

        # Add to state and mark as synced
        state.add_or_update_item(cheese_item, paprika.list_uid, skylight.list_id)
        state.mark_sync_complete(["Cheese"], datetime.now(timezone.utc) - timedelta(hours=2))

        # Delete from Paprika (simulate user deleting in Paprika app)
        del paprika.items["p1"]

        # Perform sync
        results = sync_engine.sync(dry_run=False)

        assert results['success'], f"Sync should succeed, got: {results}"
        assert "Cheese" in results['changes_applied']['skylight_deleted'], "Cheese should be deleted from Skylight"

        # Verify item is deleted from both systems
        assert len(paprika.items) == 0, "Paprika should have no items"
        assert len(skylight.items) == 0, "Skylight should have no items after sync"

        print("   ✅ Deletion sync successful")
        return True

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


def test_error_handling():
    """Test error handling during sync operations"""
    print("🧪 Testing error handling...")

    sync_engine, paprika, skylight, state, db_path = create_test_sync_engine()

    try:
        # Set up a scenario that will cause an error
        # Mock the skylight client to raise an exception
        original_add = skylight.add_item

        def failing_add(*args, **kwargs):
            raise Exception("Simulated API error")

        skylight.add_item = failing_add

        # Add item to Paprika that will need to sync to Skylight
        paprika.add_item("Problem Item", checked=False, list_name="Test List")

        # Perform sync
        results = sync_engine.sync(dry_run=False)

        assert not results['success'], "Sync should fail due to error"
        assert len(results['errors']) > 0, "Should have error messages"

        # Error should be properly recorded
        error_found = any("Problem Item" in error for error in results['errors'])
        assert error_found, "Error message should mention the problematic item"

        # Restore original method
        skylight.add_item = original_add

        print("   ✅ Error handling successful")
        return True

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


def test_sync_status():
    """Test sync status reporting"""
    print("🧪 Testing sync status reporting...")

    sync_engine, paprika, skylight, state, db_path = create_test_sync_engine()

    try:
        # Add some items
        paprika.add_item("Apples", checked=False, list_name="Test List")
        skylight.add_item("Bananas", checked=True, list_name="Test List")

        # Get sync status
        status = sync_engine.get_sync_status()

        assert status['lists_configured'], "Lists should be configured"
        assert status['paprika_items'] == 1, "Should show 1 Paprika item"
        assert status['skylight_items'] == 1, "Should show 1 Skylight item"
        assert status['pending_changes'] > 0, "Should have pending changes"

        print("   ✅ Sync status reporting successful")
        return True

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


def run_all_tests():
    """Run all sync engine tests"""
    print("🧪 Sync Engine Test Suite")
    print("=" * 50)

    tests = [
        test_basic_sync,
        test_conflict_resolution,
        test_dry_run_mode,
        test_deletion_sync,
        test_error_handling,
        test_sync_status,
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
        print("🎉 All sync engine tests passed!")
        print("✅ Phase 4: Sync Engine with Conflict Resolution - COMPLETE")
        return True
    else:
        print(f"❌ {failed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    if success:
        print("\n🚀 Ready to proceed with Phase 5: Scheduling and Configuration")
    else:
        print("\n🔧 Fix failing tests before proceeding")

    sys.exit(0 if success else 1)