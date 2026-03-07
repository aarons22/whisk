# Whisk 🥄

**Keep your grocery lists and meal plans in sync between Paprika and Skylight**

Whisk automatically syncs your grocery lists and meal plans between Paprika Recipe Manager and Skylight Calendar. Add an item on your phone, see it on your kitchen display. Plan a meal in Paprika, see it on your Skylight calendar. Check off items, and they disappear from both devices. Simple as that.

## Features

### 📝 Grocery List Sync
- **Bidirectional sync** between Paprika grocery lists and Skylight lists
- **Multiple list support** - sync as many list pairs as you want
- **Real-time updates** - changes sync every minute
- **Smart conflict resolution** - handles simultaneous edits gracefully

### 🍽️ Meal Plan Sync
- **One-way sync** from Paprika meal plans to Skylight calendar
- **Multiple meal types** - breakfast, lunch, dinner, and snacks
- **Per-meal fidelity** - each Paprika meal becomes its own Skylight sitting
  - Multiple dinners on one day remain separate dinner entries
- **Recipe integration** - syncs full Paprika recipe content + recipe reference for recipe-based meals
- **Date range control** - configurable sync window (default: 7 days ahead)

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
   Enter your Paprika and Skylight credentials. Whisk will:
   - Find your grocery lists automatically
   - Set up meal sync from Paprika to Skylight
   - Configure sync preferences (meal types, date range, etc.)

2. **Start syncing:**
   ```bash
   whisk start
   ```
   That's it! Your lists and meal plans will sync every minute in the background.

3. **Check status:**
   ```bash
   whisk status
   ```

## Configuration Options

### Grocery Lists
Want to sync multiple grocery lists? Easy:

```bash
whisk lists --add
```

This lets you pair up additional lists between Paprika and Skylight.

### Meal Sync Settings
During setup, you can configure:
- **Meal types to sync**: breakfast, lunch, dinner, snacks (all enabled by default)
- **Sync window**: how many days ahead to sync meals (default: 7 days)
- **Entry behavior**: one Paprika meal entry maps to one Skylight sitting

**Examples:**
- Multiple breakfasts in Paprika become multiple breakfast sittings in Skylight
- Recipe meals in Paprika include synced recipe reference + full recipe body in Skylight recipe

## How It Works

### Grocery List Sync (Bidirectional)
```
📱 Paprika          🔄 Whisk         📺 Skylight
Add "Milk"     →    Syncs every    →   Shows "Milk"
Check "Bread"  ←    minute         ←   Check "Bread"
```

### Meal Plan Sync (Paprika → Skylight)
```
📱 Paprika Meal Plan                📺 Skylight Calendar
Feb 15 Breakfast: Oatmeal      →   Feb 15 Breakfast: Oatmeal
Feb 15 Breakfast: Toast        →   Feb 15 Breakfast: Toast
Feb 15 Dinner: Salmon          →   Feb 15 Dinner: Salmon
Feb 15 Dinner: Salad           →   Feb 15 Dinner: Salad
```

**Sync Behavior:**
- One Paprika meal entry = one Skylight meal sitting
- Recipe-based meals sync a linked Skylight meal recipe
- Full recipe content is synced from Paprika
- Paprika is source of truth for recipe data

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

**Meal sync issues?**
- Ensure you have meal plans in Paprika for upcoming dates
- Check that meal types are enabled in your configuration
- Verify your Skylight frame has meal calendar functionality enabled

**Multiple meals not combining?**
- This is expected behavior: meals are intentionally kept as separate sittings
- Multiple meals of the same type on the same day stay separate in Skylight

**Command not found?**
- Restart your terminal after installation
- Make sure `~/.local/bin` is in your PATH

**Need help?**
- Report issues: [GitHub Issues](https://github.com/aarons22/whisk/issues)
- Check logs for detailed error information

## Requirements

- Python 3.10+
- **Paprika Recipe Manager account** with:
  - Grocery lists (for list sync)
  - Meal planning feature (for meal sync)
- **Skylight Calendar** with:
  - Grocery lists functionality enabled
  - Meal calendar/sitting functionality enabled
- Stable internet connection for API access

---

That's it! Whisk runs quietly in the background keeping your grocery lists and meal plans in sync across all your devices. Plan your meals in Paprika, shop with Skylight, and never worry about keeping everything up to date manually.

## License

Licensed under the [MIT License](LICENSE).
