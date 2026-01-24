#!/usr/bin/env python3
"""
Helper script to find Skylight frame ID

This script helps users discover their SKYLIGHT_FRAME_ID for configuration.
Run this script to authenticate with Skylight and see all available frames.
"""

import base64
import getpass
import json
import sys
from typing import Dict, Any

import requests


def authenticate_skylight(email: str, password: str) -> Dict[str, Any]:
    """
    Authenticate with Skylight API

    Args:
        email: Skylight account email
        password: Skylight account password

    Returns:
        Dictionary with user_id and user_token
    """
    url = "https://api.ourskylight.com/api/sessions"

    payload = {
        "user": {
            "email": email,
            "password": password
        }
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()

        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("❌ Invalid Skylight credentials")
        else:
            print(f"❌ HTTP error during authentication: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to authenticate with Skylight: {e}")
        sys.exit(1)


def get_frames(auth_data: Dict[str, Any]) -> list:
    """
    Get all frames for the authenticated user

    Args:
        auth_data: Authentication data from login

    Returns:
        List of frame dictionaries
    """
    # Create Base64 encoded token: userId:userToken
    user_id = auth_data.get("user_id")
    user_token = auth_data.get("user_token")

    if not user_id or not user_token:
        print(f"❌ Invalid authentication response: {auth_data}")
        sys.exit(1)

    token_string = f"{user_id}:{user_token}"
    encoded_token = base64.b64encode(token_string.encode()).decode()

    url = "https://api.ourskylight.com/api/frames"
    headers = {
        "Authorization": f'Token token="{encoded_token}"',
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        return data.get("frames", [])

    except Exception as e:
        print(f"❌ Failed to get frames from Skylight: {e}")
        sys.exit(1)


def main():
    """Main function to find and display Skylight frames"""
    print("🔍 Skylight Frame ID Finder")
    print("=" * 40)
    print()

    # Get credentials from user
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

    # Authenticate
    auth_data = authenticate_skylight(email, password)
    print(f"✅ Authenticated as user {auth_data.get('user_id')}")

    # Get frames
    print("📱 Finding your frames...")
    frames = get_frames(auth_data)

    if not frames:
        print("❌ No frames found for your account")
        print("   Make sure you have set up a Skylight frame in the app")
        sys.exit(1)

    # Display frames
    print()
    print("📋 Available frames:")
    print("-" * 60)

    for frame in frames:
        frame_id = frame.get("id", "Unknown")
        frame_name = frame.get("name", "Unnamed Frame")
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