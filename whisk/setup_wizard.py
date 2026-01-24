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

    def run(self) -> int:
        """
        Run the complete setup wizard

        Returns:
            Exit code (0 for success)
        """
        try:
            print("🚀 Welcome to Whisk Setup!")
            print("Let's configure bidirectional sync for your Paprika ↔ Skylight grocery lists")
            print()

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

        print("\n🔗 Step 3: Configure List Pairs")
        list_pairs = self._configure_list_pairs(paprika_lists, skylight_lists)

        print("\n⚙️ Step 4: Sync Preferences")
        sync_config = self._configure_sync_preferences()

        print("\n💾 Step 5: Saving Configuration")
        config = WhiskConfig(
            list_pairs=list_pairs,
            sync_interval_seconds=sync_config['interval'],
            **paprika_creds,
            **skylight_creds
        )

        self.config_manager.save_config(config)

        print("\n🧪 Step 6: Testing Configuration")
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
        """Get and validate Skylight credentials with frame discovery"""
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

            print("🔐 Testing Skylight authentication and discovering frames...")

            # Test auth and discover frames
            frames = self._test_skylight_auth_and_discover_frames(email, password)
            if frames is None:
                print("❌ Authentication failed. Please check your credentials and try again.")
                retry = input("Try again? (y/n): ").strip().lower()
                if retry != 'y':
                    raise Exception("Skylight authentication required")
                continue

            if not frames:
                print("❌ No frames found for this account. Please make sure you have a Skylight frame set up.")
                retry = input("Try again? (y/n): ").strip().lower()
                if retry != 'y':
                    raise Exception("Skylight frame required")
                continue

            # Let user choose frame
            if len(frames) == 1:
                frame = frames[0]
                frame_id = frame.get('id')
                frame_name = frame.get('attributes', {}).get('name', 'Unnamed Frame')
                print(f"✅ Found your Skylight frame: {frame_name}")
            else:
                print(f"✅ Found {len(frames)} Skylight frames:")
                for i, frame in enumerate(frames, 1):
                    frame_name = frame.get('attributes', {}).get('name', 'Unnamed Frame')
                    frame_id = frame.get('id', 'Unknown ID')
                    print(f"  {i}. {frame_name} (ID: {frame_id})")

                while True:
                    try:
                        choice = int(input(f"Choose frame (1-{len(frames)}): ").strip())
                        if 1 <= choice <= len(frames):
                            frame = frames[choice - 1]
                            frame_id = frame.get('id')
                            frame_name = frame.get('attributes', {}).get('name', 'Unnamed Frame')
                            print(f"Selected: {frame_name}")
                            break
                        else:
                            print(f"❌ Please enter a number between 1 and {len(frames)}")
                    except ValueError:
                        print("❌ Please enter a valid number")

            return {
                'skylight_email': email,
                'skylight_password': password,
                'skylight_frame_id': frame_id
            }

    def _test_paprika_auth(self, email: str, password: str) -> bool:
        """Test Paprika authentication"""
        try:
            token_cache_file = self.config_manager.config_dir / "paprika_token"
            self.paprika_client = PaprikaClient(email, password, str(token_cache_file))
            self.paprika_client.authenticate()
            return True
        except Exception as e:
            logger.debug(f"Paprika auth test failed: {e}")
            return False

    def _test_skylight_auth_and_discover_frames(self, email: str, password: str) -> Optional[List[Dict[str, Any]]]:
        """Test Skylight authentication and discover available frames"""
        try:
            # Create a temporary client with a dummy frame ID for authentication testing
            token_cache_file = self.config_manager.config_dir / "skylight_token_temp"
            temp_client = SkylightClient(email, password, "temp", str(token_cache_file))
            temp_client.authenticate()

            # Now get frames using the authenticated client
            frames = temp_client.get_frames()

            # Clean up temp token file
            if token_cache_file.exists():
                token_cache_file.unlink()

            return frames
        except Exception as e:
            logger.debug(f"Skylight auth and frame discovery failed: {e}")
            return None

    def _discover_lists(self, paprika_creds: Dict[str, str], skylight_creds: Dict[str, str]) -> Tuple[List[str], List[str]]:
        """Discover available lists from both services"""
        paprika_lists = []
        skylight_lists = []

        print("📋 Discovering Paprika lists...")
        try:
            if not self.paprika_client:
                token_cache_file = self.config_manager.config_dir / "paprika_token"
                self.paprika_client = PaprikaClient(
                    paprika_creds['paprika_email'],
                    paprika_creds['paprika_password'],
                    str(token_cache_file)
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
            # Create client with the correct frame ID
            token_cache_file = self.config_manager.config_dir / "skylight_token"
            self.skylight_client = SkylightClient(
                skylight_creds['skylight_email'],
                skylight_creds['skylight_password'],
                skylight_creds['skylight_frame_id'],
                str(token_cache_file)
            )
            self.skylight_client.authenticate()

            skylight_lists = self.skylight_client.get_lists()
            # Filter to only shopping lists (not to-do lists)
            shopping_lists = [lst for lst in skylight_lists
                             if lst.get('attributes', {}).get('kind') == 'shopping']
            skylight_list_names = [lst.get('attributes', {}).get('label', 'Unnamed List')
                                  for lst in shopping_lists]
            print(f"✅ Found {len(skylight_list_names)} Skylight shopping lists:")
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

            # Create pair with default strategy
            pair = ListPairConfig(
                paprika_list=paprika_list,
                skylight_list=skylight_list,
                enabled=True
            )
            pairs.append(pair)

            print(f"\n✅ Added pair: {paprika_list} ↔ {skylight_list}")

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

        return {
            'interval': interval
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
                        token_cache_file = self.config_manager.config_dir / "paprika_token"
                        self.paprika_client = PaprikaClient(
                            config.paprika_email,
                            config.paprika_password,
                            str(token_cache_file)
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
                        token_cache_file = self.config_manager.config_dir / "skylight_token"
                        self.skylight_client = SkylightClient(
                            config.skylight_email,
                            config.skylight_password,
                            config.skylight_frame_id,
                            str(token_cache_file)
                        )
                        self.skylight_client.authenticate()

                    items = self.skylight_client.get_list_items(pair.skylight_list)
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