#!/usr/bin/env python3
"""
Paprika Production Data Restoration Script

This script can restore your Paprika data from the backup files created
by the safe sync test. Use this if anything goes wrong during testing.

Usage:
1. Find your backup file: paprika_production_backup_YYYYMMDD_HHMMSS.json
2. Run: python restore_paprika_backup.py <backup_file>
3. Confirm restoration when prompted
"""

import sys
import json
import gzip
import requests
from pathlib import Path

def restore_paprika_data(backup_file_path):
    """Restore Paprika data from backup file"""

    print("🔄 PAPRIKA DATA RESTORATION")
    print("=" * 50)

    # Load backup file
    backup_file = Path(backup_file_path)
    if not backup_file.exists():
        print(f"❌ Backup file not found: {backup_file}")
        return False

    print(f"📂 Loading backup: {backup_file}")

    with open(backup_file, 'r') as f:
        backup_data = json.load(f)

    print(f"   Backup created: {backup_data['timestamp']}")
    print(f"   Total items: {backup_data['total_items']}")
    print(f"   Reason: {backup_data['backup_reason']}")

    # Extract the items array
    items_to_restore = backup_data['complete_state']['result']
    print(f"   Items to restore: {len(items_to_restore)}")

    # Group by list for verification
    list_groups = {}
    for item in items_to_restore:
        list_uid = item['list_uid']
        list_groups.setdefault(list_uid, []).append(item)

    print(f"\n📋 Items by list:")
    for list_uid, items in list_groups.items():
        print(f"   {list_uid}: {len(items)} items")

    # Confirm restoration
    print(f"\n⚠️  RESTORATION CONFIRMATION")
    print(f"This will restore {len(items_to_restore)} items to your Paprika account")
    print(f"Current grocery list state will be REPLACED with backup data")
    print(f"")

    confirm = input("Type 'RESTORE' to proceed: ")
    if confirm != 'RESTORE':
        print("Restoration cancelled")
        return False

    # Get credentials
    from dotenv import load_dotenv
    import os

    load_dotenv()
    email = os.getenv('PAPRIKA_EMAIL')
    password = os.getenv('PAPRIKA_PASSWORD')

    if not email or not password:
        print("❌ Paprika credentials not found in .env file")
        return False

    # Authenticate
    print(f"\n🔐 Authenticating with Paprika...")
    sys.path.insert(0, str(Path.cwd() / 'src'))
    from paprika_client import PaprikaClient

    paprika = PaprikaClient(email, password)
    paprika.authenticate()
    print(f"   ✅ Authenticated successfully")

    # Restore data via sync endpoint
    print(f"\n🔄 Restoring data...")

    headers = {'Authorization': f'Bearer {paprika.token}'}

    # Gzip compress the items array
    json_data = json.dumps(items_to_restore).encode('utf-8')
    compressed_data = gzip.compress(json_data)

    files = {'data': ('file', compressed_data, 'application/octet-stream')}

    response = requests.post(
        'https://www.paprikaapp.com/api/v2/sync/groceries/',
        files=files,
        headers=headers
    )

    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Restoration successful: {result}")

        # Verify restoration
        print(f"\n✅ Verifying restoration...")
        verify_response = requests.get('https://www.paprikaapp.com/api/v2/sync/groceries/', headers=headers)

        verify_content = verify_response.content
        if verify_content.startswith(b'\\x1f\\x8b'):
            verify_content = gzip.decompress(verify_content)

        current_state = json.loads(verify_content.decode('utf-8'))
        current_items = current_state['result']

        print(f"   Current items after restoration: {len(current_items)}")

        if len(current_items) == len(items_to_restore):
            print(f"   ✅ Item count matches backup")
        else:
            print(f"   ⚠️  Item count mismatch: {len(current_items)} vs {len(items_to_restore)}")

        return True

    else:
        print(f"   ❌ Restoration failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def list_backups():
    """List available backup files"""
    print("📂 AVAILABLE BACKUP FILES")
    print("=" * 30)

    backup_files = list(Path.cwd().glob("paprika_production_backup_*.json"))

    if not backup_files:
        print("No backup files found in current directory")
        return

    for backup_file in sorted(backup_files):
        # Load and show summary
        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)

            print(f"📄 {backup_file.name}")
            print(f"   Created: {backup_data['timestamp']}")
            print(f"   Items: {backup_data['total_items']}")
            print(f"   Reason: {backup_data['backup_reason']}")
            print()

        except Exception as e:
            print(f"📄 {backup_file.name} (Error reading: {e})")

def main():
    """Main restoration interface"""

    if len(sys.argv) < 2:
        print("Paprika Data Restoration Tool")
        print("=" * 30)
        print()
        print("Usage:")
        print(f"  {sys.argv[0]} <backup_file.json>     # Restore from specific backup")
        print(f"  {sys.argv[0]} --list                 # List available backups")
        print()

        list_backups()
        return

    if sys.argv[1] == '--list':
        list_backups()
        return

    backup_file = sys.argv[1]
    success = restore_paprika_data(backup_file)

    if success:
        print(f"\n🎉 Restoration completed successfully!")
        print(f"Your Paprika data has been restored from: {backup_file}")
    else:
        print(f"\n❌ Restoration failed")
        print(f"Your data remains unchanged")

if __name__ == "__main__":
    main()