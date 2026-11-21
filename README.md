# ForeverContext

Read-only character context for World of Warcraft: Forever. Choose the opt-in live pixel bridge below or use the SavedVariables snapshot fallback.

## Setup (Windows)

Clone this repository into a folder you control. The live screen-capture backend is Windows-only; the snapshot reader uses the Python standard library.

From the repository in Git Bash, with Python 3.12 installed:

```bash
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe tools/install_addon.py
```

The installer targets the standard `_forever_` installation by default. Run `tools/install_addon.py --help` for options; it refuses to overwrite different installed files silently. Back up any existing addon before an update. Restart WoW if this is a newly installed addon, or `/reload` if updating an enabled addon.

For development/tests, install `requirements-dev.txt`. Tests use `lupa.lua51`, not an arbitrary Lua runtime. Run with a writable scratch directory:

```bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
export TMPDIR="${TMPDIR:-$PWD/.scratch}"
mkdir -p "$TMPDIR"
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Generated character data, backups, environments, credentials, and local development handoffs are excluded from Git. Do not force-add those files.

## Live use (1.1.2)

The compact transmitter is a **256×36-pixel, click-through grid flush against the top-right edge**, with no text label. The companion captures the corresponding bounded top-right client region. Load addon updates with one `/reload`; the companion must also be restarted after its code changes. Version 1.1.1 used the larger top-left grid; old and new corner layouts must not be mixed. Combat/retry behavior was not changed by this cosmetic update.

1. Enable the addon. After an installation/update, `/reload` once to load the new code.
2. Enter `/fctx live on`. This setting persists; `/fctx live off` disables the transmitter. `/fctx live status` prints one requested diagnostic.
3. Start `LiveCapture.cmd` from this project (or run `.venv/Scripts/python.exe tools/live_capture.py`). Keep the WoW client and strip visible and unoccluded; minimized clients cannot be read. Stop the companion with Ctrl+C. No automatic startup task is installed.
4. Ask Hermes about your gear. No per-question export or reload is needed while the companion and transmitter are running. Bank data still requires a bank visit and remains last-seen data.

The bridge is **addon pixels → passive local capture → validated local files → read-only MCP tools**. `LiveMCP.cmd` runs the stdio MCP server; it is not an HTTP service. The eight tools expose status, character, equipment, bags, talents, stats, bank and full snapshot. Their default is to deny stale/unknown data, not label old snapshots live. An explicitly requested `allow_stale=true` keeps stale metadata visible.

Canonical live files are `data/live/current.json` (validated envelope) and `data/live/status.json` (companion health). Do not assume file existence means connected; use `tools.live_mcp.LiveReader` or the MCP tools to evaluate both files and freshness. SavedVariables outputs `data/latest.*` are separate, not automatically updated by live capture.

Actual client-to-companion transfer and local MCP SDK queries have been verified, including the compact layout in version 1.1.2. Personal character snapshots are not included in this repository. Native registration of this custom server in the development Hermes session remains unverified/catalog-blocked; the local server/SDK and direct reader work independently. No Hermes configuration was hand-edited.

Version 1.1.1 guards the client's public `issecretvalue` API before comparing or formatting values, following installed PawnForever's pattern. Restricted values are omitted/null with a warning, never recovered or reported as zero. The guard passed mocked tests and independent review. After the user's reload, version 1.1.1 successfully transmitted real validated client snapshots; the actual engine-opaque restricted-value path has not been deliberately induced.

Transport design sources and boundaries are in `LIVE_SPEC.md` and `LIVE_REFERENCES.md`. Tests cover framing, checksums, replay/stale handling, scaled pixel decoding, Lua rendering, Windows-companion behavior and real stdio MCP initialization/list/call. Passive read-only design is not a claim of Blizzard policy approval.

## Snapshot fallback: first use

1. Enable **ForeverContext** in WoW's AddOns list. If the newly installed addon is not listed, restart the game. Existing characters may need to return to character selection to enable a new addon.
2. Log into your character and wait a few seconds for item data.
3. Open your bank once if you want bank items included. Close it normally afterward.
4. In chat, enter `/fctx save`, then `/reload`.
5. In Hermes ask: **“Refresh my ForeverContext snapshot and compare my gear for Prot and Ret.”** Hermes can run the local reader; you do not have to paste inventory screenshots.

Alternatively, double-click `Refresh.cmd` after step 4. It imports the saved snapshot and creates `data/latest.json` and `data/latest.md`. It does not send a chat message or automatically inject data into Hermes. Ask Hermes to read those files, or attach `data/latest.md`.

`/fctx` or `/fctx export` opens a copyable JSON export in game if you prefer manual sharing. `/fctx status` reports scan/cache information. `/fctx help` lists commands.

## What is captured

- Equipped item slots and carried bag contents, including full item hyperlinks (random suffixes/enchants preserved).
- Item tooltips and available client item stats. Uncached data is marked pending rather than fabricated.
- Character identity, level, zone, money, client build, learned talents, and available character stats.
- Bank inventory **last seen while the bank was open**, separately cached per character, with a timestamp. Unknown bank data is not an empty bank.

The JSON is the canonical data. The Markdown is a readable view. The exporter deliberately does **not** assign stat weights or pretend to simulate optimal DPS. Inventory-read failures retain same-character last-seen items with explicit `equipmentKnown` / `bagsKnown` flags, separate capture timestamps, and warnings; read those before assuming the arrays reflect current gear.

## Snapshot fallback freshness

WoW updates the snapshot in addon memory on relevant events. The saved file on disk is refreshed when WoW saves SavedVariables, normally on `/reload` or logout. `/fctx save` refreshes in-memory data; it cannot independently flush the file to disk.

- Refresh before asking about newly equipped or looted gear.
- Opening a bank is required to update bank information. A new gear snapshot does not make an older bank snapshot current.
- The reader reports capture time and warns when a character snapshot is over 30 minutes old.
- Snapshot mode needs no companion. Live mode has an opt-in local companion; neither mode installs a background uploader or startup task.

## Local commands

Run from this project folder (Git Bash):

```bash
.venv/Scripts/python.exe tools/read_snapshot.py
.venv/Scripts/python.exe tools/read_snapshot.py --character 'Name-Realm'
.venv/Scripts/python.exe tools/read_snapshot.py --input 'C:/path/to/ForeverContext.lua'
.venv/Scripts/python.exe tools/read_snapshot.py --input 'C:/path/to/copied-export.json'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The reader only searches account SavedVariables files named `ForeverContext.lua` in the configured Forever installation. If multiple different character snapshots are found, select a character explicitly. It never executes Lua from disk. Malformed imports leave previous outputs untouched; previous outputs are not proof that a failed refresh succeeded.

## Project and installed files

- Source: wherever you clone this repository
- Addon source: `addon/ForeverContext`
- Installed addon: `C:/Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns/ForeverContext`
- Snapshot source: `_forever_/WTF/Account/<account>/SavedVariables/ForeverContext.lua`
- Generated local context: `data/latest.json` and `data/latest.md`

Only the new ForeverContext addon folder should be deployed; existing addons and the autofisher project are not modified.

## Safety and privacy

No game input automation, fishing integration, process-memory reads, networking from the addon, credentials, or automatic equipping/selling/deleting. Character data stays on your PC unless you share it or ask a model to analyze it. Such analysis sends selected data through your configured model/provider like other chat context. Do not publish the snapshot if you do not want to share character names, gear, gold, and inventory.

SavedVariables are parsed as a restricted data-only syntax, never with Lua execution. Account folder identifiers are not copied into generated summaries. A bank cache is intentionally stale until observed again.

## Validation boundary

Python reader tests and a Lua 5.1 harness exercise the addon against mocked client APIs. These are developer fixtures, **not your real inventory**. The current suite has 77 tests. Actual snapshot and live capture integration were additionally exercised against the running client; this does not prove every bank, tooltip, combat-restricted API or client layout works. If something fails, retain the exact Lua error and requested status output. The companion keeps screen captures transient and does not store screenshots by default.

No fake character snapshots are placed in `data/`.

### 1.0.1 compatibility notes

- Automatic scans, errors, and `/fctx export` are silent in chat. Errors are retained for explicit `/fctx status`; status/save/help each emit at most one requested message.
- Forever can deliberately hide realm names. Exports keep `realm: ""` and `realmKnown: false`; the reader accepts an unknown realm only with a valid player GUID, displays it as unknown, and never guesses a realm. Existing schema-1 exports with named realms remain supported.
- Talents use the legacy API where available, otherwise the installed Forever client's `C_ClassTalents` / `C_Traits` pattern: active config, trait groups, group currency, actual learned nodes and spell names. No static class build or level-derived points are substituted. Incomplete reads mark trees unknown; staged changes are explicitly not a confirmed build. Trait nodes retain raw IDs/coordinates rather than inventing classic tier/column positions.
- JSON encodes vertical bars as `\u007c` so the export EditBox cannot render and strip item hyperlinks. Decoding JSON restores original pipes. Each captured item also includes `itemString` when recoverable from its source link, including enchant/suffix fields. Old name-only pasted links remain literal and are labeled incomplete; lost fields are not reconstructed.
- JSON pasted into a `.txt` file can be imported with `--input` as well as `.json` or SavedVariables Lua. The restricted Lua parser is unchanged.

The C_Traits implementation was cross-checked against installed `ClassicUIForever/UI/TraitTree.lua`, `ClassicUIForever/Skills/TalentsTree.lua`, `PawnForever/Scales.lua`, and `TalentsForeverBook/Game.lua`. RXPGuides' installed ItemUpgrades reader explicitly disables itself when the legacy talent API is absent. Automated Lua 5.1 checks are not a replacement for a fresh in-game export after deployment.
