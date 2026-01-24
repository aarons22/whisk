"""
Configuration management for Whisk

Handles loading, validation, and management of configuration files with
support for multiple list pairs and secure credential storage.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class ListPairConfig:
    """Configuration for a single Paprika ↔ Skylight list pair"""
    paprika_list: str
    skylight_list: str
    conflict_strategy: str = "newest_wins"  # paprika_wins, skylight_wins, newest_wins
    enabled: bool = True

@dataclass
class WhiskConfig:
    """Main Whisk configuration"""
    # List pairs (required)
    list_pairs: List[ListPairConfig]

    # Sync behavior
    sync_interval_seconds: int = 60
    global_conflict_strategy: str = "newest_wins"

    # Credentials (loaded from .env)
    paprika_email: str = ""
    paprika_password: str = ""
    skylight_email: str = ""
    skylight_password: str = ""
    skylight_frame_id: str = ""

    # Hardcoded paths (no longer configurable)
    database_path: str = ".whisk.db"
    paprika_token_cache: str = ".paprika_token"
    skylight_token_cache: str = ".skylight_token"
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
    """Manages Whisk configuration loading, validation, and storage"""

    DEFAULT_CONFIG_FILE = "whisk.yaml"
    DEFAULT_ENV_FILE = ".env"

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize ConfigManager

        Args:
            config_dir: Directory containing config files (defaults to current directory)
        """
        self.config_dir = Path(config_dir) if config_dir else Path.cwd()
        self.config_file = self.config_dir / self.DEFAULT_CONFIG_FILE
        self.env_file = self.config_dir / self.DEFAULT_ENV_FILE

    def load_config(self) -> WhiskConfig:
        """
        Load complete Whisk configuration

        Returns:
            WhiskConfig instance with all settings loaded

        Raises:
            FileNotFoundError: If required configuration files are missing
            ValueError: If configuration is invalid
        """
        # Load credentials from .env
        credentials = self._load_credentials()

        # Load main config from YAML
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

        # Parse list pairs
        list_pairs = []
        pairs_data = yaml_data.get('list_pairs', [])
        for pair_data in pairs_data:
            if isinstance(pair_data, dict):
                list_pairs.append(ListPairConfig(
                    paprika_list=pair_data['paprika_list'],
                    skylight_list=pair_data['skylight_list'],
                    conflict_strategy=pair_data.get('conflict_strategy', 'newest_wins'),
                    enabled=pair_data.get('enabled', True)
                ))

        if not list_pairs:
            raise ValueError("No list pairs configured. Run 'whisk setup' to configure list pairs.")

        # Create config object
        config = WhiskConfig(
            sync_interval_seconds=yaml_data.get('sync_interval_seconds', 60),
            global_conflict_strategy=yaml_data.get('global_conflict_strategy', 'newest_wins'),
            list_pairs=list_pairs,
            **credentials
        )

        # Validate configuration
        self._validate_config(config)

        return config

    def save_config(self, config: WhiskConfig) -> None:
        """
        Save configuration to files

        Args:
            config: WhiskConfig instance to save
        """
        # Save credentials to .env
        self._save_credentials(config)

        # Save main config to YAML (excluding credentials)
        yaml_data = {
            'sync_interval_seconds': config.sync_interval_seconds,
            'global_conflict_strategy': config.global_conflict_strategy,
            'list_pairs': [
                {
                    'paprika_list': pair.paprika_list,
                    'skylight_list': pair.skylight_list,
                    'conflict_strategy': pair.conflict_strategy,
                    'enabled': pair.enabled
                }
                for pair in config.list_pairs
            ]
        }

        # Ensure directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Write YAML file
        with open(self.config_file, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)
            f.write('\n# This file was auto-generated by whisk setup\n')
            f.write('# For help: whisk --help\n')

        logger.info(f"Configuration saved to {self.config_file}")

    def _load_credentials(self) -> Dict[str, str]:
        """Load credentials from .env file"""
        from dotenv import load_dotenv

        if not self.env_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.env_file}\n"
                f"Run 'whisk setup' to configure credentials."
            )

        # Load environment variables
        load_dotenv(self.env_file)

        required_vars = [
            'PAPRIKA_EMAIL', 'PAPRIKA_PASSWORD',
            'SKYLIGHT_EMAIL', 'SKYLIGHT_PASSWORD',
            'SKYLIGHT_FRAME_ID'
        ]

        credentials = {}
        missing_vars = []

        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                # Convert env var names to config field names
                field_name = var.lower()
                credentials[field_name] = value

        if missing_vars:
            raise ValueError(
                f"Missing required credentials in {self.env_file}:\n" +
                "\n".join(f"  {var}" for var in missing_vars) +
                f"\n\nRun 'whisk setup' to configure credentials."
            )

        return credentials

    def _save_credentials(self, config: WhiskConfig) -> None:
        """Save credentials to .env file with proper permissions"""
        env_content = f"""# Whisk Credentials
# This file contains sensitive information - keep it secure!

# Paprika Credentials
PAPRIKA_EMAIL={config.paprika_email}
PAPRIKA_PASSWORD={config.paprika_password}

# Skylight Credentials
SKYLIGHT_EMAIL={config.skylight_email}
SKYLIGHT_PASSWORD={config.skylight_password}
SKYLIGHT_FRAME_ID={config.skylight_frame_id}
"""

        # Write file
        with open(self.env_file, 'w') as f:
            f.write(env_content)

        # Set restrictive permissions
        os.chmod(self.env_file, 0o600)
        logger.info(f"Credentials saved to {self.env_file} (permissions: 600)")

    def _validate_config(self, config: WhiskConfig) -> None:
        """Validate configuration for common issues"""
        errors = []

        # Validate sync interval
        if config.sync_interval_seconds < 30:
            errors.append("sync_interval_seconds must be at least 30 seconds")

        # Validate conflict strategies
        valid_strategies = ["paprika_wins", "skylight_wins", "newest_wins"]
        if config.global_conflict_strategy not in valid_strategies:
            errors.append(f"global_conflict_strategy must be one of: {valid_strategies}")

        # Validate list pairs
        if not config.list_pairs:
            errors.append("At least one list pair must be configured")

        for i, pair in enumerate(config.list_pairs):
            if not pair.paprika_list.strip():
                errors.append(f"List pair {i+1}: paprika_list cannot be empty")
            if not pair.skylight_list.strip():
                errors.append(f"List pair {i+1}: skylight_list cannot be empty")
            if pair.conflict_strategy not in valid_strategies:
                errors.append(f"List pair {i+1}: conflict_strategy must be one of: {valid_strategies}")

        # Validate credentials
        if not config.paprika_email:
            errors.append("PAPRIKA_EMAIL is required")
        if not config.paprika_password:
            errors.append("PAPRIKA_PASSWORD is required")
        if not config.skylight_email:
            errors.append("SKYLIGHT_EMAIL is required")
        if not config.skylight_password:
            errors.append("SKYLIGHT_PASSWORD is required")
        if not config.skylight_frame_id:
            errors.append("SKYLIGHT_FRAME_ID is required")

        if errors:
            raise ValueError(
                "Configuration validation failed:\n" +
                "\n".join(f"  - {error}" for error in errors) +
                "\n\nRun 'whisk setup' to fix configuration issues."
            )

    def config_exists(self) -> bool:
        """Check if configuration files exist"""
        return self.config_file.exists() and self.env_file.exists()

    def create_example_config(self) -> None:
        """Create example configuration files for manual editing"""
        # Example .env
        example_env = f"""{self.env_file}.example"""
        with open(example_env, 'w') as f:
            f.write("""# Whisk Credentials - Copy to .env and fill in your details
# Keep .env file secure and never commit it to version control!

# Paprika Credentials
PAPRIKA_EMAIL=your-paprika-email@example.com
PAPRIKA_PASSWORD=your-paprika-password

# Skylight Credentials
SKYLIGHT_EMAIL=your-skylight-email@example.com
SKYLIGHT_PASSWORD=your-skylight-password
SKYLIGHT_FRAME_ID=your-frame-id

# Run 'whisk setup' for interactive configuration
""")

        # Example config
        example_config = f"""{self.config_file}.example"""
        with open(example_config, 'w') as f:
            f.write("""# Whisk Configuration Example
# Copy to whisk.yaml and customize for your needs

# How often to sync (in seconds, minimum 30)
sync_interval_seconds: 60

# Default conflict resolution strategy
global_conflict_strategy: "newest_wins"  # paprika_wins, skylight_wins, newest_wins

# List pairs to sync (one-to-one mapping)
list_pairs:
  - paprika_list: "My Grocery List"
    skylight_list: "Shopping List"
    conflict_strategy: "newest_wins"
    enabled: true

  - paprika_list: "Costco Run"
    skylight_list: "Bulk Items"
    conflict_strategy: "paprika_wins"
    enabled: true

# Run 'whisk setup' for interactive configuration
""")

        logger.info(f"Example configuration files created:")
        logger.info(f"  - {example_env}")
        logger.info(f"  - {example_config}")
        logger.info(f"")
        logger.info(f"Copy these to .env and whisk.yaml, then edit with your details")
        logger.info(f"Or run 'whisk setup' for interactive configuration")


def load_config(config_dir: Optional[Path] = None) -> WhiskConfig:
    """
    Convenience function to load Whisk configuration

    Args:
        config_dir: Directory containing config files

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
        config_dir: Directory to save config files
    """
    manager = ConfigManager(config_dir)
    manager.save_config(config)