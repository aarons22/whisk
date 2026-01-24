#!/usr/bin/env python3
"""
Phase 5 Verification Test Suite

Comprehensive tests for main.py entry point functionality including:
- CLI argument parsing
- Configuration loading
- Logging setup
- Once mode operation
- Daemon mode initialization
- Error handling and graceful shutdown
"""

import sys
import tempfile
import os
import yaml
import subprocess
import time
import signal
from pathlib import Path
from unittest.mock import patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_cli_help():
    """Test that CLI help works"""
    print("🧪 Testing CLI help...")

    result = subprocess.run([
        sys.executable, "src/main.py", "--help"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

    assert result.returncode == 0, "Help should exit successfully"
    assert "Paprika ↔ Skylight Grocery List Sync" in result.stdout, "Should show program description"
    assert "--dry-run" in result.stdout, "Should show dry-run option"
    assert "--once" in result.stdout, "Should show once option"
    assert "--daemon" in result.stdout, "Should show daemon option"

    print("   ✅ CLI help working correctly")
    return True


def test_config_loading():
    """Test configuration loading from .env and config.yaml"""
    print("🧪 Testing configuration loading...")

    project_root = Path(__file__).parent.parent

    # Check that required config files exist
    env_file = project_root / ".env"
    config_file = project_root / "config.yaml"

    assert env_file.exists(), f".env file should exist at {env_file}"
    assert config_file.exists(), f"config.yaml should exist at {config_file}"

    # Test that config.yaml is valid YAML
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        assert isinstance(config, dict), "config.yaml should contain a dictionary"
        assert 'sync_interval_seconds' in config, "Should have sync_interval_seconds"
        assert 'paprika' in config, "Should have paprika section"
        assert 'skylight' in config, "Should have skylight section"
        assert 'logging' in config, "Should have logging section"
    except yaml.YAMLError as e:
        assert False, f"config.yaml should be valid YAML: {e}"

    print("   ✅ Configuration loading working correctly")
    return True


def test_once_mode_dry_run():
    """Test once mode with dry-run"""
    print("🧪 Testing once mode with dry-run...")

    result = subprocess.run([
        sys.executable, "src/main.py", "--once", "--dry-run"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

    assert result.returncode == 0, f"Once mode dry-run should succeed, got: {result.stderr}"
    assert "Sync completed successfully" in result.stdout, "Should report success"
    assert "Dry-run results:" in result.stdout or "No changes needed" in result.stderr, "Should show dry-run results"

    print("   ✅ Once mode dry-run working correctly")
    return True


def test_once_mode_real():
    """Test once mode with real sync"""
    print("🧪 Testing once mode with real sync...")

    result = subprocess.run([
        sys.executable, "src/main.py", "--once"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

    assert result.returncode == 0, f"Once mode real sync should succeed, got: {result.stderr}"
    assert "Sync completed successfully" in result.stdout, "Should report success"

    print("   ✅ Once mode real sync working correctly")
    return True


def test_daemon_initialization():
    """Test daemon mode starts and shuts down gracefully"""
    print("🧪 Testing daemon mode initialization...")

    # Start daemon in background
    proc = subprocess.Popen([
        sys.executable, "src/main.py", "--daemon"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    cwd=Path(__file__).parent.parent)

    try:
        # Let it initialize for a few seconds
        time.sleep(8)

        # Send SIGTERM to shut it down gracefully
        proc.send_signal(signal.SIGTERM)

        # Wait for it to finish
        stdout, stderr = proc.communicate(timeout=10)

        # Daemon should exit cleanly
        assert proc.returncode == 0, f"Daemon should exit cleanly, got return code {proc.returncode}"

        # Should show initialization messages
        assert "Paprika ↔ Skylight Grocery List Sync Starting" in stderr, "Should show startup message"
        assert "Sync daemon started" in stderr, "Should show daemon started message"
        assert "Received signal 15" in stderr, "Should handle SIGTERM"
        assert "Shutdown complete" in stderr, "Should shutdown gracefully"

        print("   ✅ Daemon mode initialization working correctly")
        return True

    except subprocess.TimeoutExpired:
        # Force kill if it doesn't respond to SIGTERM
        proc.kill()
        proc.communicate()
        assert False, "Daemon should respond to SIGTERM within timeout"

    except Exception as e:
        # Clean up process
        try:
            proc.kill()
            proc.communicate()
        except:
            pass
        raise e


def test_logging_setup():
    """Test that logging is configured properly"""
    print("🧪 Testing logging setup...")

    project_root = Path(__file__).parent.parent

    # Run once mode to generate logs
    result = subprocess.run([
        sys.executable, "src/main.py", "--once", "--dry-run"
    ], capture_output=True, text=True, cwd=project_root)

    assert result.returncode == 0, "Should succeed for logging test"

    # Check that log file is created
    log_file = project_root / "sync.log"
    assert log_file.exists(), f"Log file should be created at {log_file}"

    # Check log file content
    with open(log_file, 'r') as f:
        log_content = f.read()

    assert "Paprika ↔ Skylight Grocery List Sync Starting" in log_content, "Should log startup message"
    assert "INFO" in log_content, "Should have INFO level messages"

    print("   ✅ Logging setup working correctly")
    return True


def test_error_handling():
    """Test error handling with invalid configuration"""
    print("🧪 Testing error handling...")

    # Create temporary directory with invalid config
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create invalid .env file (missing required vars)
        invalid_env = temp_path / ".env"
        invalid_env.write_text("PAPRIKA_EMAIL=test@example.com\n")

        # Create valid config.yaml
        valid_config = temp_path / "config.yaml"
        valid_config.write_text("""
sync_interval_seconds: 60
paprika:
  list_name: "Test List"
skylight:
  list_name: "Test List"
database:
  path: "sync_state.db"
logging:
  level: "INFO"
retry:
  max_attempts: 3
""")

        # Try to run with invalid config
        result = subprocess.run([
            sys.executable, "-c", f"""
import sys
sys.path.insert(0, '{Path(__file__).parent.parent / "src"}')
import os
os.chdir('{temp_path}')
from main import load_config
try:
    load_config()
    print('ERROR: Should have failed')
    sys.exit(1)
except SystemExit:
    print('SUCCESS: Properly handled missing env vars')
    sys.exit(0)
"""
        ], capture_output=True, text=True)

        # Should exit with error code but handle it gracefully
        assert "SUCCESS: Properly handled missing env vars" in result.stdout, "Should handle missing env vars gracefully"

    print("   ✅ Error handling working correctly")
    return True


def test_configuration_validation():
    """Test that configuration validation works"""
    print("🧪 Testing configuration validation...")

    project_root = Path(__file__).parent.parent

    # Test with actual config - should pass validation
    result = subprocess.run([
        sys.executable, "-c", f"""
import sys
sys.path.insert(0, '{project_root / "src"}')
import os
os.chdir('{project_root}')
from main import load_config
try:
    config = load_config()
    print('SUCCESS: Configuration loaded')
    print(f'Sync interval: {{config.get("sync_interval_seconds", "NOT_FOUND")}}')
    print(f'Paprika list: {{config.get("paprika", {{}}).get("list_name", "NOT_FOUND")}}')
    print(f'Skylight list: {{config.get("skylight", {{}}).get("list_name", "NOT_FOUND")}}')
except SystemExit as e:
    print(f'ERROR: Configuration validation failed: {{e}}')
    sys.exit(1)
"""
    ], capture_output=True, text=True)

    assert result.returncode == 0, f"Configuration validation should pass: {result.stderr}"
    assert "SUCCESS: Configuration loaded" in result.stdout, "Should load configuration successfully"

    print("   ✅ Configuration validation working correctly")
    return True


def run_all_tests():
    """Run all Phase 5 tests"""
    print("🧪 Phase 5: Scheduling and Configuration Test Suite")
    print("=" * 60)

    tests = [
        test_cli_help,
        test_config_loading,
        test_once_mode_dry_run,
        test_once_mode_real,
        test_daemon_initialization,
        test_logging_setup,
        test_error_handling,
        test_configuration_validation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"   ❌ {test.__name__} failed")
        except Exception as e:
            failed += 1
            print(f"   ❌ {test.__name__} failed with exception: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All Phase 5 tests passed!")
        print("✅ Phase 5: Scheduling and Configuration - COMPLETE")
        return True
    else:
        print(f"❌ {failed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    if success:
        print("\n🚀 Ready to proceed with Phase 6: Production Hardening")
    else:
        print("\n🔧 Fix failing tests before proceeding")

    sys.exit(0 if success else 1)