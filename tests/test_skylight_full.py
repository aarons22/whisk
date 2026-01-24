#!/usr/bin/env python3
"""
Comprehensive test script for Skylight client CRUD operations

This script tests all operations: authentication, reading, creating, updating, and deleting items.
Tests are performed on the "Test List" to avoid affecting production data.
"""

import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skylight_client import SkylightClient


def load_env_vars():
    """Load environment variables from .env file"""
    env_file = Path(__file__).parent.parent / ".env"

    if not env_file.exists():
        print("❌ .env file not found")
        print("   Please create .env file with your Skylight credentials")
        print("   See .env.example for template")
        sys.exit(1)

    # Simple .env parser
    env_vars = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value

    return env_vars


def test_crud_operations(client: SkylightClient, list_name: str = "Test List"):
    """Test all CRUD operations on a specific list"""
    print(f"🧪 Testing CRUD operations on '{list_name}'")
    print("-" * 50)

    test_item_name = "Phase 2 Test Item"
    updated_name = "Phase 2 Updated Item"
    created_item_id = None

    try:
        # READ: Get initial state
        print("1. 📖 Testing READ operations...")
        initial_items = client.get_grocery_list(list_name)
        print(f"   ✅ Found {len(initial_items)} existing items")

        # Remove any existing test items to start clean
        for item in initial_items:
            if test_item_name in item.name or updated_name in item.name:
                print(f"   🧹 Cleaning up existing test item: {item.name}")
                try:
                    client.remove_item(item.skylight_id)
                except Exception as e:
                    print(f"   ⚠️  Could not clean up {item.name}: {e}")

        print()

        # CREATE: Add new item
        print("2. ➕ Testing CREATE operation...")
        try:
            created_item_id = client.add_item(
                name=test_item_name,
                checked=False,
                list_name=list_name
            )
            print(f"   ✅ Created item: {test_item_name} (ID: {created_item_id})")
        except Exception as e:
            print(f"   ❌ CREATE failed: {e}")
            return False

        # Wait a moment for the API to process
        time.sleep(1)

        # Verify item was created
        items_after_create = client.get_grocery_list(list_name)
        created_item = next((item for item in items_after_create if item.skylight_id == created_item_id), None)
        if created_item:
            print(f"   ✅ Verified item exists: {created_item.name} (checked: {created_item.checked})")
        else:
            print(f"   ❌ Created item not found in list!")
            return False

        print()

        # UPDATE: Modify the item (check it off)
        print("3. ✏️  Testing UPDATE operation (check off)...")
        try:
            client.update_item(created_item_id, checked=True)
            print(f"   ✅ Updated item to checked=True")
        except Exception as e:
            print(f"   ❌ UPDATE (check) failed: {e}")
            return False

        # Wait and verify update
        time.sleep(1)
        items_after_check = client.get_grocery_list(list_name)
        updated_item = next((item for item in items_after_check if item.skylight_id == created_item_id), None)
        if updated_item and updated_item.checked:
            print(f"   ✅ Verified item is checked: {updated_item.name}")
        else:
            print(f"   ❌ Item check status not updated!")
            return False

        print()

        # UPDATE: Modify the name and uncheck
        print("4. ✏️  Testing UPDATE operation (rename and uncheck)...")
        try:
            client.update_item(created_item_id, checked=False, name=updated_name)
            print(f"   ✅ Updated item name to: {updated_name}")
        except Exception as e:
            print(f"   ❌ UPDATE (rename) failed: {e}")
            return False

        # Wait and verify name update
        time.sleep(1)
        items_after_rename = client.get_grocery_list(list_name)
        renamed_item = next((item for item in items_after_rename if item.skylight_id == created_item_id), None)
        if renamed_item and renamed_item.name == updated_name and not renamed_item.checked:
            print(f"   ✅ Verified item renamed and unchecked: {renamed_item.name}")
        else:
            print(f"   ❌ Item rename/uncheck not successful!")
            return False

        print()

        # DELETE: Remove the item
        print("5. 🗑️  Testing DELETE operation...")
        try:
            client.remove_item(created_item_id)
            print(f"   ✅ Deleted item: {created_item_id}")
        except Exception as e:
            print(f"   ❌ DELETE failed: {e}")
            return False

        # Wait and verify deletion
        time.sleep(1)
        items_after_delete = client.get_grocery_list(list_name)
        deleted_item = next((item for item in items_after_delete if item.skylight_id == created_item_id), None)
        if deleted_item is None:
            print(f"   ✅ Verified item was deleted")
        else:
            print(f"   ❌ Item still exists after deletion!")
            return False

        print()
        print("🎉 All CRUD operations completed successfully!")
        return True

    except Exception as e:
        print(f"❌ CRUD test failed with exception: {e}")
        # Try to clean up the test item if it was created
        if created_item_id:
            try:
                print(f"🧹 Attempting cleanup of test item...")
                client.remove_item(created_item_id)
                print(f"   ✅ Cleanup successful")
            except Exception as cleanup_e:
                print(f"   ⚠️  Cleanup failed: {cleanup_e}")
        return False


def main():
    """Test Skylight client end-to-end"""
    print("🧪 Skylight Client End-to-End Test")
    print("=" * 50)

    # Load credentials
    env_vars = load_env_vars()

    email = env_vars.get("SKYLIGHT_EMAIL")
    password = env_vars.get("SKYLIGHT_PASSWORD")
    frame_id = env_vars.get("SKYLIGHT_FRAME_ID")

    if not all([email, password, frame_id]):
        print("❌ Missing required environment variables:")
        print("   SKYLIGHT_EMAIL, SKYLIGHT_PASSWORD, SKYLIGHT_FRAME_ID")
        print()
        print("📋 Setup steps:")
        print("1. Run: python scripts/find_skylight_frame.py")
        print("2. Update your .env file with the credentials")
        print("3. Run this test again")
        sys.exit(1)

    if email == "your.email@example.com" or frame_id == "your_frame_id":
        print("❌ Placeholder credentials detected in .env file")
        print("   Please replace the placeholder values with your actual credentials")
        print()
        print("📋 Setup steps:")
        print("1. Run: python scripts/find_skylight_frame.py")
        print("2. Update your .env file with the real values")
        print("3. Run this test again")
        sys.exit(1)

    print(f"📧 Using email: {email}")
    print(f"📱 Using frame ID: {frame_id}")
    print()

    try:
        # Initialize client
        client = SkylightClient(email, password, frame_id)

        # Test authentication
        print("🔐 Testing authentication...")
        client.authenticate()
        print(f"✅ Authenticated as user {client.user_id}")
        print()

        # Test basic read operations first
        print("📱 Testing frame and list discovery...")
        frames = client.get_frames()
        print(f"✅ Found {len(frames)} frames")

        lists = client.get_lists()
        print(f"✅ Found {len(lists)} lists:")
        for lst in lists:
            print(f"   - {lst.get('name', 'Unnamed')} (ID: {lst.get('id')})")
        print()

        # Test CRUD operations
        test_success = test_crud_operations(client)

        if test_success:
            print("🎉 All tests passed! Skylight integration is working correctly.")
            print()
            print("📋 Integration status:")
            print("   ✅ Authentication")
            print("   ✅ Frame discovery")
            print("   ✅ List discovery")
            print("   ✅ Read items")
            print("   ✅ Create items")
            print("   ✅ Update items (name and checked status)")
            print("   ✅ Delete items")
            print()
            print("🚀 Ready to proceed with Phase 3: State Management!")
        else:
            print("❌ Some tests failed. Please check the errors above.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()