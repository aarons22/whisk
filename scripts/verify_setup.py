#!/usr/bin/env python3
"""
Setup verification script

This script checks if your environment is properly configured for Phase 2 testing.
Run this before running the full test suite.
"""

import sys
from pathlib import Path


def check_env_file():
    """Check if .env file exists and has required variables"""
    env_file = Path(__file__).parent.parent / ".env"

    if not env_file.exists():
        print("❌ .env file not found")
        return False

    required_vars = ["SKYLIGHT_EMAIL", "SKYLIGHT_PASSWORD", "SKYLIGHT_FRAME_ID"]
    found_vars = {}

    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key in required_vars:
                    found_vars[key] = value

    missing_vars = []
    placeholder_vars = []

    for var in required_vars:
        if var not in found_vars:
            missing_vars.append(var)
        elif found_vars[var] in ["", "your.email@example.com", "your_skylight_password", "your_frame_id"]:
            placeholder_vars.append(var)

    if missing_vars:
        print(f"❌ Missing variables in .env: {', '.join(missing_vars)}")
        return False

    if placeholder_vars:
        print(f"❌ Placeholder values detected: {', '.join(placeholder_vars)}")
        return False

    print("✅ .env file looks good")
    return True


def check_dependencies():
    """Check if required Python packages are available"""
    try:
        import requests
        print("✅ requests library available")
    except ImportError:
        print("❌ requests library not found. Run: pip install requests")
        return False

    return True


def check_project_structure():
    """Check if required files exist"""
    base_path = Path(__file__).parent.parent
    required_files = [
        "src/skylight_client.py",
        "src/models.py",
        "scripts/find_skylight_frame.py",
        "tests/test_skylight_full.py"
    ]

    missing_files = []
    for file_path in required_files:
        if not (base_path / file_path).exists():
            missing_files.append(file_path)

    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        return False

    print("✅ Project structure looks good")
    return True


def main():
    """Run all setup checks"""
    print("🔍 Phase 2 Setup Verification")
    print("=" * 40)

    checks = [
        ("Environment Configuration", check_env_file),
        ("Python Dependencies", check_dependencies),
        ("Project Structure", check_project_structure),
    ]

    all_passed = True

    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            all_passed = False

    print("\n" + "=" * 40)

    if all_passed:
        print("🎉 All checks passed! You're ready to test Phase 2.")
        print()
        print("📋 Next steps:")
        print("1. Run: python tests/test_skylight_full.py")
        print("2. If tests pass, Phase 2 is complete!")
        print("3. Ready to proceed with Phase 3: State Management")
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print()
        print("📋 Common fixes:")
        print("1. Run: python scripts/find_skylight_frame.py")
        print("2. Update .env with your actual Skylight credentials")
        print("3. Install dependencies: pip install requests")


if __name__ == "__main__":
    main()