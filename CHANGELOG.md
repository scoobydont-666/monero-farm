# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- SECURITY.md policy document
- CHANGELOG.md (this file)
- CONTRIBUTING.md guidelines (planned)

## [2026-07-08] - 1.2.0

### Changed
- **MAJOR**: Mining operations suspended (MAINTENANCE MODE)
- P2Pool relay continues on miniboss (main/mini/nano sidechains)
- XMRig disabled across all fleet hosts (giga, mecha, mega, mongo)

### Security
- Wallet address moved to Ansible Vault (PR #8)
- Gitleaks CI gate added

## [2026-04-20] - 1.1.0

### Added
- Documentation: Maintenance mode README update
- Architecture documentation

## [2026-04-06] - 1.0.0

### Added
- Initial public release
- monerod full node management (v0.18.4.6)
- P2Pool multi-instance relay (main/mini/nano) v4.14
- XMRig CPU miner management v6.25.0
- Ansible roles: base, monero, p2pool, xmrig, monitoring
- Prometheus/Grafana monitoring stack (5 exporters)
- systemd service management (no K3s)

### Security
- UFW deny-by-default + LAN allowlist
- monerod RPC bound to 127.0.0.1 only
- XMRig API on port 8082 (not default 8080)

## [2026-01-15] - 0.9.0 (pre-release)

### Added
- Bootstrap installer script (`mega-monero-p2pool.sh`)
- monerod + P2Pool on miniboss
- Initial Ansible role prototypes

---

## Release Template

### Added
- New features

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Vulnerability fixes
