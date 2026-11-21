# ForeverContext v1 contract

Read-only WoW Forever addon + local snapshot reader. No automation, network calls from addon, game memory reading, input injection, autofisher integration, credential access, or executable SavedVariables parsing.

## Paths
- Project: repository root (wherever you clone ForeverContext)
- Addon source: addon/ForeverContext/ForeverContext.toc + Lua files
- Install destination: C:/Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns/ForeverContext
- Export SavedVariables global: ForeverContextExport (a JSON string).
- Cache SavedVariables global: ForeverContextDB (ordinary Lua table, NEVER executed by reader).
- Reader output: data/latest.json and data/latest.md; data/ is gitignored.

## JSON root (schemaVersion=1)
- schemaVersion integer 1
- addonVersion string
- capturedAt Unix timestamp
- character object: guid, name, realm, class, classId (class file token acceptable), race, faction, level, locale, zone, goldCopper as available
- client object: version, build, interfaceVersion
- equipment array of item objects with slot and slotName
- bags array of item objects with bag and slot (backpack and carried bags only)
- bank object: known boolean; capturedAt timestamp only for known bank; items array; accessible boolean; unavailable data explicitly unknown, never an empty known bank by default. Keep last seen cache separately per character. Explain stale bank data.
- talents array: tree name/index, points, talents array of {name, rank, maxRank, tier, column}; only learned talents needed; unspent points separately allowed.
- stats object: values from API; must not pretend API absence = real zero
- warnings array of strings

Each item: itemId, link (FULL original hyperlink incl enchant/random suffix), optional itemString (raw `item:...` payload extracted literally from the source link), name if cached, count, quality, equipLoc, requiredLevel, itemLevel, stats dictionary if available, tooltip array of {left,right} sanitized text. Missing item data stays identified and warning/pending status (never silently drop occupied slots). No computed gear scores or invented weighting.

## Commands/workflow
- /fctx or /fctx export: collect snapshot and show copyable JSON window.
- /fctx save: refresh in-memory snapshot, explain /reload required to flush SavedVariables file to disk (do not reload automatically).
- /fctx status: last scan, missing cached items, bank age/availability, export status.
- /fctx help: command listing.
- Event-driven debounced in-memory captures after equipment, bags, talents changes; never claim disk updated without reload/logout.
- Export frame can be Escape-closed, select all / Ctrl+C, scroll, close button.

Reader CLI intended: python tools/read_snapshot.py --wow-root 'C:/Program Files (x86)/World of Warcraft/_forever_' [--input PATH] [--output-dir PATH] [--max-age-minutes 30]. Discover only */SavedVariables/ForeverContext.lua under WTF/Account and require unambiguous selection when multiple characters/accounts. Allow --character NAME/NAME-REALM to select. Report snapshot and bank age. Do not include account-folder identifier in generated user-facing summaries. Safely parse only the one export string; do NOT eval/exec Lua. Reject malformed/incomplete JSON, oversized inputs, unsupported schema. Do not overwrite good outputs on invalid import. Atomic output writes.

## Test discipline
Use unittest + scoped .venv Python3.12 + lupa Lua5.1 runtime for addon harness if available. Write/run one failing behavior test before each implementation slice; synthetic mocked game data MUST remain tests only. User-facing data directory must never contain synthetic fixture gear. Tests should cover literal preservation, random suffix, uncached item, tooltip API fallback, bank unknown vs known empty/stale, failed reads, export slash/events, JSON escaping, UTF8, malformed input, malicious Lua, and missing real snapshot.

## Install
Never modify other addons or autofisher. Copy only our addon folder; backup existing ForeverContext if any before replacement. Verify byte hashes source vs destination. In-game load/API integration cannot be claimed without actual user/client evidence. No elevated privilege requested unless install fails; provide user-run installer fallback.
