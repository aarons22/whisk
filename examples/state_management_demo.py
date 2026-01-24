#!/usr/bin/env python3
"""
State Management Demonstration

This script demonstrates the key features of the state management system:
- Tracking items across both Paprika and Skylight
- Detecting changes (additions, modifications, deletions)
- Conflict detection for items modified in both systems
- Sync state tracking and statistics
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_manager import StateManager
from models import GroceryItem


def demo_state_management():
    """Demonstrate state management capabilities"""
    print("🎯 State Management System Demo")
    print("=" * 50)

    # Use a demo database
    demo_db = "demo_state.db"

    # Clean up any existing demo db
    Path(demo_db).unlink(missing_ok=True)

    with StateManager(demo_db) as sm:
        print("\n1️⃣ Setting up initial state...")

        # Simulate initial sync state from a few hours ago
        base_time = datetime.now(timezone.utc) - timedelta(hours=3)

        initial_items = [
            GroceryItem("Milk", checked=False, paprika_id="p1", skylight_id="s1",
                       paprika_timestamp=base_time, skylight_timestamp=base_time),
            GroceryItem("Bread", checked=True, paprika_id="p2", skylight_id="s2",
                       paprika_timestamp=base_time, skylight_timestamp=base_time),
            GroceryItem("Eggs", checked=False, paprika_id="p3", skylight_id="s3",
                       paprika_timestamp=base_time, skylight_timestamp=base_time),
        ]

        for item in initial_items:
            sm.add_or_update_item(item, "paprika_list_1", "skylight_list_1")

        # Mark all as synced
        sm.mark_sync_complete([item.name for item in initial_items], base_time)

        print("   ✅ Added 3 items to initial state")

        # Show initial statistics
        stats = sm.get_sync_statistics()
        print(f"   📊 Initial stats: {stats['total_items']} items, {stats['sync_coverage']}% coverage")

        print("\n2️⃣ Simulating changes over time...")

        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        thirty_min_ago = now - timedelta(minutes=30)

        # Simulate current Paprika state (some changes)
        current_paprika = [
            GroceryItem("Milk", checked=True, paprika_id="p1",  # Modified (checked off)
                       paprika_timestamp=hour_ago),
            GroceryItem("Bread", checked=True, paprika_id="p2",  # Unchanged
                       paprika_timestamp=base_time),
            # Eggs deleted from Paprika
            GroceryItem("Cheese", checked=False, paprika_id="p4",  # New item
                       paprika_timestamp=thirty_min_ago),
        ]

        # Simulate current Skylight state (different changes)
        current_skylight = [
            GroceryItem("Milk", checked=False, skylight_id="s1",  # Conflict! (unchecked)
                       skylight_timestamp=thirty_min_ago),  # More recent than Paprika
            GroceryItem("Bread", checked=True, skylight_id="s2",   # Unchanged
                       skylight_timestamp=base_time),
            GroceryItem("Eggs", checked=True, skylight_id="s3",    # Modified (checked off)
                       skylight_timestamp=hour_ago),
            GroceryItem("Butter", checked=False, skylight_id="s5", # New item
                       skylight_timestamp=now),
        ]

        print("   📝 Paprika changes: Milk checked, Eggs deleted, Cheese added")
        print("   📝 Skylight changes: Milk unchecked, Eggs checked, Butter added")

        print("\n3️⃣ Detecting changes...")

        changes = sm.detect_changes(current_paprika, current_skylight, "paprika_list_1", "skylight_list_1")

        print("   🔍 Change detection results:")
        print(f"     • Paprika additions: {len(changes['paprika_added'])} items")
        for item in changes['paprika_added']:
            print(f"       - {item.name}")

        print(f"     • Skylight additions: {len(changes['skylight_added'])} items")
        for item in changes['skylight_added']:
            print(f"       - {item.name}")

        print(f"     • Paprika modifications: {len(changes['paprika_modified'])} items")
        for item in changes['paprika_modified']:
            print(f"       - {item.name}")

        print(f"     • Skylight modifications: {len(changes['skylight_modified'])} items")
        for item in changes['skylight_modified']:
            print(f"       - {item.name}")

        print(f"     • Paprika deletions: {len(changes['paprika_deleted'])} items")
        for item in changes['paprika_deleted']:
            print(f"       - {item.name}")

        print(f"     • Conflicts: {len(changes['conflicts'])} items")
        for item in changes['conflicts']:
            p_time = item.paprika_timestamp.strftime("%H:%M") if item.paprika_timestamp else "N/A"
            s_time = item.skylight_timestamp.strftime("%H:%M") if item.skylight_timestamp else "N/A"
            winner = "Skylight" if (item.skylight_timestamp and item.paprika_timestamp and
                                  item.skylight_timestamp > item.paprika_timestamp) else "Paprika"
            print(f"       - {item.name} (P:{p_time} vs S:{s_time}, {winner} wins)")

        print("\n4️⃣ Updating state with current data...")

        # Add new items to state
        for item in current_paprika:
            sm.add_or_update_item(item, "paprika_list_1", None)

        for item in current_skylight:
            sm.add_or_update_item(item, None, "skylight_list_1")

        print("   ✅ State updated with current data")

        # Show final statistics
        final_stats = sm.get_sync_statistics()
        print(f"   📊 Final stats: {final_stats['total_items']} items, {final_stats['sync_coverage']}% coverage")

        print("\n5️⃣ Viewing all tracked items...")

        all_items = sm.get_all_active_items()
        print(f"   📋 Currently tracking {len(all_items)} items:")

        for item in all_items:
            p_id = item['paprika_id'] or "—"
            s_id = item['skylight_id'] or "—"
            status = "✓" if item['checked'] else " "
            synced = item['last_synced_at'] is not None
            sync_status = "✅" if synced else "🔄"
            print(f"     [{status}] {item['item_name']:<10} P:{p_id:<3} S:{s_id:<3} {sync_status}")

    print(f"\n6️⃣ Cleaning up demo database...")
    Path(demo_db).unlink(missing_ok=True)
    print("   🗑️  Demo database removed")

    print("\n" + "=" * 50)
    print("🎉 State Management Demo Complete!")
    print("\n✨ Key capabilities demonstrated:")
    print("   • SQLite-based state tracking")
    print("   • Change detection (additions, modifications, deletions)")
    print("   • Conflict detection with timestamp-based resolution")
    print("   • Sync statistics and reporting")
    print("   • Deletion tracking with soft deletes")
    print("\n🚀 Ready for Phase 4: Sync Engine implementation!")


if __name__ == "__main__":
    demo_state_management()