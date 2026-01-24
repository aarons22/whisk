"""
Interactive Setup Wizard for Whisk

Guides users through credential entry, list discovery, and configuration
without requiring manual file editing.
"""

import getpass
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .config import ConfigManager, WhiskConfig, ListPairConfig
from .paprika_client import PaprikaClient
from .skylight_client import SkylightClient

logger = logging.getLogger(__name__)


class SetupWizard:
    """Interactive setup wizard for Whisk configuration"""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize setup wizard

        Args:
            config_dir: Directory for configuration files
        """
        self.config_manager = ConfigManager(config_dir)
        self.paprika_client: Optional[PaprikaClient] = None
        self.skylight_client: Optional[SkylightClient] = None

    def run(self, migrate: bool = False) -> int:
        """
        Run the complete setup wizard

        Args:
            migrate: If True, attempt to migrate from old configuration

        Returns:
            Exit code (0 for success)
        """
        try:
            print("🚀 Welcome to Whisk Setup!")
            print("Let's configure bidirectional sync for your Paprika ↔ Skylight grocery lists")
            print()

            if migrate:
                return self._run_migration()
            else:
                return self._run_fresh_setup()

        except KeyboardInterrupt:
            print("\n⏹️ Setup cancelled by user")
            return 130
        except Exception as e:
            logger.exception("Setup wizard failed")
            print(f"\n❌ Setup failed: {e}")
            print("Please try again or check the logs for details.")
            return 1

    def _run_fresh_setup(self) -> int:
        """Run fresh setup wizard"""
        print("📝 Step 1: Paprika Credentials")
        print("Enter your Paprika Recipe Manager account credentials:")
        paprika_creds = self._get_paprika_credentials()

        print("\n📱 Step 2: Skylight Credentials")
        print("Enter your Skylight Calendar account credentials:")
        skylight_creds = self._get_skylight_credentials()

        print("\n🔍 Step 3: Discovering Lists")
        paprika_lists, skylight_lists = self._discover_lists(paprika_creds, skylight_creds)

        print("\n🔗 Step 4: Configure List Pairs")
        list_pairs = self._configure_list_pairs(paprika_lists, skylight_lists)

        print("\n⚙️ Step 5: Sync Preferences")
        sync_config = self._configure_sync_preferences()

        print("\n💾 Step 6: Saving Configuration")
        config = WhiskConfig(
            list_pairs=list_pairs,
            sync_interval_seconds=sync_config['interval'],
            global_conflict_strategy=sync_config['strategy'],
            **paprika_creds,
            **skylight_creds
        )

        self.config_manager.save_config(config)

        print("\n🧪 Step 7: Testing Configuration")
        success = self._test_configuration(config)

        if success:
            print("\n✅ Setup completed successfully!")
            print(f"Configuration saved to: {self.config_manager.config_file}")
            print()
            print("Next steps:")
            print("  whisk sync           # Test one-time sync")
            print("  whisk start          # Start background daemon")
            print("  whisk status         # Check daemon status")
            return 0
        else:
            print("\n⚠️ Setup completed but configuration test failed")
            print("You may need to verify your credentials and try again.")
            return 1

    def _run_migration(self) -> int:
        """Run migration from old paprika-skylight-sync configuration"""
        print("📦 Migrating from paprika-skylight-sync...")

        # Look for old configuration files
        old_config_file = Path("config.yaml")
        old_env_file = Path(".env")

        if not old_config_file.exists() or not old_env_file.exists():
            print("❌ No existing configuration found to migrate")
            print("Run 'whisk setup' without --migrate for fresh setup")
            return 1

        try:
            # Load old configuration
            import yaml
            from dotenv import load_dotenv
            import os

            load_dotenv(old_env_file)
            with open(old_config_file, 'r') as f:
                old_config = yaml.safe_load(f)

            # Extract credentials
            paprika_creds = {
                'paprika_email': os.getenv('PAPRIKA_EMAIL', ''),
                'paprika_password': os.getenv('PAPRIKA_PASSWORD', ''),
            }
            skylight_creds = {
                'skylight_email': os.getenv('SKYLIGHT_EMAIL', ''),
                'skylight_password': os.getenv('SKYLIGHT_PASSWORD', ''),
                'skylight_frame_id': os.getenv('SKYLIGHT_FRAME_ID', ''),
            }

            # Convert to new format
            paprika_list = old_config.get('paprika', {}).get('list_name', 'My Grocery List')
            skylight_list = old_config.get('skylight', {}).get('list_name', 'Grocery List')
            conflict_strategy = old_config.get('sync', {}).get('conflict_strategy', 'newest_wins')
            sync_interval = old_config.get('sync_interval_seconds', 60)

            list_pairs = [ListPairConfig(
                paprika_list=paprika_list,
                skylight_list=skylight_list,
                conflict_strategy=conflict_strategy,
                enabled=True
            )]

            # Create new configuration
            config = WhiskConfig(
                list_pairs=list_pairs,
                sync_interval_seconds=sync_interval,
                global_conflict_strategy=conflict_strategy,
                **paprika_creds,
                **skylight_creds
            )

            # Save new configuration
            self.config_manager.save_config(config)

            print("✅ Migration completed successfully!")
            print(f"New configuration saved to: {self.config_manager.config_file}")
            print()
            print("Migrated settings:")
            print(f"  List pair: {paprika_list} ↔ {skylight_list}")
            print(f"  Conflict strategy: {conflict_strategy}")
            print(f"  Sync interval: {sync_interval} seconds")

            return 0

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            print("Try running 'whisk setup' without --migrate for fresh setup")
            return 1

    def _get_paprika_credentials(self) -> Dict[str, str]:
        """Get and validate Paprika credentials"""
        while True:
            print()
            email = input("Paprika email: ").strip()
            if not email:
                print("❌ Email cannot be empty")
                continue

            password = getpass.getpass("Paprika password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                continue

            print("🔐 Testing Paprika authentication...")
            if self._test_paprika_auth(email, password):
                print("✅ Paprika authentication successful")
                return {
                    'paprika_email': email,
                    'paprika_password': password
                }
            else:
                print("❌ Authentication failed. Please check your credentials and try again.")
                retry = input("Try again? (y/n): ").strip().lower()
                if retry != 'y':
                    raise Exception("Paprika authentication required")

    def _get_skylight_credentials(self) -> Dict[str, str]:
        """Get and validate Skylight credentials"""
        while True:
            print()
            email = input("Skylight email: ").strip()
            if not email:
                print("❌ Email cannot be empty")
                continue

            password = getpass.getpass("Skylight password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                continue

            frame_id = input("Skylight frame ID: ").strip()
            if not frame_id:
                print("❌ Frame ID cannot be empty")
                print("💡 Tip: Find your frame ID at https://app.ourskylight.com/frames")
                continue

            print("🔐 Testing Skylight authentication...")
            if self._test_skylight_auth(email, password, frame_id):
                print("✅ Skylight authentication successful")
                return {
                    'skylight_email': email,
                    'skylight_password': password,
                    'skylight_frame_id': frame_id
                }
            else:
                print("❌ Authentication failed. Please check your credentials and try again.")
                print("💡 Make sure your frame ID is correct")
                retry = input("Try again? (y/n): ").strip().lower()
                if retry != 'y':
                    raise Exception("Skylight authentication required")

    def _test_paprika_auth(self, email: str, password: str) -> bool:
        """Test Paprika authentication"""
        try:
            self.paprika_client = PaprikaClient(email, password)
            self.paprika_client.authenticate()
            return True
        except Exception as e:
            logger.debug(f"Paprika auth test failed: {e}")
            return False

    def _test_skylight_auth(self, email: str, password: str, frame_id: str) -> bool:
        """Test Skylight authentication"""
        try:
            self.skylight_client = SkylightClient(email, password, frame_id)
            self.skylight_client.authenticate()
            return True
        except Exception as e:
            logger.debug(f"Skylight auth test failed: {e}")
            return False

    def _discover_lists(self, paprika_creds: Dict[str, str], skylight_creds: Dict[str, str]) -> Tuple[List[str], List[str]]:
        """Discover available lists from both services"""
        paprika_lists = []
        skylight_lists = []

        print("📋 Discovering Paprika lists...")
        try:
            if not self.paprika_client:
                self.paprika_client = PaprikaClient(
                    paprika_creds['paprika_email'],
                    paprika_creds['paprika_password']
                )
                self.paprika_client.authenticate()

            paprika_lists = self.paprika_client.get_grocery_lists()
            paprika_list_names = [lst['name'] for lst in paprika_lists]
            print(f"✅ Found {len(paprika_list_names)} Paprika lists:")
            for i, name in enumerate(paprika_list_names, 1):
                print(f"  {i}. {name}")

        except Exception as e:
            logger.error(f"Failed to discover Paprika lists: {e}")
            print("⚠️ Could not discover Paprika lists - you'll need to enter names manually")
            paprika_list_names = []

        print("\n📋 Discovering Skylight lists...")
        try:
            if not self.skylight_client:
                self.skylight_client = SkylightClient(
                    skylight_creds['skylight_email'],
                    skylight_creds['skylight_password'],
                    skylight_creds['skylight_frame_id']
                )
                self.skylight_client.authenticate()

            skylight_lists = self.skylight_client.get_lists()
            skylight_list_names = [lst['name'] for lst in skylight_lists]
            print(f"✅ Found {len(skylight_list_names)} Skylight lists:")
            for i, name in enumerate(skylight_list_names, 1):
                print(f"  {i}. {name}")

        except Exception as e:
            logger.error(f"Failed to discover Skylight lists: {e}")
            print("⚠️ Could not discover Skylight lists - you'll need to enter names manually")
            skylight_list_names = []

        return paprika_list_names, skylight_list_names

    def _configure_list_pairs(self, paprika_lists: List[str], skylight_lists: List[str]) -> List[ListPairConfig]:
        """Configure list pairs interactively"""
        pairs = []

        print("Create list pairs to sync between Paprika and Skylight:")
        print("Each pair syncs one Paprika list with one Skylight list.")
        print()

        while True:
            print(f"🔗 List Pair #{len(pairs) + 1}")

            # Get Paprika list
            paprika_list = self._select_or_enter_list(
                "Paprika list",
                paprika_lists,
                "Enter the exact name of your Paprika grocery list"
            )

            # Get Skylight list
            skylight_list = self._select_or_enter_list(
                "Skylight list",
                skylight_lists,
                "Enter the exact name of your Skylight grocery list"
            )

            # Get conflict strategy
            print("\nConflict resolution strategy:")
            print("  1. newest_wins - Most recently modified item wins (recommended)")
            print("  2. paprika_wins - Paprika always wins conflicts")
            print("  3. skylight_wins - Skylight always wins conflicts")

            while True:
                choice = input("Choose strategy (1-3): ").strip()
                if choice == "1":
                    strategy = "newest_wins"
                    break
                elif choice == "2":
                    strategy = "paprika_wins"
                    break
                elif choice == "3":
                    strategy = "skylight_wins"
                    break
                else:
                    print("❌ Please enter 1, 2, or 3")

            # Create pair
            pair = ListPairConfig(
                paprika_list=paprika_list,
                skylight_list=skylight_list,
                conflict_strategy=strategy,
                enabled=True
            )
            pairs.append(pair)

            print(f"\n✅ Added pair: {paprika_list} ↔ {skylight_list} ({strategy})")

            # Ask for another pair
            if len(pairs) >= 10:  # Reasonable limit
                print("\n⚠️ Maximum of 10 list pairs reached")
                break

            another = input("\nAdd another list pair? (y/n): ").strip().lower()
            if another != 'y':
                break
            print()

        if not pairs:
            raise Exception("At least one list pair must be configured")

        return pairs

    def _select_or_enter_list(self, service_name: str, available_lists: List[str], manual_prompt: str) -> str:
        """Select from available lists or enter manually"""
        if available_lists:
            print(f"\nAvailable {service_name}s:")
            for i, name in enumerate(available_lists, 1):
                print(f"  {i}. {name}")
            print(f"  {len(available_lists) + 1}. Enter custom name")

            while True:
                choice = input(f"Select {service_name} (1-{len(available_lists) + 1}): ").strip()
                try:
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(available_lists):
                        return available_lists[choice_num - 1]
                    elif choice_num == len(available_lists) + 1:
                        break  # Fall through to manual entry
                    else:
                        print(f"❌ Please enter a number between 1 and {len(available_lists) + 1}")
                except ValueError:
                    print("❌ Please enter a valid number")

        # Manual entry
        while True:
            list_name = input(f"{manual_prompt}: ").strip()
            if list_name:
                return list_name
            print("❌ List name cannot be empty")

    def _configure_sync_preferences(self) -> Dict[str, Any]:
        """Configure sync preferences"""
        print("⏱️ Sync interval (how often to check for changes):")
        print("  1. 30 seconds (frequent)")
        print("  2. 60 seconds (recommended)")
        print("  3. 5 minutes (battery-friendly)")
        print("  4. 15 minutes (conservative)")
        print("  5. Custom interval")

        while True:
            choice = input("Choose sync interval (1-5): ").strip()
            if choice == "1":
                interval = 30
                break
            elif choice == "2":
                interval = 60
                break
            elif choice == "3":
                interval = 300
                break
            elif choice == "4":
                interval = 900
                break
            elif choice == "5":
                while True:
                    try:
                        interval = int(input("Enter custom interval in seconds (minimum 30): "))
                        if interval >= 30:
                            break
                        else:
                            print("❌ Minimum interval is 30 seconds")
                    except ValueError:
                        print("❌ Please enter a valid number")
                break
            else:
                print("❌ Please enter 1, 2, 3, 4, or 5")

        print(f"\n🔄 Default conflict resolution strategy:")
        print("  1. newest_wins - Most recently modified wins (recommended)")
        print("  2. paprika_wins - Paprika always wins")
        print("  3. skylight_wins - Skylight always wins")
        print("(Individual list pairs can override this)")

        while True:
            choice = input("Choose default strategy (1-3): ").strip()
            if choice == "1":
                strategy = "newest_wins"
                break
            elif choice == "2":
                strategy = "paprika_wins"
                break
            elif choice == "3":
                strategy = "skylight_wins"
                break
            else:
                print("❌ Please enter 1, 2, or 3")

        return {
            'interval': interval,
            'strategy': strategy
        }

    def _test_configuration(self, config: WhiskConfig) -> bool:
        """Test the configuration by attempting to read lists"""
        try:
            print("🔍 Testing list access...")

            # Test each list pair
            for i, pair in enumerate(config.list_pairs, 1):
                print(f"  Testing pair {i}: {pair.paprika_list} ↔ {pair.skylight_list}")

                # Test Paprika list
                try:
                    if not self.paprika_client:
                        self.paprika_client = PaprikaClient(
                            config.paprika_email,
                            config.paprika_password
                        )
                        self.paprika_client.authenticate()

                    items = self.paprika_client.get_grocery_list(pair.paprika_list)
                    print(f"    ✅ Paprika '{pair.paprika_list}': {len(items)} items")

                except Exception as e:
                    print(f"    ❌ Paprika '{pair.paprika_list}': {e}")
                    return False

                # Test Skylight list
                try:
                    if not self.skylight_client:
                        self.skylight_client = SkylightClient(
                            config.skylight_email,
                            config.skylight_password,
                            config.skylight_frame_id
                        )
                        self.skylight_client.authenticate()

                    items = self.skylight_client.get_grocery_list(pair.skylight_list)
                    print(f"    ✅ Skylight '{pair.skylight_list}': {len(items)} items")

                except Exception as e:
                    print(f"    ❌ Skylight '{pair.skylight_list}': {e}")
                    return False

            print("✅ All list pairs accessible")
            return True

        except Exception as e:
            logger.error(f"Configuration test failed: {e}")
            print(f"❌ Configuration test failed: {e}")
            return False