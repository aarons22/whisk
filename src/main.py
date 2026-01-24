#!/usr/bin/env python3
"""
Paprika ↔ Skylight Grocery List Sync - Main Entry Point

This is the main entry point for the grocery list sync automation.
Supports three modes:
  --dry-run: Test sync without making changes
  --once: Run sync once and exit
  --daemon: Run continuously with scheduled intervals (default)

Configuration:
  .env file: Credentials (PAPRIKA_EMAIL, SKYLIGHT_EMAIL, etc.)
  config.yaml: Settings (sync intervals, list names, logging)
"""

import argparse
import logging
import logging.handlers
import os
import signal
import sys
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from paprika_client import PaprikaClient
from skylight_client import SkylightClient
from state_manager import StateManager
from sync_engine import SyncEngine

# Global scheduler for signal handling
scheduler: Optional[BlockingScheduler] = None
sync_engine: Optional[SyncEngine] = None
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """
    Load configuration from .env and config.yaml files

    Returns:
        Combined configuration dictionary

    Raises:
        SystemExit: If configuration is invalid or files are missing
    """
    # Load environment variables
    env_path = project_root / ".env"
    if not env_path.exists():
        print(f"❌ Error: .env file not found at {env_path}")
        print("   Please copy .env.example to .env and fill in your credentials")
        sys.exit(1)

    load_dotenv(env_path)

    # Load YAML configuration
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print(f"❌ Error: config.yaml not found at {config_path}")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"❌ Error parsing config.yaml: {e}")
        sys.exit(1)

    # Validate required environment variables
    required_env_vars = [
        'PAPRIKA_EMAIL', 'PAPRIKA_PASSWORD',
        'SKYLIGHT_EMAIL', 'SKYLIGHT_PASSWORD',
        'SKYLIGHT_FRAME_ID'
    ]

    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"❌ Error: Missing required environment variables in .env:")
        for var in missing_vars:
            print(f"   {var}")
        print("\n   Please check your .env file against .env.example")
        sys.exit(1)

    # Combine configuration
    config = {
        'credentials': {
            'paprika_email': os.getenv('PAPRIKA_EMAIL'),
            'paprika_password': os.getenv('PAPRIKA_PASSWORD'),
            'skylight_email': os.getenv('SKYLIGHT_EMAIL'),
            'skylight_password': os.getenv('SKYLIGHT_PASSWORD'),
            'skylight_frame_id': os.getenv('SKYLIGHT_FRAME_ID')
        },
        **yaml_config
    }

    return config


def setup_logging(config: Dict[str, Any]) -> None:
    """
    Configure logging with file rotation and console output

    Args:
        config: Configuration dictionary with logging settings
    """
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    log_file = project_root / log_config.get('file', 'sync.log')
    max_bytes = log_config.get('max_bytes', 10485760)  # 10 MB
    backup_count = log_config.get('backup_count', 3)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()  # Remove any existing handlers

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Ensure log file is created
        log_file.parent.mkdir(exist_ok=True)

    except Exception as e:
        logger.warning(f"Could not set up file logging: {e}")
        logger.info("Continuing with console logging only")


def initialize_clients(config: Dict[str, Any]) -> tuple[PaprikaClient, SkylightClient, StateManager]:
    """
    Initialize API clients and state manager

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (paprika_client, skylight_client, state_manager)

    Raises:
        SystemExit: If initialization fails
    """
    try:
        # Initialize Paprika client
        logger.info("Initializing Paprika client...")
        paprika_client = PaprikaClient(
            email=config['credentials']['paprika_email'],
            password=config['credentials']['paprika_password']
        )

        # Test authentication
        paprika_client.authenticate()
        logger.info("✅ Paprika client authenticated successfully")

        # Initialize Skylight client
        logger.info("Initializing Skylight client...")
        skylight_client = SkylightClient(
            email=config['credentials']['skylight_email'],
            password=config['credentials']['skylight_password'],
            frame_id=config['credentials']['skylight_frame_id']
        )

        # Test authentication
        skylight_client.authenticate()
        logger.info("✅ Skylight client authenticated successfully")

        # Initialize state manager
        db_path = project_root / config.get('database', {}).get('path', 'sync_state.db')
        state_manager = StateManager(str(db_path))
        logger.info(f"✅ State manager initialized with database: {db_path}")

        return paprika_client, skylight_client, state_manager

    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)


def create_sync_engine(
    config: Dict[str, Any],
    paprika_client: PaprikaClient,
    skylight_client: SkylightClient,
    state_manager: StateManager
) -> SyncEngine:
    """
    Create and configure sync engine

    Args:
        config: Configuration dictionary
        paprika_client: Authenticated Paprika client
        skylight_client: Authenticated Skylight client
        state_manager: Initialized state manager

    Returns:
        Configured SyncEngine instance
    """
    paprika_list_name = config.get('paprika', {}).get('list_name', 'Test List')
    skylight_list_name = config.get('skylight', {}).get('list_name', 'Test List')

    logger.info(f"Creating sync engine for lists: '{paprika_list_name}' ↔ '{skylight_list_name}'")

    try:
        sync_engine = SyncEngine(
            paprika_client=paprika_client,
            skylight_client=skylight_client,
            state_manager=state_manager,
            paprika_list_name=paprika_list_name,
            skylight_list_name=skylight_list_name
        )

        logger.info("✅ Sync engine created successfully")
        return sync_engine

    except Exception as e:
        logger.error(f"Failed to create sync engine: {e}")
        sys.exit(1)


def perform_sync(dry_run: bool = False) -> Dict[str, Any]:
    """
    Perform a sync operation with retry logic

    Args:
        dry_run: If True, simulate changes without applying them

    Returns:
        Sync results dictionary
    """
    if not sync_engine:
        logger.error("Sync engine not initialized")
        return {'success': False, 'error': 'Sync engine not initialized'}

    config = load_config()
    retry_config = config.get('retry', {})
    max_attempts = retry_config.get('max_attempts', 3)
    backoff_factor = retry_config.get('backoff_factor', 2)

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Starting sync attempt {attempt}/{max_attempts} (dry_run={dry_run})")

            results = sync_engine.sync(dry_run=dry_run)

            if results['success']:
                logger.info(f"✅ Sync completed successfully on attempt {attempt}")
                if not dry_run:
                    # Log summary
                    changes = results.get('changes_applied', {})
                    created = len(changes.get('paprika_created', [])) + len(changes.get('skylight_created', []))
                    updated = len(changes.get('paprika_updated', [])) + len(changes.get('skylight_updated', []))
                    deleted = len(changes.get('paprika_deleted', [])) + len(changes.get('skylight_deleted', []))

                    if created or updated or deleted:
                        logger.info(f"   Changes: {created} created, {updated} updated, {deleted} deleted")
                    else:
                        logger.info("   No changes needed")

                    if results.get('conflicts_resolved', 0) > 0:
                        logger.info(f"   Resolved {results['conflicts_resolved']} conflicts")

                return results
            else:
                logger.warning(f"Sync attempt {attempt} completed with errors: {results.get('errors', [])}")
                if attempt < max_attempts:
                    wait_time = backoff_factor ** (attempt - 1)
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

        except Exception as e:
            logger.error(f"Sync attempt {attempt} failed with exception: {e}")
            if attempt < max_attempts:
                wait_time = backoff_factor ** (attempt - 1)
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                return {'success': False, 'error': str(e)}

    logger.error(f"All {max_attempts} sync attempts failed")
    return {'success': False, 'error': 'All retry attempts failed'}


def scheduled_sync():
    """Scheduled sync job for daemon mode"""
    logger.debug("Scheduled sync triggered")
    results = perform_sync(dry_run=False)

    if not results['success']:
        logger.error(f"Scheduled sync failed: {results.get('error', 'Unknown error')}")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down gracefully...")

    if scheduler and scheduler.running:
        logger.info("Stopping scheduler...")
        scheduler.shutdown(wait=True)

    if sync_engine and hasattr(sync_engine.state, 'close'):
        logger.info("Closing database connections...")
        sync_engine.state.close()

    logger.info("Shutdown complete")
    sys.exit(0)


def run_once_mode(dry_run: bool = False):
    """Run sync once and exit"""
    logger.info(f"Running in once mode (dry_run={dry_run})")

    results = perform_sync(dry_run=dry_run)

    if results['success']:
        print("✅ Sync completed successfully")
        if dry_run:
            print("\n📋 Dry-run results:")
            changes = results.get('changes_applied', {})
            for action, items in changes.items():
                if items and isinstance(items, list):
                    print(f"   {action}: {', '.join(items)}")
        sys.exit(0)
    else:
        print(f"❌ Sync failed: {results.get('error', 'Unknown error')}")
        sys.exit(1)


def run_daemon_mode(config: Dict[str, Any]):
    """Run sync daemon with scheduled intervals"""
    global scheduler

    sync_interval = config.get('sync_interval_seconds', 60)
    logger.info(f"Starting daemon mode with {sync_interval}s intervals")

    # Create scheduler
    executors = {
        'default': ThreadPoolExecutor(1)  # Single thread to avoid conflicts
    }

    scheduler = BlockingScheduler(executors=executors, timezone='UTC')

    # Add sync job
    scheduler.add_job(
        scheduled_sync,
        'interval',
        seconds=sync_interval,
        id='sync_job',
        max_instances=1,  # Prevent overlapping syncs
        replace_existing=True
    )

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Perform initial sync
        logger.info("Performing initial sync...")
        initial_results = perform_sync(dry_run=False)
        if initial_results['success']:
            logger.info("✅ Initial sync completed successfully")
        else:
            logger.warning(f"Initial sync failed: {initial_results.get('error')}")
            logger.info("Continuing with scheduled sync anyway...")

        # Start scheduler
        logger.info(f"🚀 Sync daemon started - syncing every {sync_interval} seconds")
        logger.info("Press Ctrl+C to stop")

        scheduler.start()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Daemon failed: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    global sync_engine

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Paprika ↔ Skylight Grocery List Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py                    # Run daemon mode (default)
  python src/main.py --once             # Run sync once and exit
  python src/main.py --dry-run          # Test sync without changes
  python src/main.py --once --dry-run   # Test once without changes

Configuration:
  .env file: Contains credentials (copy from .env.example)
  config.yaml: Contains sync settings and list names
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test sync without making actual changes'
    )

    parser.add_argument(
        '--once',
        action='store_true',
        help='Run sync once and exit (instead of daemon mode)'
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run in daemon mode with scheduled intervals (default)'
    )

    args = parser.parse_args()

    # Load configuration first (needed for logging setup)
    config = load_config()

    # Set up logging
    setup_logging(config)

    # Log startup
    logger.info("=" * 60)
    logger.info("🚀 Paprika ↔ Skylight Grocery List Sync Starting")
    logger.info("=" * 60)

    # Initialize clients
    paprika_client, skylight_client, state_manager = initialize_clients(config)

    # Create sync engine
    sync_engine = create_sync_engine(config, paprika_client, skylight_client, state_manager)

    # Determine mode
    if args.once:
        run_once_mode(dry_run=args.dry_run)
    else:
        # Default to daemon mode
        if args.dry_run:
            logger.warning("Dry-run mode not supported in daemon mode, use --once --dry-run instead")
            sys.exit(1)
        run_daemon_mode(config)


if __name__ == "__main__":
    main()