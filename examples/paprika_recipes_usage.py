#!/usr/bin/env python3
"""
Example script demonstrating Paprika Recipe API usage

This script shows how to use the PaprikaClient to:
- List all recipes (lightweight)
- Get recipe details
- Create new recipes
- Update existing recipes
- Delete recipes (soft delete)

Note: You'll need valid Paprika credentials in a .env file or environment variables.
"""

import os
import sys
from dotenv import load_dotenv

# Add parent directory to path for local development
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whisk.paprika_client import PaprikaClient


def main():
    # Load credentials from .env file
    load_dotenv()
    email = os.getenv("PAPRIKA_EMAIL")
    password = os.getenv("PAPRIKA_PASSWORD")

    if not email or not password:
        print("Error: PAPRIKA_EMAIL and PAPRIKA_PASSWORD must be set")
        print("Create a .env file with these variables or set them in your environment")
        return 1

    # Initialize client
    print("Initializing Paprika client...")
    client = PaprikaClient(email, password)

    try:
        # Example 1: List all recipes (lightweight - only UIDs and hashes)
        print("\n=== Listing all recipes (lightweight) ===")
        recipes = client.list_recipes()
        print(f"Found {len(recipes)} recipes")
        if recipes:
            print("First recipe:")
            print(f"  UID: {recipes[0]['uid']}")
            print(f"  Hash: {recipes[0]['hash'][:16]}...")

        # Example 2: Get full recipe details
        if recipes:
            print("\n=== Getting recipe details ===")
            recipe_uid = recipes[0]["uid"]
            recipe = client.get_recipe(recipe_uid)
            print(f"Recipe: {recipe['name']}")
            print(f"  Rating: {recipe['rating']}/5")
            print(f"  Categories: {', '.join(recipe.get('categories', []))}")
            print(f"  Prep time: {recipe.get('prep_time', 'N/A')}")
            print(f"  Cook time: {recipe.get('cook_time', 'N/A')}")
            if recipe.get("ingredients"):
                print(f"  Ingredients (first 100 chars): {recipe['ingredients'][:100]}...")

        # Example 3: Create a new recipe
        print("\n=== Creating a new recipe ===")
        new_recipe = {
            "name": "Example Test Recipe",
            "description": "This is a test recipe created by the example script",
            "ingredients": "1 cup test ingredient\n2 tbsp example spice\n3 test items",
            "directions": "1. Mix ingredients\n2. Cook thoroughly\n3. Serve hot",
            "prep_time": "10 min",
            "cook_time": "20 min",
            "total_time": "30 min",
            "servings": "4 servings",
            "rating": 4,
            "categories": ["Test", "Examples"],
            "source": "Whisk Example Script",
        }
        created_uid = client.create_recipe(new_recipe)
        print(f"Created recipe with UID: {created_uid}")

        # Example 4: Update the recipe
        print("\n=== Updating the recipe ===")
        updated_recipe = client.get_recipe(created_uid)
        updated_recipe["rating"] = 5
        updated_recipe["notes"] = "Updated by example script"
        client.update_recipe(created_uid, updated_recipe)
        print(f"Updated recipe: {updated_recipe['name']}")

        # Example 5: Delete the recipe (soft delete)
        print("\n=== Deleting the recipe (soft delete) ===")
        client.delete_recipe(created_uid)
        print(f"Deleted recipe: {created_uid}")

        # Verify it's marked as deleted
        deleted_recipe = client.get_recipe(created_uid)
        print(f"Recipe in_trash status: {deleted_recipe['in_trash']}")

        print("\n✅ All examples completed successfully!")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
