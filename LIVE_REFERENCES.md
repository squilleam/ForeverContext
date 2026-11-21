# Live bridge design references and provenance

These projects were inspected as design references, not installed or executed. ForeverContext's FCTX1 codec/transmitter is a separate implementation and protocol. Existing addon source stays separate from the autofisher.

## LibSerpix (Alex Berliner)

- Repository: https://github.com/alex-berliner/LibSerpix
- Files actually read: `README.md`, `LibSerpix/LibSerpix.lua`, `LICENSE.txt`.
- License inspected: MIT, copyright 2023 Alex Berliner.
- Useful ideas: visible anchor colors, serializing ordinary addon data into textures, framing, length/checksum fields, passive external receiver.
- Our differences: bounded chunking for full gear/tooltips, session/sequence isolation, whole-snapshot integrity, calibrated 4-bit grayscale, explicit stale-data semantics. No production source was copied from its sender.

## libserpix_rs

- Repository: https://github.com/alex-berliner/libserpix_rs
- Files actually read: README/source listings and `src/lib.rs`.
- Useful architecture: keep external screen reading/decoding separate from addon collection; data travels out of the client only.
- Not a claim that its full Rust implementation was reviewed or reused.

## Dwow

- Repository: https://github.com/bezumiya/Dwow
- File actually read: `docs/PROTOCOL.md`.
- Useful ideas: top-left marker search, physical-pixel sizing, checksums, sequence heartbeat, handling minimized/covered windows, stale output rather than imagined current state.
- Our differences: retain full structured inventory/talent snapshots, chunk rather than truncate, preserve all item identifiers, local read-only MCP instead of Discord presence.
- No production code copied; no assertion about Blizzard approval of either project.

## Official MCP and Hermes documentation

- https://github.com/modelcontextprotocol/python-sdk
- https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver
- https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- SDK installed in this project's isolated Python3.12 environment: mcp2.3.0. FastMCP is not the v2 API; use installed MCPServer/current SDK examples and a genuine stdio client test.

## Local compatibility references

Existing PawnForever, ClassicUIForever, Syndicator, TalentsForeverBook and RXPGuides files were inspected read-only for actual Forever APIs. Their files are not modified or imported as gameplay automation.

## Policy boundary checked

- Official UI Add-On Development Policy: https://us.forums.blizzard.com/en/wow/t/ui-add-on-development-policy/24534
- Official support article "Is Third Party Software Allowed?": https://us.support.blizzard.com/en/help/article/13078
- Official developer warning on client modification/security bypass: https://eu.forums.blizzard.com/en/wow/t/prohibitions-on-third-party-software/583048

These sources do not explicitly approve this custom screen-export companion. Blizzard Support says it cannot confirm whether particular software is permitted. Read-only design is not a guarantee of policy approval or exemption. Keep source visible, addon free, performance bounded, normal operation quiet, and live mode opt-in/off by default. No client modification, security bypass, memory inspection or gameplay inputs are part of this implementation.

## Verification boundary

A read-only screen probe captured the existing WoW client's top-left 768x96 region into memory, reporting 6,055 distinct colors rather than a blank capture. No screenshot was stored. This establishes screen capture availability on this host, NOT successful FCTX1 live transfer. Synthetic pixel tests establish codec behavior only; actual addon transmission still needs live client activation and successful reconstructed data.
