"""
Configuration management for Whisk

Handles loading, validation, and management of configuration with
support for multiple list pairs and secure credential storage in
a single file in the user's config directory.
"""

import base64
import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import platformdirs

logger = logging.getLogger(__name__)

@dataclass
class ListPairConfig:
    """Configuration for a single Paprika ↔ Skylight list pair"""
    paprika_list: str
    skylight_list: str
    enabled: bool = True

@dataclass
class WhiskConfig:
    """Main Whisk configuration"""
    # List pairs (required)
    list_pairs: List[ListPairConfig]

    # Sync behavior
    sync_interval_seconds: int = 60

    # Credentials (loaded from config file)
    paprika_email: str = ""
    paprika_password: str = ""
    skylight_email: str = ""
    skylight_password: str = ""
    skylight_frame_id: str = ""

    # Hardcoded paths (relative to user config directory)
    database_path: str = "whisk.db"
    paprika_token_cache: str = "paprika_token"
    skylight_token_cache: str = "skylight_token"
    log_file: str = "whisk.log"

    # Hardcoded technical settings
    logging_level: str = "INFO"
    max_retry_attempts: int = 3
    retry_backoff_factor: int = 2
    fuzzy_threshold: float = 0.85
    case_sensitive: bool = False
    timestamp_tolerance_seconds: int = 60

    # Log rotation settings (hardcoded)
    log_max_bytes: int = 10 * 1024 * 1024  # 10MB
    log_backup_count: int = 3

class ConfigManager:
    """Manages Whisk configuration loading, validation, and storage in user config directory"""

    CONFIG_FILE_NAME = "config.yaml"
    APP_NAME = "whisk"

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize ConfigManager

        Args:
            config_dir: Custom config directory (defaults to user config directory)
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Use platformdirs to get the appropriate config directory for the OS
            self.config_dir = Path(platformdirs.user_config_dir(self.APP_NAME))

        self.config_file = self.config_dir / self.CONFIG_FILE_NAME

    def get_config_location(self) -> Path:
        """Get the configuration file location"""
        return self.config_file

    def get_resource_path(self, filename: str) -> Path:
        """Get path for a resource file in the config directory"""
        return self.config_dir / filename

    def load_config(self) -> WhiskConfig:
        """
        Load complete Whisk configuration from user config directory

        Returns:
            WhiskConfig instance with all settings loaded

        Raises:
            FileNotFoundError: If configuration file is missing
            ValueError: If configuration is invalid
        """
        if not self.config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_file}\n"
                f"Run 'whisk setup' to create initial configuration."
            )

        try:
            with open(self.config_file, 'r') as f:
                yaml_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {self.config_file}: {e}")

        # Decode credentials (base64 encoded for basic obfuscation)
        credentials = self._decode_credentials(yaml_data.get('credentials', {}))

        # Parse list pairs
        list_pairs = []
        pairs_data = yaml_data.get('list_pairs', [])
        for pair_data in pairs_data:
            if isinstance(pair_data, dict):
                list_pairs.append(ListPairConfig(
                    paprika_list=pair_data['paprika_list'],
                    skylight_list=pair_data['skylight_list'],
                    enabled=pair_data.get('enabled', True)
                ))

        if not list_pairs:
            raise ValueError("No list pairs configured. Run 'whisk setup' to configure list pairs.")

        # Create config object
        config = WhiskConfig(
            sync_interval_seconds=yaml_data.get('sync_interval_seconds', 60),
            list_pairs=list_pairs,
            **credentials
        )

        # Validate configuration
        self._validate_config(config)

        return config

    def save_config(self, config: WhiskConfig) -> None:
        """
        Save configuration to user config directory

        Args:
            config: WhiskConfig instance to save
        """
        # Ensure directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Encode credentials for basic obfuscation
        encoded_credentials = self._encode_credentials(config)

        # Prepare YAML data
        yaml_data = {
            'sync_interval_seconds': config.sync_interval_seconds,
            'credentials': encoded_credentials,
            'list_pairs': [
                {
                    'paprika_list': pair.paprika_list,
                    'skylight_list': pair.skylight_list,
                    'enabled': pair.enabled
                }
                for pair in config.list_pairs
            ]
        }

        # Write YAML file
        with open(self.config_file, 'w') as f:
            f.write(f"# Whisk Configuration\n")
            f.write(f"# Stored in: {self.config_file}\n")
            f.write(f"# This file contains encoded credentials - keep it secure!\n")
            f.write(f"# Run 'whisk setup' to reconfigure\n\n")

            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)

        # Set restrictive permissions (owner only)
        os.chmod(self.config_file, 0o600)

        logger.info(f"Configuration saved to {self.config_file}")
        logger.info(f"File permissions set to 600 (owner only)")

    def _encode_credentials(self, config: WhiskConfig) -> Dict[str, str]:
        """Encode credentials with base64 for basic obfuscation"""
        return {
            'paprika_email': base64.b64encode(config.paprika_email.encode()).decode(),
            'paprika_password': base64.b64encode(config.paprika_password.encode()).decode(),
            'skylight_email': base64.b64encode(config.skylight_email.encode()).decode(),
            'skylight_password': base64.b64encode(config.skylight_password.encode()).decode(),
            'skylight_frame_id': base64.b64encode(config.skylight_frame_id.encode()).decode(),
        }

    def _decode_credentials(self, encoded_creds: Dict[str, str]) -> Dict[str, str]:
        """Decode base64 encoded credentials"""
        try:
            return {
                'paprika_email': base64.b64decode(encoded_creds.get('paprika_email', '')).decode(),
                'paprika_password': base64.b64decode(encoded_creds.get('paprika_password', '')).decode(),
                'skylight_email': base64.b64decode(encoded_creds.get('skylight_email', '')).decode(),
                'skylight_password': base64.b64decode(encoded_creds.get('skylight_password', '')).decode(),
                'skylight_frame_id': base64.b64decode(encoded_creds.get('skylight_frame_id', '')).decode(),
            }
        except Exception as e:
            raise ValueError(f"Failed to decode credentials: {e}")

    def _validate_config(self, config: WhiskConfig) -> None:
        """Validate configuration for common issues"""
        errors = []

        # Validate sync interval
        if config.sync_interval_seconds < 30:
            errors.append("sync_interval_seconds must be at least 30 seconds")

        # Validate list pairs
        if not config.list_pairs:
            errors.append("At least one list pair must be configured")

        for i, pair in enumerate(config.list_pairs):
            if not pair.paprika_list.strip():
                errors.append(f"List pair {i+1}: paprika_list cannot be empty")
            if not pair.skylight_list.strip():
                errors.append(f"List pair {i+1}: skylight_list cannot be empty")

        # Validate credentials
        if not config.paprika_email:
            errors.append("Paprika email is required")
        if not config.paprika_password:
            errors.append("Paprika password is required")
        if not config.skylight_email:
            errors.append("Skylight email is required")
        if not config.skylight_password:
            errors.append("Skylight password is required")
        if not config.skylight_frame_id:
            errors.append("Skylight frame ID is required")

        if errors:
            raise ValueError(
                "Configuration validation failed:\n" +
                "\n".join(f"  - {error}" for error in errors) +
                "\n\nRun 'whisk setup' to fix configuration issues."
            )

    def config_exists(self) -> bool:
        """Check if configuration file exists"""
        return self.config_file.exists()

    def remove_config(self) -> bool:
        """Remove configuration file (for cleanup/reset)"""
        if self.config_file.exists():
            self.config_file.unlink()
            return True
        return False

    def create_example_config(self) -> None:
        """Create example configuration file for reference"""
        example_file = self.config_dir / "config.example.yaml"

        # Ensure directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        with open(example_file, 'w') as f:
            f.write("""# Whisk Configuration Example
# This file shows the structure of a Whisk configuration
# Run 'whisk setup' for interactive configuration

# Sync behavior
sync_interval_seconds: 60

# Encoded credentials (generated by setup wizard)
credentials:
  paprika_email: "<base64-encoded>"
  paprika_password: "<base64-encoded>"
  skylight_email: "<base64-encoded>"
  skylight_password: "<base64-encoded>"
  skylight_frame_id: "<base64-encoded>"

# List pairs to sync (one-to-one mapping)
list_pairs:
  - paprika_list: "My Grocery List"
    skylight_list: "Shopping List"
    enabled: true

  - paprika_list: "Costco Run"
    skylight_list: "Bulk Items"
    enabled: true

# Note: Don't edit credentials manually - use 'whisk setup' instead
# Conflict resolution always uses 'newest wins' strategy
""")

        logger.info(f"Example configuration created: {example_file}")


def load_config(config_dir: Optional[Path] = None) -> WhiskConfig:
    """
    Convenience function to load Whisk configuration

    Args:
        config_dir: Custom config directory

    Returns:
        WhiskConfig instance
    """
    manager = ConfigManager(config_dir)
    return manager.load_config()


def save_config(config: WhiskConfig, config_dir: Optional[Path] = None) -> None:
    """
    Convenience function to save Whisk configuration

    Args:
        config: WhiskConfig to save
        config_dir: Custom config directory
    """
    manager = ConfigManager(config_dir)
    manager.save_config(config)