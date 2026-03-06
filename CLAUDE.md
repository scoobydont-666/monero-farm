# Monero Farm — Hydra Head #2

## Project Location
/opt/monero-farm

## Purpose
Cryptocurrency mining operations leveraging idle GPU/CPU capacity on the Hydra cluster.

## Parent Project
Part of Project Hydra (/opt/hydra-project/HYDRA_MASTER_PROJECT.md)

## Hardware
- **GIGA (gateway)**: 3x RTX 3060 12GB (2x RTX 5080 planned upgrade)
- **MEGA (worker)**: 1x RTX 5080 16GB
- Mining uses idle GPU/CPU cycles — yields to AI workloads (Christi, ComfyUI)

## Architecture
- XMRig for Monero mining (CPU + GPU)
- Systemd service with idle-time scheduling
- Prometheus metrics for hashrate, power, profitability
- Auto-stop when AI workloads demand GPU

## Key Rules
- Mining MUST yield to AI inference workloads — never compete for GPU during active queries
- All configs in /opt/monero-farm/config/
- Operational scripts in /opt/monero-farm/scripts/
- Service user: aisvc (same as other Hydra services)

## Status
Scaffold phase — directory structure created, no operational code yet.

## Planned Milestones
| Phase | Description | Status |
|-------|-------------|--------|
| Scaffold | Directory, CLAUDE.md, initial docs | Complete |
| M6: Core Mining Ops | XMRig config, pool setup, monitoring | Not started |
| M7: GPU/CPU Scheduler | Idle-time mining, workload priority | Not started |
