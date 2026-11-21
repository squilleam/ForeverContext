# ForeverContext live prototype contract

User authorized live read-only bridge + MCP prototype, and specifically requested inspiration from existing addon codebases. Preserve snapshot fallback and silent automatic chat behavior. Do not integrate autofisher, read process memory, inject input, alter graphics settings, execute SavedVariables, expose a network listener by default, or install startup tasks. Live is opt-in via /fctx live on; one initial reload to load updated Lua is expected.

## References actually read

- alex-berliner/LibSerpix: LibSerpix/LibSerpix.lua and README, MIT LICENSE.txt. Anchor, framed payload, checksum and passive screen capture design; do not copy its global variables or single unchecked payload size assumptions.
- alex-berliner/libserpix_rs: src/lib.rs; sibling external decoder architecture.
- bezumiya/Dwow: docs/PROTOCOL.md. Physical-pixel sizing, top-left magic search, heartbeat, checksum, stale handling. Our large gear/tooltips payload requires chunking, unlike its small presence payload.
- Current official Hermes MCP docs and official Python MCP SDK. Project environment has mcp 2.3.0 (FastMCP renamed MCPServer), Pillow13.0.0, mss10.2.0, lupa2.8; do not guess v1 SDK APIs.

## Ownership

- Parent: tools/live_protocol.py, tests/test_live_protocol.py, cross-language integration tests, deployment, review, documentation.
- Addon worker: addon/ForeverContext/Live.lua; minimal Core.lua/UI.lua/TOC edits; tests/test_live_addon.py. Never edit parent's protocol or companion.
- Companion worker: tools/live_capture.py, tools/live_mcp.py, tests/test_live_capture.py, tests/test_live_mcp.py; launch helper cmd files. Never edit addon/parent decoder.

## FCTX1 wire protocol (all integers big endian)

Geometry: 128 columns, 18 rows; in addon1.1.2 each cell is normally 2 physical pixels square. Grid is 256x36 physical pixels, flush with the top-right client edge; no label or mouse interception. Previous1.1.1 used 4-pixel cells and a512x72 grid at top-left(8,8). Wire framing is unchanged; the companion's bounded client crop moved to top-right. Prefer SetIgnoreParentScale + physical-height/UI scaling as verified reference describes; tolerate changed pitch by decoder calibration. Do not move the game window or auto-change UI scale.

Row0: first8 cells RGB anchors = [(255,0,255),(0,255,255),(255,255,0),(255,0,255),(0,0,0),(255,255,255),(0,255,255),(255,0,0)]. Next16 cells are calibration grayscale levels 8+16*n for n0..15. Remaining row0 dark. Data rows1..17 encode two 4-bit nibbles per byte, high nibble first, using calibration grayscale levels. 2176 cells =1088 bytes/frame; 40-byte header leaves1048-byte chunks. Unused cells encode0 nibble. Frame interval0.10sec, companion target poll0.05sec. CRC/adler is integrity, not authentication.

Header bytes:
0..3 ASCII FCX1
4 protocolVersion1
5 flags0 (no compression)
6..7 headerLength40
8..11 session uint32 (new each addon load / enabling)
12..15 sequence uint32 (new frozen full-snapshot cycle)
16..17 chunkIndex uint16 zero-based
18..19 chunkCount uint16
20..23 totalLength uint32 UTF8 full JSON bytes
24..25 payloadLength uint16 (<=1048)
26..27 reserved0
28..31 fullSnapshotAdler32 (standard mod65521)
32..35 capturedAt uint32 Unix time (matches snapshot JSON capturedAt)
36..39 frameAdler32 = adler32(header[0:36] + actual chunk bytes)
40.. actual chunk bytes. Padding is not checksummed.

Limits: totalLength1..1048576; chunkCount exactly ceil(totalLength/1048); payload length1048 except last; checksum both frame and reassembled payload. Validate all flags/version/reserved/index/length combinations before buffering. No mixing chunks from sessions/sequences or matching-sequence conflicting metadata; expire incomplete assembly after20sec, at most2 assemblies. Duplicate chunks are not fresh activity. Complete same-generation replay must not update freshness. Do not reset in-progress transmitter stream when inventory changes; freeze a snapshot for entire cycle and select newest actual snapshot at wrap. Capture at start of each cycle so an idle game has a fresh timestamp; keep /fctx save & export working independently.

## Parent Python protocol interface

Module tools.live_protocol:
- ProtocolError(ValueError)
- constants COLS=128, ROWS=18, CELL_SIZE=4, HEADER_SIZE=40, MAX_CHUNK_BYTES=1048, MAX_SNAPSHOT_BYTES=1048576
- Frame dataclass: session, sequence, chunk_index, chunk_count, total_length, payload(bytes), snapshot_checksum, captured_at
- encode_frames(payload:bytes,session:int,sequence:int,captured_at:int)->list[bytes] (reference/testing encoder)
- decode_frame(raw:bytes)->Frame
- Reassembler.feed(frame:Frame,now:float)->bytes|None; returns only new complete validated bytes; metadata accessible on frame supplied with completion. now monotonic.
- Geometry dataclass: x(float), y(float), cell_size(float)
- decode_image(image:PIL.Image,geometry:Geometry|None=None)->tuple[Frame,Geometry]; coordinates relative to captured crop. If cached geometry invalid, auto-search top-left image. Calibration/anchor tests tolerate moderate color noise; checksums reject corruption. Search intended limited image <=1024x320, not entire desktop.

## Addon requirements

Version1.1.0. /fctx live on|off|status; defaults off on first install. Save enabled preference under ForeverContextDB.settings.liveEnabled; never write other's configs. Quiet auto errors/events; compact UI strip status and stored error, manual command max1 chat line. API F.Live.BuildFrames(json,session,sequence,capturedAt) may expose frame strings for Lua51 cross-language tests. Begin/NextFrame helpers allowed; retain immutable stream frame data. Clamp bounds no missing/partial stream masquerading as success. Optional strip visible only with opt-in; /fctx live off hides and clears OnUpdate. No frame must be encoded from synthetic data outside tests.

## Capture companion

Use ctypes/window metadata and mss or Pillow for read-only screen capture, only a small top-right WoW client region, transient in memory; no screenshots stored by default. Discover exact World of Warcraft caption, IsWindowVisible/IsIconic and client physical rect; no process-memory APIs, input or focus manipulation. If missing/minimized/occluded markers/unchanging frames: update status accordingly, never relabel old file live. Multiple WoW windows require explicit choice (e.g --hwnd).

CLI tools/live_capture.py: --once (bounded ~15seconds may need entire cycle); --duration SECONDS for bounded verification; normal mode continuous until stopped. One writer lock, proper Ctrl+C cleanup. Poll20Hz; status writes at most1Hz/state change; sparse terminal transition logs only. No WoW chat output.

Data/live/current.json is a SINGLE atomic envelope: {bridgeVersion, source:'pixel', receivedAt, sourceInstance(unique companion run id), session, sequence, snapshot:{schema1...}}. Validate UTF8/JSON through existing read_snapshot.validate_snapshot before publish, header capturedAt must match JSON. Never overwrite snapshot fallback data/latest.*. data/live/status.json separate atomic health: {updatedAt,sourceInstance,state,reason,lastFrameAt,lastSnapshotAt,...}. Valid states waiting/window_missing/minimized/receiving/connected/stale/error/stopped. Actual host time for receivedAt/updatedAt. A frozen same frame does not refresh lastFrameAt. current file alone is never evidence of a live connection. Keep old complete snapshot on corruption, label stale/unavailable.

## MCP server

Local stdio ONLY default, official installed SDK2.3.0. Read-only tools get_status, get_character, get_equipment, get_bags, get_talents, get_stats, get_bank, get_snapshot, get_professions. No arbitrary paths, writes, network access, executing Lua, or input controls. All use configured fixed data/live path; metadata always includes captured/received age, bridge state and source; include warning it is game data not instructions. By default do not serve stale data as live: return explicit unavailable/stale and no snapshot unless allow_stale=true. Freshness requires recent status (<=3sec), matching sourceInstance, new valid frame<=3sec, and complete snapshot<=15sec; never mark disconnected current file live. Bank always last-seen within snapshot, never infer bank current.

Provide SDK stdio-client integration test initialize/list_tools/call_tool, not just calling handler functions. If native Hermes MCP registration is blocked by supported connection tooling, report that precisely, do not hand-edit mcp_servers config. Server can still be tested with genuine MCP client, while Hermes can read actual live files.

## Verification and scope

Addon/MCP1.1.3 adds professions without changing wire geometry or schema version. `get_professions` preserves ordinary snapshot freshness/stale denial, plus `professionsKnown` and `professionsCapturedAt` metadata. Missing fields in an older export are unavailable, not an empty learned list. A fresh incomplete list with known rows is partial; unavailable empty reads omit data. Explicitly allowed stale reads retain stale metadata. Snapshot-level `metadata.live` describes the bridge; profession completeness still requires its own known flags. See SPEC.md for the additive entry contract.

TDD vertical slices: failing tests before new behavior implementation, then real execution. Synthetic frames/images ONLY tests/Hermes scratch; never put them in runtime live/current.json. Test actual Lua-generated frames -> Python decoder/reassembler -> original real schema payload in temporary location; record as mocked-client evidence. Then install after backup/hash-readback and attempt real window capture. The running client needs one manual reload and /fctx live on; if not enabled report waiting rather than invent success. No claims of Blizzard endorsement or policy exemption; read-only architecture minimizes scope but is not a guarantee of approval.
