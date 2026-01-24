# Paprika ↔ Skylight Grocery List Sync

Bidirectional automation script that syncs grocery lists between Paprika Recipe Manager and Skylight Frame.

## Overview

This tool automatically syncs grocery items between:
- **Paprika**: Recipe management app with grocery lists
- **Skylight**: Digital photo frame with shared lists

**Key Features:**
- Two-way sync (changes in either system propagate to the other)
- Automatic conflict resolution (most recent change wins)
- Configurable sync intervals
- Preserves Paprika's aisle categorization
- Syncs checked/purchased status
- Safe testing mode using "Test List" before production use

## Prerequisites

- Python 3.10 or higher
- Paprika account with cloud sync enabled
- Skylight account with frame set up
- macOS, Linux, or Windows

## Installation

### 1. Clone or Download Project

```bash
cd ~/Projects
# If you haven't already, create the project directory
```

### 2. Create Virtual Environment

```bash
cd ~/Projects/paprika-skylight
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -e .
```

## Configuration

### 1. Set Up Credentials

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# Paprika Credentials
PAPRIKA_EMAIL=your.email@example.com
PAPRIKA_PASSWORD=your_paprika_password

# Skylight Credentials
SKYLIGHT_EMAIL=your.email@example.com
SKYLIGHT_PASSWORD=your_skylight_password
SKYLIGHT_FRAME_ID=your_frame_id  # See step 2 below
```

**Important:** The `.env` file contains sensitive credentials and is automatically excluded from git.

### 2. Find Your Skylight Frame ID

Run the helper script to discover your frame ID:

```bash
python scripts/find_skylight_frame.py
```

This will:
1. Prompt for your Skylight email and password
2. List all your Skylight frames with their IDs
3. Display output like: `Frame Name: "Smith Family" - ID: abc123xyz`

Copy the frame ID to your `.env` file.

### 3. Configure List Names and Sync Interval

Edit `config.yaml` to set list names and sync behavior:

```yaml
# For testing (recommended initially)
paprika:
  list_name: "Test List"

skylight:
  list_name: "Test List"

# Sync every 60 seconds (adjust as needed)
sync_interval_seconds: 60
```

**Testing Strategy:**
- Start with "Test List" in both apps to protect your production grocery data
- Once stable, change to production lists:
  - Paprika: "My Grocery List"
  - Skylight: "Grocery List"

### 4. Create Test Lists

Before running sync:
1. Open Paprika app → Create a new grocery list called "Test List"
2. Open Skylight app → Create a new list called "Test List"

## Usage

### Dry Run (Test Mode)

Test sync logic without making changes:

```bash
cd ~/Projects/paprika-skylight
source .venv/bin/activate
python src/main.py --dry-run
```

This shows what would be synced without actually modifying anything.

### Single Sync

Run one sync operation:

```bash
python src/main.py --once
```

Use this to test that sync works correctly before running continuously.

### Continuous Sync (Daemon Mode)

Run sync daemon continuously at configured interval:

```bash
python src/main.py --daemon
```

Press `Ctrl+C` to stop gracefully.

### Check Status

View current sync state:

```bash
python src/main.py --status
```

## macOS Auto-Start (Optional)

To run the sync automatically when your Mac starts:

### 1. Create launchd Service

Create `~/Library/LaunchAgents/com.user.grocery-sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.grocery-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/Projects/paprika-skylight/.venv/bin/python</string>
        <string>/Users/YOUR_USERNAME/Projects/paprika-skylight/src/main.py</string>
        <string>--daemon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/Projects/paprika-skylight</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Projects/paprika-skylight/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Projects/paprika-skylight/logs/stderr.log</string>
</dict>
</plist>
```

**Replace `YOUR_USERNAME` with your actual username.**

### 2. Load Service

```bash
# Create logs directory
mkdir -p ~/Projects/paprika-skylight/logs

# Load the service
launchctl load ~/Library/LaunchAgents/com.user.grocery-sync.plist

# Check status
launchctl list | grep grocery-sync
```

### 3. Manage Service

```bash
# Stop service
launchctl stop com.user.grocery-sync

# Start service
launchctl start com.user.grocery-sync

# Unload service (disable auto-start)
launchctl unload ~/Library/LaunchAgents/com.user.grocery-sync.plist
```

## How It Works

### Sync Strategy

1. **Fetch** current items from both Paprika and Skylight
2. **Compare** with last-known state (stored in SQLite database)
3. **Detect** changes:
   - Items added to one system
   - Items removed from one system
   - Items checked/unchecked
   - Items modified in both (conflict)
4. **Resolve** conflicts using timestamps (most recent change wins)
5. **Apply** changes to keep both systems in sync
6. **Update** local state database

### Data Synced

- Item name
- Checked/purchased status
- Timestamps (for conflict resolution)

### Data NOT Synced

- Aisles (Paprika auto-assigns, Skylight doesn't support)
- Quantities (not consistently supported)
- Notes (not consistently supported)

## Troubleshooting

### Authentication Errors

**Paprika "Invalid credentials":**
- Verify `PAPRIKA_EMAIL` and `PAPRIKA_PASSWORD` in `.env`
- Ensure cloud sync is enabled in Paprika app
- Try logging into Paprika app to verify credentials

**Skylight "Unauthorized":**
- Verify `SKYLIGHT_EMAIL` and `SKYLIGHT_PASSWORD` in `.env`
- Verify `SKYLIGHT_FRAME_ID` is correct (use `find_skylight_frame.py`)

### No Items Syncing

**Check list names:**
- Verify list names in `config.yaml` exactly match lists in apps (case-sensitive)
- Default test names: "Test List" in both
- Default production names: "My Grocery List" (Paprika), "Grocery List" (Skylight)

**Check logs:**
```bash
tail -f sync.log
```

Look for errors or warnings.

### Duplicate Items

If you see duplicate items:
1. Stop the sync daemon
2. Manually merge duplicates in both apps (keep one copy)
3. Delete sync state: `rm sync_state.db`
4. Restart sync (it will rebuild state from current items)

### Reset Sync State

To completely reset and rebuild from scratch:

```bash
# Stop daemon if running
# Delete sync state database
rm sync_state.db

# Delete token caches
rm .paprika_token

# Restart sync
python src/main.py --once
```

This re-syncs everything from both systems.

## Switching to Production Lists

Once testing is complete and stable:

1. **Stop sync daemon** (if running)
2. **Edit config.yaml:**
   ```yaml
   paprika:
     list_name: "My Grocery List"

   skylight:
     list_name: "Grocery List"
   ```
3. **Delete test sync state:** `rm sync_state.db`
4. **Run single sync:** `python src/main.py --once`
5. **Verify** items synced correctly in both apps
6. **Start daemon:** `python src/main.py --daemon`

## File Permissions

The sync tool automatically sets restrictive permissions on sensitive files:

- `.env` - Should be `600` (owner read/write only)
- `.paprika_token` - Automatically set to `600`
- `sync_state.db` - Contains item mappings (not sensitive but auto-protected)

Verify:
```bash
ls -la .env .paprika_token
```

Both should show `-rw-------` (600 permissions).

## Logs

Logs are written to `sync.log` with automatic rotation (keeps last 3 files, 10MB each).

**View live logs:**
```bash
tail -f sync.log
```

**Log levels:**
- `INFO`: Normal operations (sync start/complete, items synced)
- `WARNING`: Conflict resolutions, retry attempts
- `ERROR`: API failures, authentication issues
- `DEBUG`: Detailed request/response info (set in config.yaml)

## Development & Testing

### Run Phase 1 Tests (Paprika)

```bash
python tests/test_paprika.py
```

Tests authentication, read/write operations, and checked status sync.

### Run Phase 2 Tests (Skylight)

```bash
python tests/test_skylight.py
```

Tests Skylight API integration (once implemented in Phase 2).

### Run Full Sync Tests

```bash
python tests/test_sync.py
```

Tests end-to-end sync scenarios (once implemented in Phase 4+).

## Project Structure

```
~/Projects/paprika-skylight/
├── .env                    # Credentials (gitignored)
├── .env.example            # Template
├── config.yaml             # Configuration
├── README.md              # This file
├── CLAUDE.md              # Implementation patterns
├── pyproject.toml         # Dependencies
├── sync_state.db          # SQLite database (created at runtime)
├── sync.log               # Log file
├── src/
│   ├── main.py           # Entry point
│   ├── paprika_client.py # Paprika API wrapper
│   ├── skylight_client.py # Skylight API wrapper
│   ├── sync_engine.py    # Sync logic
│   ├── state_manager.py  # SQLite state tracking
│   └── models.py         # Data models
├── scripts/
│   └── find_skylight_frame.py # Frame ID discovery
└── tests/
    ├── test_paprika.py   # Paprika tests
    ├── test_skylight.py  # Skylight tests
    └── test_sync.py      # Integration tests
```

## Known Limitations

- **Unofficial APIs**: Both Paprika and Skylight APIs are reverse-engineered and may break with app updates
- **Rate Limits**: Unknown rate limits; sync interval should be reasonable (60+ seconds recommended)
- **Simultaneous Edits**: If same item edited in both apps between syncs, last write wins (could lose one edit)
- **Single List**: Currently syncs one list pair at a time

## Future Enhancements

- Web UI for monitoring sync status
- Support for multiple grocery lists
- Manual conflict resolution UI
- Item quantities and notes sync
- Email notifications for sync failures

## Support

For issues or questions:
1. Check logs: `tail -f sync.log`
2. Review troubleshooting section above
3. Try resetting sync state
4. Check that both apps are working independently

## License

This project uses reverse-engineered APIs for interoperability purposes. Use at your own risk.
