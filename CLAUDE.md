# Monero Farm — Project Hydra Head #2

## Current Status (2026-04-06)
**P2Pool relay only. NO XMRig mining on any fleet host.** Decision: Josh has decided — no mining anywhere. Only P2Pool relay on miniboss stays running (main, mini, nano sidechains). monerod full node continues to support P2Pool as the backing blockchain source. All XMRig services disabled across giga, mecha, mega, mongo.

## Project Location
/opt/monero-farm

## Purpose
XMR mining farm management — monerod full node + P2Pool decentralized mining relay. All services managed via systemd (NOT K3s). This is Hydra Head #2.

## Parent Project
Part of a multi-project AI platform umbrella.

## Origin
Bootstrapped by `/mnt/data/mega-monero-p2pool.sh` — a single-shot installer that set up the full stack on miniboss. The Ansible roles in this project are the "v2" that codifies and extends that script for fleet management.

## Directory Structure
```
/opt/monero-farm/
├── CLAUDE.md                   # This file
├── ansible/
│   ├── inventory/hosts.yml     # Fleet inventory
│   ├── roles/
│   │   ├── base/               # Hugepages, users, UFW, NTP
│   │   ├── monero/             # monerod download + config + systemd
│   │   ├── p2pool/             # P2Pool download + multi-instance systemd
│   │   ├── xmrig/              # XMRig download + config per rig
│   │   └── monitoring/         # Exporters, Prometheus, Grafana
│   └── site.yml                # Master playbook
├── config/                     # Reference configs (Ansible is authoritative)
│   ├── monerod.conf
│   ├── p2pool-flags.conf
│   └── xmrig/config.json
├── docker/systemd/             # Reference systemd units (Ansible is authoritative)
│   ├── monerod.service
│   ├── p2pool.service
│   └── xmrig.service
├── scripts/
│   ├── health-check.sh         # Full service health audit
│   ├── hashrate-summary.sh     # XMRig HTTP API poller
│   ├── backup.sh               # Backup configs + wallet data
│   └── restart-all.sh          # Orchestrated service restart
├── docs/
│   └── architecture.md         # Architecture overview
└── memory/
    ├── MEMORY.md               # Key facts summary
    ├── architecture.md         # Architecture decisions
    └── debugging.md            # Error → fix mapping
```

## Ansible Roles

| Role | Purpose | Binary Install | Key Templates |
|------|---------|----------------|---------------|
| base | Users, hugepages, UFW (LAN-only), NTP | — | — |
| monero | monerod full node | Downloads from getmonero.org | monerod.conf.j2, monerod.service.j2 |
| p2pool | Multi-instance P2Pool (main + mini + nano) | Downloads from GitHub releases | p2pool.service.j2 (looped per instance) |
| xmrig | XMRig CPU miner | Downloads from GitHub releases | config.json.j2, xmrig.service.j2 |
| monitoring | Exporters + Prometheus + Grafana | — | prometheus.yml.j2, alerts, dashboard |

### Usage
```bash
# Full deploy
ansible-playbook -i inventory/hosts.yml site.yml --connection=local

# Dry run
ansible-playbook -i inventory/hosts.yml site.yml --check --diff --connection=local

# Single role
ansible-playbook -i inventory/hosts.yml site.yml --tags monitoring --connection=local
```

## Current Versions (pinned in role defaults)

| Component | Version | Default Source |
|-----------|---------|---------------|
| monerod | v0.18.4.6 | downloads.getmonero.org |
| P2Pool | v4.14 | GitHub SChernykh/p2pool |
| XMRig | v6.25.0 | GitHub xmrig/xmrig |

## Service Port Map

| Service | Port | Bind | Notes |
|---------|------|------|-------|
| monerod RPC | 18081 | 127.0.0.1 | Restricted RPC — loopback only |
| monerod P2P | 18080 | 0.0.0.0 | Peer-to-peer (needs inbound) |
| monerod ZMQ | 18083 | 127.0.0.1 | ZMQ pub for P2Pool block notifications |
| P2Pool mini stratum | 3333 | 0.0.0.0 | Mini sidechain — miners connect here |
| P2Pool main stratum | 4444 | 0.0.0.0 | Main sidechain — miners connect here |
| P2Pool P2P (mini) | 37888 | 0.0.0.0 | P2Pool mini sidechain gossip |
| P2Pool P2P (main) | 37889 | 0.0.0.0 | P2Pool main sidechain gossip |
| P2Pool P2P (nano) | 37890 | 0.0.0.0 | P2Pool nano sidechain gossip (when enabled) |
| P2Pool local-api (mini) | 37900 | 127.0.0.1 | P2Pool mini JSON API |
| P2Pool local-api (main) | 37901 | 127.0.0.1 | P2Pool main JSON API |
| P2Pool local-api (nano) | 37902 | 127.0.0.1 | P2Pool nano JSON API (when enabled) |
| monerod-exporter | 18090 | 127.0.0.1 | Prometheus monerod metrics |
| unified-exporter | 18096 | 127.0.0.1 | Prometheus monerod + P2Pool combined (163 metrics) |
| p2pool-builtin | 18095 | 127.0.0.1 | P2Pool native Prometheus metrics |
| observer-exporter | 8000 | 127.0.0.1 | Scrapes p2pool.observer for miner stats |
| XMRig HTTP API | 8082 | 127.0.0.1 | **NOT 8080** (avoids OpenWebUI conflict) |
| Prometheus | 9090 | 127.0.0.1 | Monitoring server |
| Grafana | 3000 | 0.0.0.0 | Dashboard UI (LAN-only via UFW) |
| node-exporter | 9100 | 127.0.0.1 | System metrics |
| monero-wallet-rpc | 18084 | 127.0.0.1 | Wallet RPC for tax record extraction (not yet deployed) |

## Critical Rules

1. **P2Pool pool selection**: nano if fleet < 1 KH/s, mini if 1–10 KH/s, main if > 10 KH/s
2. **Wallet address**: Set in `ansible/inventory/hosts.yml` as `monero_wallet_address`
3. **monerod RPC**: Always bind 127.0.0.1, never 0.0.0.0
4. **Hugepages**: `vm.nr_hugepages` MUST be >= 1280 before XMRig starts (Ansible base role handles this)
5. **Tax records**: Use `monero-wallet-rpc get_transfers` as source of truth; log FMV at receipt per IRS Notice 2014-21
6. **Systemd only**: All services via systemd — NOT K3s (CPU affinity for RandomX, no cgroup interference)
7. **All services run as root** — the planned monero/miner user migration has not been done
8. **Blockchain data**: `/var/lib/monero` — needs ~200 GB NVMe headroom (pruned node, currently 253 GB)
9. **XMRig HTTP API port**: 8082, NOT default 8080 (collision avoidance with OpenWebUI on gateway)
10. **Idempotent always**: Never break running services. Verify against script, live system, and docs before changes.
11. **LAN subnet**: Set `lan_subnet` in `roles/base/defaults/main.yml` — UFW rules restrict stratum + Grafana to LAN only

## Monitoring Stack

Five Prometheus scrape targets:
1. **monerod-exporter** (:18090) — 10 basic monerod gauges (height, peers, difficulty)
2. **unified-exporter** (:18096) — 163 metrics combining monerod RPC + P2Pool data-api + txpool stats
3. **p2pool-builtin** (:18095) — Native P2Pool metrics (heights, hashrates, miner counts per sidechain)
4. **observer-exporter** (:8000) — Scrapes p2pool.observer for external miner statistics
5. **node-exporter** (:9100) — Standard system metrics (CPU, RAM, disk)

Alert rules: MonerodDown, MonerodNotSyncing, MonerodZeroPeers, P2PoolExporterDown, P2PoolNoStratumConnections, P2PoolLowHashrate, P2PoolNoBlocksFoundRecently, HighCPULoad, LowDiskSpace, HighRAMUsage

## Shared Services Matrix (vs other Hydra heads)

| Service | Monero Farm | Christi | STR Intel |
|---------|-------------|---------|-----------|
| Ollama (inference) | No | Yes | Yes |
| ChromaDB (vector) | No | Yes | Yes |
| Redis (cache) | No | Yes | Yes |
| Traefik (routing) | No | Yes | Yes |
| Prometheus | Yes | Yes | Yes |
| GPU allocation | CPU only | GPU0 | GPU0 |
| Auth (JWT) | No | Yes | Yes |
| Billing | No | Yes | Yes |
| NFS | No | Yes | Yes |

Monero Farm is the most independent head — it shares almost nothing with the AI infrastructure except the Hydra umbrella and Prometheus monitoring.

## Debugging Quick Reference

| Symptom | Check | Fix |
|---------|-------|-----|
| monerod not syncing | `curl -s http://127.0.0.1:18081/json_rpc -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' \| jq .result.synchronized` | Wait for sync; check disk space |
| P2Pool no shares | `journalctl -u p2pool-mini -n 50` | Verify monerod synced; check ZMQ port 18083 |
| XMRig 0 hashrate | `curl -s http://127.0.0.1:8082/2/summary \| jq .hashrate` | Check hugepages; verify P2Pool stratum reachable |
| Low hashrate | `cat /proc/sys/vm/nr_hugepages` | Should be >= 1280 for RandomX |
| Port conflict | `ss -tlnp \| grep 8080` | XMRig must use 8082, not 8080 |
| Exporter errors | `journalctl -u p2pool-exporter -n 20` | Check monerod RPC is responsive |

## Related Projects

- Part of a multi-project platform with shared infrastructure
- **Installer Script**: Original bootstrap script (gold image)
