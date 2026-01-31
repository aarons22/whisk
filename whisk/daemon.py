"""
Daemon management for Whisk

Handles starting, stopping, and monitoring of the Whisk sync daemon
with proper PID file management and signal handling.
"""

import os
import signal
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import psutil
from datetime import datetime, timezone

from .config import WhiskConfig

logger = logging.getLogger(__name__)


class DaemonManager:
    """Manages Whisk sync daemon lifecycle"""

    def __init__(self, config: Optional[WhiskConfig], config_dir: Optional[Path], pid_file: str = ".whisk.pid"):
        """
        Initialize daemon manager

        Args:
            config: Whisk configuration (optional for stop/status operations)
            config_dir: Directory for PID file and other resources
            pid_file: Path to PID file
        """
        self.config = config
        self.config_dir = config_dir or Path.cwd()
        self.pid_file = self.config_dir / pid_file
        self.sync_engine = None

    def is_running(self) -> bool:
        """
        Check if daemon is currently running

        Returns:
            True if daemon is running, False otherwise
        """
        if not self.pid_file.exists():
            return False

        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())

            # Check if process is actually running
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                # Verify it's actually our process (basic check)
                if 'whisk' in ' '.join(proc.cmdline()):
                    return True

        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # PID file exists but process is not running - clean up
        self.pid_file.unlink(missing_ok=True)
        return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get daemon status information

        Returns:
            Dictionary with status information
        """
        if not self.is_running():
            return {
                'running': False,
                'message': 'Daemon is not running'
            }

        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())

            proc = psutil.Process(pid)
            return {
                'running': True,
                'pid': pid,
                'started': datetime.fromtimestamp(proc.create_time(), tz=timezone.utc),
                'memory_mb': round(proc.memory_info().rss / 1024 / 1024, 1),
                'cpu_percent': proc.cpu_percent(),
                'status': proc.status()
            }

        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return {
                'running': False,
                'error': f'Could not get status: {e}'
            }

    def start_daemon(self, foreground: bool = False) -> int:
        """
        Start the sync daemon

        Args:
            foreground: If True, run in foreground; if False, daemonize

        Returns:
            Exit code (0 for success)
        """
        if self.is_running():
            print("❌ Daemon is already running")
            return 1

        if foreground:
            return self._run_daemon()
        else:
            return self._daemonize()

    def stop_daemon(self) -> int:
        """
        Stop the running daemon

        Returns:
            Exit code (0 for success)
        """
        if not self.is_running():
            print("❌ Daemon is not running")
            return 1

        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())

            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit (up to 10 seconds)
            for _ in range(100):  # 10 seconds total
                if not psutil.pid_exists(pid):
                    break
                time.sleep(0.1)
            else:
                # Force kill if it doesn't respond to SIGTERM
                logger.warning(f"Process {pid} didn't respond to SIGTERM, sending SIGKILL")
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)

            # Clean up PID file
            self.pid_file.unlink(missing_ok=True)
            print("✅ Daemon stopped successfully")
            return 0

        except (ValueError, ProcessLookupError, psutil.NoSuchProcess):
            # Process already gone, clean up PID file
            self.pid_file.unlink(missing_ok=True)
            print("✅ Daemon was already stopped")
            return 0
        except Exception as e:
            print(f"❌ Failed to stop daemon: {e}")
            return 1

    def _daemonize(self) -> int:
        """
        Daemonize the process (Unix double-fork)

        Returns:
            Exit code (0 for success)
        """
        try:
            # First fork
            pid = os.fork()
            if pid > 0:
                # Parent process exits
                sys.exit(0)
        except OSError as e:
            logger.error(f"First fork failed: {e}")
            return 1

        # Decouple from parent environment
        os.chdir('/')
        os.setsid()
        os.umask(0)

        try:
            # Second fork
            pid = os.fork()
            if pid > 0:
                # Second parent exits
                sys.exit(0)
        except OSError as e:
            logger.error(f"Second fork failed: {e}")
            return 1

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        # Redirect to null
        with open(os.devnull, 'r') as dev_null_r, \
             open(os.devnull, 'w') as dev_null_w:
            os.dup2(dev_null_r.fileno(), sys.stdin.fileno())
            os.dup2(dev_null_w.fileno(), sys.stdout.fileno())
            os.dup2(dev_null_w.fileno(), sys.stderr.fileno())

        # Run the daemon
        return self._run_daemon()

    def _run_daemon(self) -> int:
        """
        Run the actual daemon process

        Returns:
            Exit code (0 for success)
        """
        try:
            # Write PID file
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))

            # Set up signal handlers
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

            # Initialize and start daemon
            logger.info("Whisk daemon starting...")
            print("🚀 Whisk daemon started")

            # Main daemon loop
            self._daemon_loop()

        except KeyboardInterrupt:
            logger.info("Daemon interrupted by user")
        except Exception as e:
            logger.error(f"Daemon failed: {e}")
            return 1
        finally:
            # Clean up
            self.pid_file.unlink(missing_ok=True)
            logger.info("Daemon stopped")

        return 0

    def _daemon_loop(self) -> None:
        """Main daemon loop - perform scheduled syncs"""
        if not self.config:
            logger.error("Cannot run daemon without configuration")
            return

        from .multi_sync_engine import WhiskSyncEngine

        # Initialize sync engine
        self.sync_engine = WhiskSyncEngine(self.config, self.config_dir)

        sync_interval = self.config.sync_interval_seconds
        logger.info(f"Starting sync loop with {sync_interval}s intervals")

        while True:
            try:
                logger.debug("Performing scheduled sync...")

                # Perform sync of all enabled pairs
                result = self.sync_engine.sync_all_pairs(dry_run=False)

                if result.success:
                    logger.info(f"✅ Scheduled sync completed: {result.successful_pairs}/{result.total_pairs} pairs, "
                               f"{result.total_changes} changes, {result.total_conflicts_resolved} conflicts resolved")
                else:
                    logger.warning(f"⚠️ Scheduled sync had errors: {result.failed_pairs}/{result.total_pairs} pairs failed")
                    for error in result.errors[:3]:  # Log first 3 errors
                        logger.warning(f"   {error}")

                # Sleep until next sync
                time.sleep(sync_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Sync failed: {e}")
                # Continue running even if sync fails
                time.sleep(sync_interval)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")

        # Graceful shutdown
        if self.sync_engine:
            logger.info("Stopping sync engine...")
            # Sync engine doesn't need explicit cleanup

        # Clean up PID file
        self.pid_file.unlink(missing_ok=True)
        logger.info("Daemon shutdown complete")
        sys.exit(0)