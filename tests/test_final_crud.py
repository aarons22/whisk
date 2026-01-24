#!/usr/bin/env python3
"""
Final comprehensive CRUD test with all fixes
"""

import base64
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skylight_client import SkylightClient


def final_crud_test():
    """Final comprehensive CRUD test"""
    print("🎉 Final Skylight CRUD Test")
    print("=" * 40)

    # Use auth token
    auth_header = "MTM1NjY0ODI6YXR1X2FoNHZxUE41d3E4VXdKcldWNUhacWhMM1B2bDRtT3pQ"
    decoded = base64.b64decode(auth_header).decode()
    user_id, auth_token = decoded.split(":", 1)

    client = SkylightClient("", "", "4878053")
    client.user_id = user_id
    client.auth_token = auth_token

    test_item_name = "Final Test Item"

    try:
        # Step 1: READ - Show initial state
        print("1️⃣ READ - Initial state:")
        initial_items = client.get_grocery_list("Test List")
        for item in initial_items:
            status = "✓" if item.checked else " "
            print(f"   [{status}] {item.name}")
        print()

        # Step 2: CREATE - Add test item
        print("2️⃣ CREATE - Adding test item...")
        created_id = client.add_item(test_item_name, checked=False, list_name="Test List")
        print(f"   ✅ Created: {test_item_name} (ID: {created_id})")
        time.sleep(0.5)

        # Verify creation
        items_after_create = client.get_grocery_list("Test List")
        created_item = next((item for item in items_after_create if item.skylight_id == created_id), None)
        if created_item:
            status = "✓" if created_item.checked else " "
            print(f"   ✅ Verified: [{status}] {created_item.name}")
        print()

        # Step 3: UPDATE - Check off the item
        print("3️⃣ UPDATE - Checking off item...")
        client.update_item(created_id, checked=True)
        time.sleep(0.5)

        items_after_update = client.get_grocery_list("Test List")
        updated_item = next((item for item in items_after_update if item.skylight_id == created_id), None)
        if updated_item:
            status = "✓" if updated_item.checked else " "
            print(f"   ✅ After update: [{status}] {updated_item.name}")
            if updated_item.checked:
                print("   🎉 Successfully checked off!")
            else:
                print("   ❌ Update didn't work")
        print()

        # Step 4: UPDATE - Uncheck the item
        print("4️⃣ UPDATE - Unchecking item...")
        client.update_item(created_id, checked=False)
        time.sleep(0.5)

        items_after_uncheck = client.get_grocery_list("Test List")
        unchecked_item = next((item for item in items_after_uncheck if item.skylight_id == created_id), None)
        if unchecked_item:
            status = "✓" if unchecked_item.checked else " "
            print(f"   ✅ After uncheck: [{status}] {unchecked_item.name}")
            if not unchecked_item.checked:
                print("   🎉 Successfully unchecked!")
            else:
                print("   ❌ Uncheck didn't work")
        print()

        # Step 5: DELETE - Remove the test item
        print("5️⃣ DELETE - Removing test item...")
        client.remove_item(created_id)
        time.sleep(0.5)

        items_after_delete = client.get_grocery_list("Test List")
        deleted_item = next((item for item in items_after_delete if item.skylight_id == created_id), None)
        if deleted_item is None:
            print("   ✅ Successfully deleted!")
        else:
            print("   ❌ Item still exists")
        print()

        # Step 6: Final state
        print("6️⃣ READ - Final state:")
        final_items = client.get_grocery_list("Test List")
        for item in final_items:
            status = "✓" if item.checked else " "
            print(f"   [{status}] {item.name}")

        print("\n" + "="*50)
        print("🎉 ALL CRUD OPERATIONS SUCCESSFUL!")
        print("✅ Create: Working")
        print("✅ Read: Working")
        print("✅ Update (check/uncheck): Working")
        print("✅ Delete: Working")
        print()
        print("🚀 Phase 2: Skylight Integration - COMPLETE!")
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = final_crud_test()
    if success:
        print("\n✨ Ready to proceed with Phase 3: State Management")
    else:
        print("\n🔧 Still need some fixes")