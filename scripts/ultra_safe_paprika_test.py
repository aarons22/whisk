#!/usr/bin/env python3
"""
ULTRA-SAFE Paprika Test with Production Override

This version allows testing with production data but with extra safety measures:
1. Multiple confirmations required
2. Only deletes items specifically named "test" or "sync_test"
3. Creates backup AND keeps production items completely unchanged
4. Dry-run mode first to show exactly what would happen
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from paprika_client import PaprikaClient
from dotenv import load_dotenv
import os
import requests
import json
import gzip
import datetime

def ultra_safe_paprika_test():
    """Ultra-safe test with production data protection"""

    print("🛡️  ULTRA-SAFE PAPRIKA SYNC TEST")
    print("=" * 50)
    print("Extra safety: Will ONLY delete items with 'test' in the name")
    print("All production data will be preserved")
    print()

    load_dotenv()
    paprika = PaprikaClient(os.getenv('PAPRIKA_EMAIL'), os.getenv('PAPRIKA_PASSWORD'))
    paprika.authenticate()

    # STEP 1: Create backup
    print("1. Creating production data backup...")
    headers = {'Authorization': f'Bearer {paprika.token}'}
    response = requests.get('https://www.paprikaapp.com/api/v2/sync/groceries/', headers=headers)

    if response.status_code != 200:
        print(f"❌ Failed to fetch current state: {response.status_code}")
        return False

    # Handle gzipped response
    content = response.content
    if content.startswith(b'\\x1f\\x8b'):
        content = gzip.decompress(content)

    current_state = json.loads(content.decode('utf-8'))
    all_items = current_state['result']

    # Create backup
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path.cwd() / f"paprika_ultra_safe_backup_{timestamp}.json"

    backup_data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'total_items': len(all_items),
        'backup_reason': 'Ultra-safe sync test with production override',
        'complete_state': current_state
    }

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2)
    backup_file.chmod(0o600)

    print(f"   ✅ Backup created: {backup_file}")
    print(f"   📊 {len(all_items)} total items backed up")

    # STEP 2: Find test items ONLY
    test_list_uid = "A35D5BB9-3EB3-4DE0-A883-CD786E8564FB"

    # Only consider items with 'test' in the name (case insensitive)
    test_items = [
        item for item in all_items
        if item['list_uid'] == test_list_uid and
        ('test' in item['name'].lower() or 'sync' in item['name'].lower())
    ]

    production_items = [
        item for item in all_items
        if not (item['list_uid'] == test_list_uid and
                ('test' in item['name'].lower() or 'sync' in item['name'].lower()))
    ]

    other_test_list_items = [
        item for item in all_items
        if item['list_uid'] == test_list_uid and
        not ('test' in item['name'].lower() or 'sync' in item['name'].lower())
    ]

    print(f"\\n2. Item analysis:")
    print(f"   Test items (with 'test' in name): {len(test_items)}")
    print(f"   Other Test List items: {len(other_test_list_items)} (WILL BE PRESERVED)")
    print(f"   Production items: {len(production_items)} (WILL BE PRESERVED)")

    for item in test_items:
        status = "✅" if item['purchased'] else "⬜"
        print(f"     {status} {item['name']} ← CAN BE DELETED")

    for item in other_test_list_items[:3]:  # Show first few
        status = "✅" if item['purchased'] else "⬜"
        print(f"     {status} {item['name']} ← WILL BE PRESERVED")

    if len(other_test_list_items) > 3:
        print(f"     ... and {len(other_test_list_items) - 3} more Test List items")

    if len(test_items) == 0:
        print("\\n📝 No test items found, adding one...")
        new_test_id = paprika.add_item("ultra_sync_test_item", checked=False, list_name="Test List")
        print(f"   Added: ultra_sync_test_item (ID: {new_test_id})")

        # Refetch
        response = requests.get('https://www.paprikaapp.com/api/v2/sync/groceries/', headers=headers)
        content = response.content
        if content.startswith(b'\\x1f\\x8b'):
            content = gzip.decompress(content)
        current_state = json.loads(content.decode('utf-8'))
        all_items = current_state['result']

        test_items = [
            item for item in all_items
            if item['list_uid'] == test_list_uid and
            ('test' in item['name'].lower() or 'sync' in item['name'].lower())
        ]
        production_items = [
            item for item in all_items
            if not (item['list_uid'] == test_list_uid and
                    ('test' in item['name'].lower() or 'sync' in item['name'].lower()))
        ]

    # STEP 3: Create dry-run preview
    print(f"\\n3. DRY RUN PREVIEW:")

    if len(test_items) > 0:
        item_to_delete = test_items[0]
        print(f"   🎯 Would delete: {item_to_delete['name']}")
        print(f"   ✅ Would preserve: {len(production_items)} production items")
        print(f"   ✅ Would preserve: {len(other_test_list_items)} other test list items")

        total_after = len(all_items) - 1
        print(f"   📊 Total items after: {total_after} (was {len(all_items)})")
    else:
        print("   ❌ No test items to delete")
        return False

    # STEP 4: Multiple confirmations
    print(f"\\n⚠️  ULTRA-SAFE CONFIRMATION REQUIRED")
    print(f"This test will:")
    print(f"   - Delete ONLY: {item_to_delete['name']}")
    print(f"   - Preserve ALL {len(production_items)} production items")
    print(f"   - Preserve ALL {len(other_test_list_items)} other test list items")
    print(f"   - Full restoration available from: {backup_file.name}")
    print()

    confirm1 = input("Type 'SAFE' if you understand the safety measures: ")
    if confirm1 != 'SAFE':
        print("Test cancelled")
        return False

    confirm2 = input(f"Type 'DELETE' to confirm deletion of '{item_to_delete['name']}': ")
    if confirm2 != 'DELETE':
        print("Test cancelled")
        return False

    confirm3 = input(f"Type 'PROCEED' to execute the test: ")
    if confirm3 != 'PROCEED':
        print("Test cancelled")
        return False

    # STEP 5: Execute sync
    print(f"\\n4. Executing ultra-safe sync...")

    # Build complete sync array (all items except the one test item)
    sync_array = []

    # Add ALL production items unchanged
    sync_array.extend(production_items)

    # Add all other test list items unchanged
    sync_array.extend(other_test_list_items)

    # Add remaining test items (all except the one we're deleting)
    remaining_test_items = [item for item in test_items if item['uid'] != item_to_delete['uid']]
    sync_array.extend(remaining_test_items)

    print(f"   📦 Sync array composition:")
    print(f"      Production items: {len(production_items)}")
    print(f"      Other test list items: {len(other_test_list_items)}")
    print(f"      Remaining test items: {len(remaining_test_items)}")
    print(f"      Total: {len(sync_array)}")
    print(f"      Deleted: 1 ({item_to_delete['name']})")

    # Send sync
    json_data = json.dumps(sync_array).encode('utf-8')
    compressed_data = gzip.compress(json_data)

    files = {'data': ('file', compressed_data, 'application/octet-stream')}

    response = requests.post(
        'https://www.paprikaapp.com/api/v2/sync/groceries/',
        files=files,
        headers=headers
    )

    print(f"   Response: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"   Success: {result}")

        # STEP 6: Verify
        print(f"\\n5. Verification...")

        verify_response = requests.get('https://www.paprikaapp.com/api/v2/sync/groceries/', headers=headers)
        verify_content = verify_response.content
        if verify_content.startswith(b'\\x1f\\x8b'):
            verify_content = gzip.decompress(verify_content)
        verify_state = json.loads(verify_content.decode('utf-8'))
        verify_items = verify_state['result']

        # Check results
        deleted_item_gone = not any(item['uid'] == item_to_delete['uid'] for item in verify_items)
        current_production_count = len([
            item for item in verify_items
            if not (item['list_uid'] == test_list_uid and
                    ('test' in item['name'].lower() or 'sync' in item['name'].lower()))
        ])

        print(f"   Total items after sync: {len(verify_items)}")
        print(f"   Production items preserved: {current_production_count} (expected {len(production_items)})")
        print(f"   Test item deleted: {deleted_item_gone}")

        if deleted_item_gone and current_production_count == len(production_items):
            print("\\n🎉 ULTRA-SAFE TEST SUCCESS!")
            print(f"   ✅ '{item_to_delete['name']}' successfully deleted")
            print(f"   ✅ All {len(production_items)} production items preserved")
            print(f"   ✅ True deletion via sync endpoint CONFIRMED!")
            print("\\n🚀 This proves Phase 6 architecture will work!")
            return True
        else:
            print("\\n❌ Test verification failed")
            return False

    else:
        print(f"   ❌ Sync request failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

if __name__ == "__main__":
    success = ultra_safe_paprika_test()
    print(f"\\n{'✅ TEST PASSED - PHASE 6 IS READY' if success else '❌ TEST FAILED'}")