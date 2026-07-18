# Changelog

All notable changes to SOPVM will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0] - 2026-07-18

### Added
- **M2**: SOP YAML parser with JSON Schema validation and semantic checks
- **M3**: AST→IR lowering pass (`CompiledProgram`, `IrNode`)
- **M4**: Capability token parser, policy loader, static checker (`satisfies()`, `check()`)
- **M5**: Paging pass (`apply_paging()`) and compile pipeline (`compile_sop()`)
- **M6**: Runtime executor with state machine, event hooks, infinite-loop detection
- **M7**: Capability gate — runtime tool-call interception and enforcement
- **M8**: Plugin architecture — `ToolProvider`, `ProviderRegistry`, sandbox wrapper
- **M9**: LangGraph integration adapter (`as_langgraph_node()`)
- **M10**: Telemetry — `Event`, `EventType` enum, `TelemetrySink`, `JsonlSink`
- **M11**: CLI with `compile`, `check`, `run`, `trace` subcommands (click)
- **M12**: Adversarial security test suite (25+ test cases, CI-gated)
- **M13**: Public API stabilization — `sopvm.compile()`, `sopvm.check()`, `sopvm.Runtime`
- Pre-commit hook (`sopvm-check`)
- IR version validation — `UnsupportedIrVersionError` for unsupported IR files
- API compatibility CI check script
- JSON Schema for SOP YAML format (`schemas/sop.schema.json`)
- JSON Schema for capability tokens (`schemas/capability.schema.json`)

### Security
- **M4**: Static capability checker catches policy ceiling violations at compile time
- **M7**: Runtime capability gate denies out-of-scope tool calls
- **M8**: Provider sandbox catches lying providers (defense in depth)
- **M12**: IR tampering detection — runtime re-validates `capabilities_paged` against policy
- **M12**: Adversarial test corpus covers 25+ escalation techniques

### Changed
- **M5**: Replaced M3's placeholder `capabilities_paged = capabilities_declared` with real policy-resolved subset
- **M10**: Extended M6's stub `Event` with full telemetry schema (EventType enum, timestamps, run_id)

### Fixed
- **M12**: Fixed IR tampering gap — executor now re-validates capabilities_paged at run time when policy is provided

## [0.1.0] - 2026-07-18

### Added
- Initial release: Markdown+frontmatter SOP parser (M1)
- `sopvm compile --check` CLI command
- Unit tests for parser
