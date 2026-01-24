#!/usr/bin/env python3
"""
Sync Engine Demonstration

This script demonstrates the complete bidirectional sync functionality including:
- Automatic change detection
- Conflict resolution with Paprika as source of truth for equal timestamps
- Dry-run mode for safe testing
- Comprehensive error handling and logging
"""

import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sync_engine import SyncEngine
from state_manager import StateManager
from models import GroceryItem

# Mock clients for demonstration
class DemoPaprikaClient:
    def __init__(self):
        self.items = {}
        self.list_uid = "paprika_demo_list"

    def get_list_uid_by_name(self, name): return self.list_uid
    def get_grocery_list(self, list_name): return list(self.items.values())

    def add_item(self, name, checked, list_name):
        item_id = f"p{len(self.items) + 1}"
        item = GroceryItem(name=name, checked=checked, paprika_id=item_id,
                          paprika_timestamp=datetime.now(timezone.utc))
        self.items[item_id] = item
        return item_id

    def update_item(self, paprika_id, checked, name=None):
        if paprika_id in self.items:
            self.items[paprika_id].checked = checked
            if name: self.items[paprika_id].name = name
            self.items[paprika_id].paprika_timestamp = datetime.now(timezone.utc)

    def remove_item(self, paprika_id):
        if paprika_id in self.items: del self.items[paprika_id]


class DemoSkylightClient:
    def __init__(self):
        self.items = {}
        self.list_id = "skylight_demo_list"

    def get_list_id_by_name(self, name): return self.list_id
    def get_grocery_list(self, list_name): return list(self.items.values())

    def add_item(self, name, checked, list_name):
        item_id = f"s{len(self.items) + 1}"
        item = GroceryItem(name=name, checked=checked, skylight_id=item_id,
                          skylight_timestamp=datetime.now(timezone.utc))
        self.items[item_id] = item
        return item_id

    def update_item(self, skylight_id, checked, name=None):
        if skylight_id in self.items:
            self.items[skylight_id].checked = checked
            if name: self.items[skylight_id].name = name
            self.items[skylight_id].skylight_timestamp = datetime.now(timezone.utc)

    def remove_item(self, skylight_id):
        if skylight_id in self.items: del self.items[skylight_id]


def print_system_state(paprika, skylight, title):
    """Helper to display current state of both systems"""
    print(f"\n📊 {title}")
    print("-" * 50)

    paprika_items = paprika.get_grocery_list("Demo List")
    skylight_items = skylight.get_grocery_list("Demo List")

    print(f"📱 Paprika ({len(paprika_items)} items):")
    for item in paprika_items:
        status = "✓" if item.checked else " "
        time_str = item.paprika_timestamp.strftime("%H:%M") if item.paprika_timestamp else "N/A"
        print(f"   [{status}] {item.name} (ID: {item.paprika_id}, {time_str})")

    print(f"🖥️  Skylight ({len(skylight_items)} items):")
    for item in skylight_items:
        status = "✓" if item.checked else " "
        time_str = item.skylight_timestamp.strftime("%H:%M") if item.skylight_timestamp else "N/A"
        print(f"   [{status}] {item.name} (ID: {item.skylight_id}, {time_str})")


def demo_sync_engine():
    """Demonstrate complete sync engine functionality"""
    print("🎯 Sync Engine Demonstration")
    print("=" * 60)

    # Create demo database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name

    try:
        # Initialize components
        paprika = DemoPaprikaClient()
        skylight = DemoSkylightClient()
        state = StateManager(db_path)

        sync_engine = SyncEngine(
            paprika_client=paprika,
            skylight_client=skylight,
            state_manager=state,
            paprika_list_name="Demo List",
            skylight_list_name="Demo List"
        )

        print("✅ Sync engine initialized successfully")

        # Scenario 1: Initial setup with different items in each system
        print("\n🎬 Scenario 1: Initial Sync")
        print("Adding different items to each system...")

        paprika.add_item("Milk", checked=False, list_name="Demo List")
        paprika.add_item("Bread", checked=True, list_name="Demo List")

        skylight.add_item("Eggs", checked=False, list_name="Demo List")
        skylight.add_item("Cheese", checked=True, list_name="Demo List")

        print_system_state(paprika, skylight, "Before Initial Sync")

        # Perform sync
        results = sync_engine.sync(dry_run=False)

        print(f"\n🔄 Sync Results:")
        print(f"   Duration: {results['sync_duration_seconds']}s")
        print(f"   Success: {results['success']}")
        print(f"   Changes: {results['changes_detected']}")
        print(f"   Created in Paprika: {results['changes_applied'].get('paprika_created', [])}")
        print(f"   Created in Skylight: {results['changes_applied'].get('skylight_created', [])}")

        print_system_state(paprika, skylight, "After Initial Sync")

        # Scenario 2: Conflict resolution
        print("\n🎬 Scenario 2: Conflict Resolution")
        print("Modifying same item in both systems at different times...")

        # Wait a bit then modify in Paprika (older timestamp)
        import time
        time.sleep(0.1)
        milk_paprika = next(item for item in paprika.items.values() if item.name == "Milk")
        paprika.update_item(milk_paprika.paprika_id, checked=True)  # Check off in Paprika

        time.sleep(0.1)  # Skylight modification is newer
        milk_skylight = next(item for item in skylight.items.values() if item.name == "Milk")
        skylight.update_item(milk_skylight.skylight_id, checked=False)  # Uncheck in Skylight (newer)

        print_system_state(paprika, skylight, "Before Conflict Resolution")

        # Sync to resolve conflict
        results = sync_engine.sync(dry_run=False)

        print(f"\n🔄 Conflict Resolution Results:")
        print(f"   Conflicts resolved: {results['conflicts_resolved']}")

        for resolution in results.get('resolved_conflicts', []):
            print(f"   {resolution}")

        print_system_state(paprika, skylight, "After Conflict Resolution")

        # Scenario 3: Dry-run mode
        print("\n🎬 Scenario 3: Dry-Run Mode")
        print("Adding item to Paprika and testing dry-run...")

        paprika.add_item("Butter", checked=False, list_name="Demo List")

        print_system_state(paprika, skylight, "Before Dry-Run")

        # Dry-run sync
        results = sync_engine.sync(dry_run=True)

        print(f"\n🔄 Dry-Run Results:")
        print(f"   Would create in Skylight: {results['changes_applied'].get('skylight_would_create', [])}")
        print(f"   Would update in Paprika: {results['changes_applied'].get('paprika_would_update', [])}")

        print_system_state(paprika, skylight, "After Dry-Run (No Changes Made)")

        # Scenario 4: Item deletion sync
        print("\n🎬 Scenario 4: Deletion Sync")
        print("Deleting item from one system...")

        # First, do a real sync to get butter in both systems
        sync_engine.sync(dry_run=False)

        print_system_state(paprika, skylight, "Both Systems Synced")

        # Now delete from Skylight
        butter_skylight = next(item for item in skylight.items.values() if item.name == "Butter")
        skylight.remove_item(butter_skylight.skylight_id)

        print("\n🗑️  Deleted 'Butter' from Skylight")

        # Sync deletion
        results = sync_engine.sync(dry_run=False)

        print(f"\n🔄 Deletion Sync Results:")
        print(f"   Deleted from Paprika: {results['changes_applied'].get('paprika_deleted', [])}")

        print_system_state(paprika, skylight, "After Deletion Sync")

        # Final status
        print("\n📈 Final Sync Status:")
        status = sync_engine.get_sync_status()
        for key, value in status.items():
            if key != 'sync_statistics':
                print(f"   {key}: {value}")

        print("\n🎉 Sync Engine Demo Complete!")
        print("\n✨ Demonstrated capabilities:")
        print("   • Bidirectional sync (items created in both directions)")
        print("   • Conflict resolution (Skylight timestamp won)")
        print("   • Dry-run mode (safe testing without changes)")
        print("   • Deletion sync (removals propagated)")
        print("   • Status monitoring (comprehensive reporting)")

    finally:
        state.close()
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    demo_sync_engine()