# Whisk 🥄

**Keep your grocery lists in sync between Paprika and Skylight**

Whisk automatically syncs your grocery lists between Paprika Recipe Manager and Skylight Calendar. Add an item on your phone, see it on your kitchen display. Check it off on Skylight, it disappears from Paprika. Simple as that.

## Important Notes

⚠️ **Security**: Your Paprika and Skylight credentials are stored locally on your machine only. While this works and is relatively low risk given the nature of grocery list data, we plan to explore more secure authentication methods in the future.

⚠️ **No Official Support**: This tool is **not supported by Paprika or Skylight**. You use it at your own risk. It works by interfacing with unofficial APIs that could change at any time.

## Installation

Run this one command to install Whisk:

**macOS/Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/aarons22/whisk/main/install.sh | bash
```

**Windows:**
```cmd
curl -sSL https://raw.githubusercontent.com/aarons22/whisk/main/install.bat -o install.bat && install.bat
```

## Quick Setup

1. **Run the setup wizard:**
   ```bash
   whisk setup
   ```
   Enter your Paprika and Skylight credentials. Whisk will find your lists automatically.

2. **Start syncing:**
   ```bash
   whisk start
   ```
   That's it! Your lists will sync every minute in the background.

3. **Check status:**
   ```bash
   whisk status
   ```

## Adding More Lists

Want to sync multiple grocery lists? Easy:

```bash
whisk lists --add
```

This lets you pair up additional lists between Paprika and Skylight.

## Common Commands

```bash
whisk setup      # Initial setup wizard
whisk start      # Start background sync
whisk stop       # Stop background sync
whisk status     # Check if sync is running
whisk sync       # Sync once manually
whisk lists      # Show your paired lists
whisk upgrade    # Update to latest version
```

## Troubleshooting

**Sync not working?**
- Check if the daemon is running: `whisk status`
- Try a manual sync: `whisk sync`
- Re-run setup if credentials changed: `whisk setup`

**Command not found?**
- Restart your terminal after installation
- Make sure `~/.local/bin` is in your PATH

**Need help?**
- Report issues: [GitHub Issues](https://github.com/aarons22/whisk/issues)

## Requirements

- Python 3.10+
- Paprika Recipe Manager account
- Skylight Calendar with grocery lists enabled

---

That's it! Whisk runs quietly in the background keeping your lists in sync so you never have to think about it.

## License

Licensed under the [MIT License](LICENSE).