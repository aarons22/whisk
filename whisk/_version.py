"""Version information for whisk package."""

import subprocess
import sys
from pathlib import Path

def get_version():
    """Get version from git tag or fallback to default."""
    try:
        # Try to get version from git tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        if result.returncode == 0:
            # Remove 'v' prefix if present
            version = result.stdout.strip()
            return version[1:] if version.startswith('v') else version
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # Fallback to reading from pyproject.toml
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        import re
        content = pyproject_path.read_text()
        match = re.search(r'version\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)

    # Final fallback
    return "0.0.1"

__version__ = get_version()

if __name__ == "__main__":
    print(__version__)