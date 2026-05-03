#!/usr/bin/env python3
"""
Helper script to find Skylight frame ID

This script helps users discover their SKYLIGHT_FRAME_ID for configuration.
Run this script to authenticate with Skylight and see all available frames.
"""

import getpass
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from whisk.skylight_client import SkylightClient


def main():
    """Main function to find and display Skylight frames"""
    print("🔍 Skylight Frame ID Finder")
    print("=" * 40)
    print()

    email = input("Enter your Skylight email: ").strip()
    if not email:
        print("❌ Email is required")
        sys.exit(1)

    password = getpass.getpass("Enter your Skylight password: ")
    if not password:
        print("❌ Password is required")
        sys.exit(1)

    print()
    print("🔐 Authenticating with Skylight...")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        token_cache = f.name

    try:
        client = SkylightClient(email, password, frame_id="", token_cache_file=token_cache)
        client.authenticate()
        print("✅ Authenticated")

        print("📱 Finding your frames...")
        frames = client.get_frames()
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)
    finally:
        Path(token_cache).unlink(missing_ok=True)

    if not frames:
        print("❌ No frames found for your account")
        print("   Make sure you have set up a Skylight frame in the app")
        sys.exit(1)

    print()
    print("📋 Available frames:")
    print("-" * 60)

    for frame in frames:
        attrs = frame.get("attributes", frame)
        frame_id = frame.get("id", "Unknown")
        frame_name = attrs.get("name", "Unnamed Frame")
        print(f"  Frame Name: {frame_name}")
        print(f"  Frame ID:   {frame_id}")
        print("-" * 60)

    print()
    print("💡 Configuration Instructions:")
    print("1. Copy the Frame ID for your desired frame")
    print("2. Add it to your .env file:")
    print("   SKYLIGHT_FRAME_ID=<your_frame_id>")
    print()
    print("🎉 Setup complete! You can now configure your grocery list sync.")


if __name__ == "__main__":
    main()
