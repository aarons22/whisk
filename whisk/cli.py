"""
Whisk CLI - Command Line Interface

Modern CLI for managing Paprika ↔ Skylight grocery list sync with
support for multiple list pairs, interactive setup, and daemon management.
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import Optional

from .config import ConfigManager, WhiskConfig

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Setup basic logging for CLI commands"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def cmd_setup(args) -> int:
    """Interactive setup wizard"""
    from .setup_wizard import SetupWizard

    setup_wizard = SetupWizard(args.config_dir)
    return setup_wizard.run()


def cmd_sync(args) -> int:
    """One-time sync of configured list pairs"""
    from .multi_sync_engine import WhiskSyncEngine
    from .config import ConfigManager

    try:
        config_manager = ConfigManager()
        if not config_manager.config_exists():
            print("❌ No configuration found. Run 'whisk setup' first.")
            return 1

        config = config_manager.load_config()
        sync_engine = WhiskSyncEngine(config, config_manager.config_dir)

        if args.list:
            # Sync specific list pair - find matching pair
            matching_pair = None
            for pair in config.list_pairs:
                if args.list in [pair.paprika_list, pair.skylight_list]:
                    matching_pair = pair
                    break

            if not matching_pair:
                print(f"❌ List pair not found for: {args.list}")
                print("Available list pairs:")
                for i, pair in enumerate(config.list_pairs, 1):
                    status = "✅" if pair.enabled else "❌"
                    print(f"  {i}. {status} {pair.paprika_list} ↔ {pair.skylight_list}")
                return 1

            print(f"🔄 Syncing list pair: {matching_pair.paprika_list} ↔ {matching_pair.skylight_list}")
            if args.dry_run:
                print("📋 Dry run mode - no changes will be made")

            result = sync_engine.sync_single_pair(
                matching_pair.paprika_list,
                matching_pair.skylight_list,
                dry_run=args.dry_run
            )

            if result.success:
                changes = result.get_total_changes()
                if changes > 0:
                    print(f"✅ Sync completed: {changes} changes made")
                    if args.dry_run:
                        print("   (Dry run - changes were simulated)")
                else:
                    print("✅ Sync completed: No changes needed")
                return 0
            else:
                print(f"❌ Sync failed: {result.error}")
                return 1
        else:
            # Sync all pairs
            enabled_pairs = sync_engine.get_enabled_pairs()
            if not enabled_pairs:
                print("❌ No enabled list pairs found")
                return 1

            print(f"🔄 Syncing {len(enabled_pairs)} list pair(s)...")
            if args.dry_run:
                print("📋 Dry run mode - no changes will be made")

            result = sync_engine.sync_all_pairs(dry_run=args.dry_run)

            if result.success:
                print(f"✅ Sync completed: {result.successful_pairs}/{result.total_pairs} pairs successful")
                if result.total_changes > 0:
                    print(f"   {result.total_changes} total changes made")
                    if args.dry_run:
                        print("   (Dry run - changes were simulated)")
                if result.total_conflicts_resolved > 0:
                    print(f"   {result.total_conflicts_resolved} conflicts resolved")
                if result.failed_pairs > 0:
                    print(f"⚠️  {result.failed_pairs} pairs had errors:")
                    for error in result.errors:
                        print(f"     {error}")
                return 0
            else:
                print(f"❌ Sync failed: {result.failed_pairs}/{result.total_pairs} pairs failed")
                for error in result.errors:
                    print(f"   {error}")
                return 1

    except Exception as e:
        print(f"❌ Sync failed: {e}")
        return 1


def cmd_start(args) -> int:
    """Start daemon for continuous sync"""
    from .daemon import DaemonManager
    from .config import ConfigManager

    try:
        config_manager = ConfigManager()
        if not config_manager.config_exists():
            print("❌ No configuration found. Run 'whisk setup' first.")
            return 1

        config = config_manager.load_config()

        # Validate that we have enabled pairs
        enabled_pairs = [p for p in config.list_pairs if p.enabled]
        if not enabled_pairs:
            print("❌ No enabled list pairs found. Run 'whisk setup' to configure list pairs.")
            return 1

        print(f"🚀 Starting Whisk daemon for {len(enabled_pairs)} list pair(s)...")
        for pair in enabled_pairs:
            print(f"  • {pair.paprika_list} ↔ {pair.skylight_list}")

        daemon = DaemonManager(config, config_manager.config_dir)
        return daemon.start_daemon(foreground=args.foreground)

    except Exception as e:
        print(f"❌ Failed to start daemon: {e}")
        return 1


def cmd_stop(args) -> int:
    """Stop running daemon"""
    from .daemon import DaemonManager
    from .config import ConfigManager

    try:
        config_manager = ConfigManager()
        config = None
        if config_manager.config_exists():
            config = config_manager.load_config()

        daemon = DaemonManager(config, config_manager.config_dir)
        return daemon.stop_daemon()

    except Exception as e:
        print(f"❌ Failed to stop daemon: {e}")
        return 1


def cmd_status(args) -> int:
    """Show daemon status and last sync info"""
    from .daemon import DaemonManager
    from .config import ConfigManager

    try:
        config_manager = ConfigManager()
        config = None
        if config_manager.config_exists():
            config = config_manager.load_config()

        daemon = DaemonManager(config, config_manager.config_dir)
        status = daemon.get_status()

        if status['running']:
            print("✅ Whisk daemon is running")
            print(f"   PID: {status.get('pid')}")
            print(f"   Started: {status.get('started')}")
            print(f"   Memory: {status.get('memory_mb')}MB")
            if config:
                enabled_pairs = [p for p in config.list_pairs if p.enabled]
                print(f"   Syncing: {len(enabled_pairs)} list pair(s)")
        else:
            print("⏹️ Whisk daemon is not running")
            if 'error' in status:
                print(f"   Error: {status['error']}")

        return 0

    except Exception as e:
        print(f"❌ Failed to get status: {e}")
        return 1


def cmd_lists(args) -> int:
    """Show available or configured lists"""
    from .config import ConfigManager

    try:
        config_manager = ConfigManager()

        if args.service == "paprika":
            print("📋 Discovering Paprika Lists...")

            if not config_manager.config_exists():
                print("❌ No configuration found. Run 'whisk setup' first.")
                return 1

            config = config_manager.load_config()

            # Import here to avoid circular imports
            from .paprika_client import PaprikaClient

            paprika_token_cache = config_manager.config_dir / config.paprika_token_cache
            client = PaprikaClient(
                config.paprika_email,
                config.paprika_password,
                str(paprika_token_cache)
            )
            client.authenticate()

            lists = client.get_grocery_lists()
            print(f"Found {len(lists)} Paprika grocery lists:")
            for i, lst in enumerate(lists, 1):
                name = lst.get('name', 'Unnamed List')
                is_default = " (default)" if lst.get('is_default', False) else ""
                print(f"  {i}. {name}{is_default}")
            return 0

        elif args.service == "skylight":
            print("📋 Discovering Skylight Lists...")

            if not config_manager.config_exists():
                print("❌ No configuration found. Run 'whisk setup' first.")
                return 1

            config = config_manager.load_config()

            # Import here to avoid circular imports
            from .skylight_client import SkylightClient

            skylight_token_cache = config_manager.config_dir / config.skylight_token_cache
            client = SkylightClient(
                config.skylight_email,
                config.skylight_password,
                config.skylight_frame_id,
                str(skylight_token_cache)
            )
            client.authenticate()

            lists = client.get_lists()
            shopping_lists = [lst for lst in lists
                             if lst.get('attributes', {}).get('kind') == 'shopping']
            print(f"Found {len(shopping_lists)} Skylight grocery lists:")
            for i, lst in enumerate(shopping_lists, 1):
                name = lst.get('attributes', {}).get('label', 'Unnamed List')
                is_default = " (default)" if lst.get('attributes', {}).get('default_grocery_list', False) else ""
                print(f"  {i}. {name}{is_default}")
            return 0

        else:
            # Show configured pairs
            if not config_manager.config_exists():
                print("❌ No configuration found. Run 'whisk setup' first.")
                return 1

            config = config_manager.load_config()
            print("📋 Configured List Pairs:")

            if not config.list_pairs:
                print("  No list pairs configured. Run 'whisk setup' to add pairs.")
                return 0

            # Try to get status information
            try:
                from .multi_sync_engine import WhiskSyncEngine
                sync_engine = WhiskSyncEngine(config, config_manager.config_dir)
                pair_statuses = sync_engine.get_pair_status()

                for i, status in enumerate(pair_statuses, 1):
                    enabled_icon = "✅" if status['enabled'] else "❌"
                    strategy = status['conflict_strategy']

                    if status.get('status') == 'ready':
                        paprika_count = status.get('paprika_count', '?')
                        skylight_count = status.get('skylight_count', '?')
                        print(f"  {i}. {enabled_icon} {status['paprika_list']} ({paprika_count} items) ↔ "
                              f"{status['skylight_list']} ({skylight_count} items) [{strategy}]")
                    else:
                        print(f"  {i}. {enabled_icon} {status['paprika_list']} ↔ {status['skylight_list']} "
                              f"[{strategy}] - {status.get('status', 'unknown')}")

            except Exception as e:
                # Fall back to basic display
                logger.debug(f"Could not get pair status: {e}")
                for i, pair in enumerate(config.list_pairs, 1):
                    status = "✅" if pair.enabled else "❌"
                    print(f"  {i}. {status} {pair.paprika_list} ↔ {pair.skylight_list} ({pair.conflict_strategy})")

            return 0

    except Exception as e:
        print(f"❌ Failed to list: {e}")
        return 1


def cmd_config(args) -> int:
    """Configuration management"""
    try:
        config_manager = ConfigManager()

        if args.action == "show":
            if not config_manager.config_exists():
                print("❌ No configuration found. Run 'whisk setup' first.")
                return 1

            config = config_manager.load_config()
            print("⚙️ Current Whisk Configuration:")
            print(f"  Sync interval: {config.sync_interval_seconds} seconds")
            print(f"  Global conflict strategy: {config.global_conflict_strategy}")
            print(f"  List pairs: {len(config.list_pairs)}")

            for i, pair in enumerate(config.list_pairs, 1):
                status = "enabled" if pair.enabled else "disabled"
                print(f"    {i}. {pair.paprika_list} ↔ {pair.skylight_list} ({status})")

            return 0

        elif args.action == "check":
            if not config_manager.config_exists():
                print("❌ No configuration found. Run 'whisk setup' first.")
                return 1

            print("🔍 Validating configuration...")
            try:
                config = config_manager.load_config()
                print("✅ Configuration is valid")
                return 0
            except Exception as e:
                print(f"❌ Configuration validation failed: {e}")
                return 1

        else:
            print(f"❌ Unknown config action: {args.action}")
            return 1

    except Exception as e:
        print(f"❌ Config command failed: {e}")
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser"""
    parser = argparse.ArgumentParser(
        prog="whisk",
        description="Bidirectional sync for Paprika and Skylight grocery lists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  whisk setup                    # Interactive setup wizard
  whisk sync                     # One-time sync of all pairs
  whisk sync --list "Groceries"  # Sync specific list pair
  whisk start                    # Start daemon mode
  whisk stop                     # Stop daemon
  whisk status                   # Show daemon status
  whisk lists                    # Show configured list pairs
  whisk lists paprika            # Show available Paprika lists
  whisk config show              # Display current configuration

For detailed help on any command, use: whisk <command> --help
        """
    )

    parser.add_argument(
        "--version",
        action="version",
        version="whisk 1.0.0"
    )

    # Global options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--config-dir",
        type=Path,
        help="Directory containing configuration files (default: current directory)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Interactive setup wizard",
        description="Run interactive setup wizard to configure credentials and list pairs"
    )

    # Sync command
    sync_parser = subparsers.add_parser(
        "sync",
        help="One-time sync of configured list pairs",
        description="Perform one-time sync of all or specific list pairs"
    )
    sync_parser.add_argument(
        "--list",
        help="Sync only the specified list pair (by Paprika or Skylight list name)"
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes"
    )

    # Start daemon
    start_parser = subparsers.add_parser(
        "start",
        help="Start daemon for continuous sync",
        description="Start background daemon to sync continuously at configured intervals"
    )
    start_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground instead of background"
    )

    # Stop daemon
    subparsers.add_parser(
        "stop",
        help="Stop running daemon",
        description="Stop background sync daemon"
    )

    # Status
    subparsers.add_parser(
        "status",
        help="Show daemon status and last sync info",
        description="Display current daemon status and information about last sync"
    )

    # Lists command
    lists_parser = subparsers.add_parser(
        "lists",
        help="Show available or configured lists",
        description="Show configured list pairs or discover available lists from services"
    )
    lists_parser.add_argument(
        "service",
        nargs="?",
        choices=["paprika", "skylight"],
        help="Show available lists from specific service (paprika or skylight)"
    )

    # Config command
    config_parser = subparsers.add_parser(
        "config",
        help="Configuration management",
        description="View or validate configuration"
    )
    config_parser.add_argument(
        "action",
        choices=["show", "check"],
        help="Configuration action to perform"
    )

    return parser


def main() -> int:
    """Main CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    # Handle no command
    if not args.command:
        parser.print_help()
        return 0

    # Route to command handlers
    command_handlers = {
        "setup": cmd_setup,
        "sync": cmd_sync,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "lists": cmd_lists,
        "config": cmd_config,
    }

    handler = command_handlers.get(args.command)
    if handler:
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\n⏹️ Cancelled by user")
            return 130  # Standard exit code for Ctrl+C
        except Exception as e:
            logger.exception("Unexpected error in command handler")
            print(f"❌ Unexpected error: {e}")
            return 1
    else:
        print(f"❌ Unknown command: {args.command}")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())