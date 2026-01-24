#!/usr/bin/env python3
"""
Example usage of the Skylight client

This script demonstrates how to use the SkylightClient for basic operations.
Make sure your .env file is configured before running this.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skylight_client import SkylightClient


def load_env_vars():
    """Load environment variables from .env file"""
    env_file = Path(__file__).parent.parent / ".env"

    if not env_file.exists():
        print("❌ .env file not found. Please create it with your Skylight credentials.")
        sys.exit(1)

    env_vars = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value

    return env_vars


def main():
    """Demonstrate Skylight client usage"""
    print("📱 Skylight Client Usage Example")
    print("=" * 40)

    # Load credentials
    env_vars = load_env_vars()
    client = SkylightClient(
        email=env_vars["SKYLIGHT_EMAIL"],
        password=env_vars["SKYLIGHT_PASSWORD"],
        frame_id=env_vars["SKYLIGHT_FRAME_ID"]
    )

    # Authenticate
    print("🔐 Authenticating...")
    client.authenticate()
    print(f"✅ Authenticated as user {client.user_id}")
    print()

    # List all available frames
    print("📱 Available frames:")
    frames = client.get_frames()
    for frame in frames:
        print(f"  - {frame.get('name')}: {frame.get('id')}")
    print()

    # List all available lists
    print("📝 Available lists:")
    lists = client.get_lists()
    for lst in lists:
        print(f"  - {lst.get('name')}: {lst.get('id')}")
    print()

    # Work with Test List
    list_name = "Test List"
    print(f"🛒 Working with '{list_name}':")

    # Get current items
    items = client.get_grocery_list(list_name)
    print(f"📋 Current items ({len(items)}):")
    for item in items:
        status = "✓" if item.checked else " "
        print(f"  [{status}] {item.name}")
    print()

    # Add an example item
    print("➕ Adding example item...")
    item_id = client.add_item("Example Item", checked=False, list_name=list_name)
    print(f"✅ Added item with ID: {item_id}")
    print()

    # Update the item
    print("✏️  Updating item (checking it off)...")
    client.update_item(item_id, checked=True)
    print("✅ Item checked off")
    print()

    # Show updated list
    updated_items = client.get_grocery_list(list_name)
    print(f"📋 Updated items ({len(updated_items)}):")
    for item in updated_items:
        status = "✓" if item.checked else " "
        print(f"  [{status}] {item.name}")
    print()

    # Clean up - remove the example item
    print("🗑️  Removing example item...")
    client.remove_item(item_id)
    print("✅ Example item removed")

    print()
    print("🎉 Example completed successfully!")


if __name__ == "__main__":
    main()