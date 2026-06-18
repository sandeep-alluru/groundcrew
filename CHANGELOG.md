# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-17

### Added
- Content-addressed `FileState`, `StateSnapshot`, and `SnapshotDiff` data model backed by SHA-256
- `ActionSpec` and `ActionReceipt` semantic action codec — portable, content-addressed
- `Oracle` context manager: captures filesystem state before/after any action
- `ReceiptStore` — SQLite-backed persistence of all action receipts
- Rich terminal output, JSON, and Markdown formatters
- Click CLI: `capture`, `diff`, `log`, `status` subcommands
- FastAPI REST server: `/capture`, `/receipt/{id}`, `/receipts`, `/diff/{id}`, `/health`
- MCP server (`openveritas-mcp`) for native Claude tool integration
- 69 unit tests, 90% branch coverage

[Unreleased]: https://github.com/sandeep-alluru/openveritas/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeep-alluru/openveritas/releases/tag/v0.1.0
