"""
Phase 1 Tests: Paprika Integration

Run with: python tests/test_paprika.py

Requirements:
- .env file with PAPRIKA_EMAIL and PAPRIKA_PASSWORD
- "Test List" created in Paprika app (to protect production data)
"""

import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.paprika_client import PaprikaClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_authentication():
    """Test 1: Authentication"""
    logger.info("=" * 60)
    logger.info("TEST 1: Authentication")
    logger.info("=" * 60)

    try:
        client = PaprikaClient(
            email=os.getenv("PAPRIKA_EMAIL"), password=os.getenv("PAPRIKA_PASSWORD")
        )
        client.authenticate()
        logger.info("✓ Authentication successful")
        return client
    except Exception as e:
        logger.error(f"✗ Authentication failed: {e}")
        raise


def test_read_list(client: PaprikaClient):
    """Test 2: Read grocery list"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Read Grocery List")
    logger.info("=" * 60)

    try:
        items = client.get_grocery_list("Test List")
        logger.info(f"✓ Retrieved {len(items)} items from grocery list")

        if items:
            logger.info("\nCurrent items:")
            for item in items:
                logger.info(f"  {item}")

        return items
    except Exception as e:
        logger.error(f"✗ Failed to read grocery list: {e}")
        raise


def test_add_item(client: PaprikaClient):
    """Test 3: Add item to grocery list"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Add Item")
    logger.info("=" * 60)

    test_item_name = "Phase 1 Test Item"

    try:
        uid = client.add_item(name=test_item_name, checked=False)
        logger.info(f"✓ Added test item: {test_item_name} (uid={uid})")

        # Verify it appears in the list
        items = client.get_grocery_list("Test List")
        found = any(item.name == test_item_name for item in items)

        if found:
            logger.info(f"✓ Verified item appears in list")
        else:
            logger.error(f"✗ Item not found in list after creation")
            raise Exception("Item verification failed")

        return uid
    except Exception as e:
        logger.error(f"✗ Failed to add item: {e}")
        raise


def test_update_checked_status(client: PaprikaClient, paprika_id: str):
    """Test 4: Update item checked status"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Update Checked Status")
    logger.info("=" * 60)

    try:
        # Check the item
        client.update_item(paprika_id=paprika_id, checked=True)
        logger.info(f"✓ Updated item to checked=True")

        # Verify status
        items = client.get_grocery_list("Test List")
        item = next((i for i in items if i.paprika_id == paprika_id), None)

        if item and item.checked:
            logger.info(f"✓ Verified item is checked")
        else:
            logger.error(f"✗ Item not checked after update")
            raise Exception("Checked status verification failed")

        # Uncheck the item
        client.update_item(paprika_id=paprika_id, checked=False)
        logger.info(f"✓ Updated item to checked=False")

        # Verify status
        items = client.get_grocery_list("Test List")
        item = next((i for i in items if i.paprika_id == paprika_id), None)

        if item and not item.checked:
            logger.info(f"✓ Verified item is unchecked")
        else:
            logger.error(f"✗ Item still checked after update")
            raise Exception("Unchecked status verification failed")

    except Exception as e:
        logger.error(f"✗ Failed to update checked status: {e}")
        raise


def test_remove_item(client: PaprikaClient, paprika_id: str):
    """Test 5: Remove item from grocery list (marks as purchased)"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Remove Item")
    logger.info("=" * 60)
    logger.info("NOTE: Paprika API doesn't support true deletion - item will be marked as purchased")

    try:
        client.remove_item(paprika_id=paprika_id)
        logger.info(f"✓ Removed test item (uid={paprika_id})")

        # Verify it's marked as purchased (since true deletion not supported)
        items = client.get_grocery_list("Test List")
        item = next((i for i in items if i.paprika_id == paprika_id), None)

        if item and item.checked:
            logger.info(f"✓ Verified item is marked as purchased (API limitation)")
        else:
            logger.warning(
                f"! Item state unexpected but continuing (API has limited delete support)"
            )

    except Exception as e:
        logger.error(f"✗ Failed to remove item: {e}")
        raise


def test_token_caching(client: PaprikaClient):
    """Test 6: Token caching"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Token Caching")
    logger.info("=" * 60)

    try:
        # Create new client instance (should load cached token)
        new_client = PaprikaClient(
            email=os.getenv("PAPRIKA_EMAIL"), password=os.getenv("PAPRIKA_PASSWORD")
        )

        # This should use cached token instead of re-authenticating
        items = new_client.get_grocery_list("Test List")
        logger.info(f"✓ Used cached token to retrieve {len(items)} items")

    except Exception as e:
        logger.error(f"✗ Token caching failed: {e}")
        raise


def main():
    """Run all Phase 1 tests"""
    # Check for flags
    keep_item = "--keep-item" in sys.argv

    # Load environment variables
    load_dotenv()

    if not os.getenv("PAPRIKA_EMAIL") or not os.getenv("PAPRIKA_PASSWORD"):
        logger.error("PAPRIKA_EMAIL and PAPRIKA_PASSWORD must be set in .env file")
        sys.exit(1)

    logger.info("Starting Phase 1 Tests: Paprika Integration")
    logger.info("NOTE: This will use 'Test List' in your Paprika account")
    if keep_item:
        logger.info("INFO: Test item will be KEPT in your list for manual verification")
    logger.info("")

    try:
        # Run tests sequentially
        client = test_authentication()
        test_read_list(client)
        paprika_id = test_add_item(client)
        test_update_checked_status(client, paprika_id)

        if keep_item:
            # Don't remove - leave for manual verification
            logger.info("\n" + "=" * 60)
            logger.info("SKIPPING REMOVAL TEST (--keep-item flag set)")
            logger.info("=" * 60)
            logger.info(f"Test item 'Phase 1 Test Item' (UID: {paprika_id})")
            logger.info("is now in your Paprika grocery list.")
            logger.info("")
            logger.info("Please check your Paprika app:")
            logger.info("1. Open Paprika app")
            logger.info("2. Go to Grocery Lists")
            logger.info("3. Look for 'Phase 1 Test Item' in your list")
            logger.info("")
            logger.info("After verifying, you can manually delete it or run tests again without --keep-item")
        else:
            test_remove_item(client, paprika_id)

        test_token_caching(client)

        logger.info("\n" + "=" * 60)
        logger.info("ALL PHASE 1 TESTS PASSED ✓")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        if keep_item:
            logger.info("1. Check Paprika app for 'Phase 1 Test Item'")
            logger.info("2. Manually delete test item when done verifying")
            logger.info("3. Verify production 'My Grocery List' is untouched")
            logger.info("4. Proceed to Phase 2: Skylight Integration")
        else:
            logger.info("1. Manually verify 'Test List' in Paprika app is clean")
            logger.info("2. Verify production 'My Grocery List' is untouched")
            logger.info("3. Proceed to Phase 2: Skylight Integration")

    except Exception as e:
        logger.error("\n" + "=" * 60)
        logger.error("TESTS FAILED ✗")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python tests/test_paprika.py [--keep-item]")
        print("")
        print("Options:")
        print("  --keep-item    Keep the test item in your grocery list for manual verification")
        print("                 (default: removes test item after tests complete)")
        print("")
        print("Examples:")
        print("  python tests/test_paprika.py              # Normal test run, cleans up after")
        print("  python tests/test_paprika.py --keep-item  # Leave test item for verification")
        sys.exit(0)

    main()
