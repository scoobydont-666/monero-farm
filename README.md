# Monero Farm

XMR mining farm management — **monerod** full node + **P2Pool** decentralized mining (main/mini/nano) + **XMRig** CPU miner fleet, with full **Prometheus + Grafana** observability. All services managed via **systemd** and provisioned with **Ansible**.

Part of [Project Hydra](https://github.com/scoobydont-666) — Head #2.

## Architecture

```
                         ┌─────────────────────┐
                         │    Monero Network    │
                         └──────────┬──────────┘
                                    │ P2P :18080
                         ┌──────────▼──────────┐
                         │      monerod         │
                         │  (pruned full node)  │
                         │  RPC :18081 (local)  │
                         │  ZMQ :18083 (local)  │
                         └──────┬───────────────┘
                                │ ZMQ block notifications
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │  P2Pool  │ │  P2Pool  │ │  P2Pool  │
            │  main    │ │  mini    │ │  nano    │
            │  :4444   │ │  :3333   │ │  :2222   │
            └────┬─────┘ └────┬─────┘ └────┬─────┘
                 │ stratum    │ stratum    │ stratum
                 ▼            ▼            ▼
            ┌─────────────────────────────────────┐
            │         XMRig Miner Fleet           │
            │   (CPU miners, hugepages enabled)   │
            │         HTTP API :8082              │
            └─────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Ubuntu 22.04+ (tested on 24.04)
- Ansible 2.16+
- A primary Monero wallet address

### Setup

```bash
# 1. Clone
git clone https://github.com/scoobydont-666/monero-farm.git
cd monero-farm

# 2. Create your inventory from the example
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
# Edit hosts.yml — set your wallet address, host IPs, and SSH user

# 3. Dry run (review changes before applying)
cd ansible
ansible-playbook -i inventory/hosts.yml site.yml --check --diff --connection=local

# 4. Deploy
ansible-playbook -i inventory/hosts.yml site.yml --connection=local
```

### Deploy a single role

```bash
ansible-playbook -i inventory/hosts.yml site.yml --tags xmrig --connection=local
ansible-playbook -i inventory/hosts.yml site.yml --tags monitoring --connection=local
```

## Ansible Roles

| Role | What It Does |
|------|-------------|
| **base** | Creates system users, configures hugepages (2.5 GB for RandomX), UFW firewall (LAN-only), NTP |
| **monero** | Downloads monerod binary, deploys config + systemd unit, enables pruned full node |
| **p2pool** | Downloads P2Pool binary, deploys multiple sidechain instances (main + mini, nano optional) |
| **xmrig** | Downloads XMRig binary, deploys config + systemd unit per miner host |
| **monitoring** | Deploys 4 Prometheus exporters, Prometheus config + 10 alert rules, Grafana with provisioned dashboard |

## Service Ports

| Service | Port | Bind | Purpose |
|---------|------|------|---------|
| monerod RPC | 18081 | loopback | JSON-RPC (restricted) |
| monerod P2P | 18080 | public | Peer discovery |
| monerod ZMQ | 18083 | loopback | Block notifications to P2Pool |
| P2Pool mini stratum | 3333 | LAN | Miners connect here (< 10 KH/s fleet) |
| P2Pool main stratum | 4444 | LAN | Miners connect here (> 10 KH/s fleet) |
| P2Pool nano stratum | 2222 | LAN | Miners connect here (< 1 KH/s fleet) |
| XMRig HTTP API | 8082 | loopback | Miner stats (not 8080 — collision avoidance) |
| Prometheus | 9090 | loopback | Metrics server |
| Grafana | 3000 | LAN | Dashboard UI |

## Monitoring Stack

Five Prometheus scrape targets feed the Grafana dashboard:

| Exporter | Port | Metrics |
|----------|------|---------|
| monerod-exporter | :18090 | 10 basic monerod gauges |
| unified-exporter | :18096 | 163 combined monerod + P2Pool metrics |
| p2pool-builtin | :18095 | Native P2Pool metrics per sidechain |
| observer-exporter | :8000 | External miner stats from p2pool.observer |
| node-exporter | :9100 | System CPU, RAM, disk |

### Alert Rules

MonerodDown, MonerodNotSyncing, MonerodZeroPeers, P2PoolExporterDown, P2PoolNoStratumConnections, P2PoolLowHashrate, P2PoolNoBlocksFoundRecently, HighCPULoad, LowDiskSpace, HighRAMUsage

## P2Pool Sidechain Selection

| Sidechain | Fleet Hashrate | Default Stratum | P2P Port |
|-----------|---------------|-----------------|----------|
| nano | < 1 KH/s | :2222 | 37890 |
| mini | 1 – 10 KH/s | :3333 | 37888 |
| main | > 10 KH/s | :4444 | 37889 |

By default, **main + mini** are deployed. Nano is commented out in `ansible/roles/p2pool/defaults/main.yml` — uncomment to enable.

## Operational Scripts

```bash
# Full service health audit
./scripts/health-check.sh

# Live hashrate across all miners (refreshes every 10s)
./scripts/hashrate-summary.sh --watch

# Orchestrated restart (respects dependency order)
./scripts/restart-all.sh

# Backup configs, wallet keys, P2Pool state
./scripts/backup.sh /path/to/backup/dir
```

## Current Versions

| Component | Version |
|-----------|---------|
| monerod | v0.18.4.6 |
| P2Pool | v4.14 |
| XMRig | v6.25.0 |

Update versions in `ansible/roles/*/defaults/main.yml` and re-run the playbook to upgrade.

## Security Notes

- `ansible/inventory/hosts.yml` is **gitignored** — it contains your wallet address and host IPs
- Copy `hosts.yml.example` and fill in your values
- All services run as dedicated users (`monero`, `p2pool`, `miner`, `exporter`) — not root
- systemd hardening: `ProtectSystem=strict`, `PrivateTmp`, `NoNewPrivileges`
- All RPC and exporter ports bind to loopback only
- Grafana runs HTTPS (self-signed cert, generated on first deploy)
- UFW restricts stratum + Grafana to LAN subnet
- monerod P2P and P2Pool P2P are open (required for peer discovery)

## Migration (HiveOS → Ubuntu)

For miners currently running HiveOS, `scripts/migrate/` has an in-place migration tool:

```bash
# Set required env vars
export MINIBOSS_IP=192.168.x.x          # your fullnode IP
export MINIBOSS_PUBKEY="ssh-ed25519 AAAA... user@host"

# Run from fullnode, targeting the miner
./scripts/migrate/hiveos-to-ubuntu.sh <miner-ip> [ssh-user]
```

Also includes `user-data` for Ubuntu autoinstall — edit the placeholders (`YOUR_SSH_PUBLIC_KEY_HERE`, `FULLNODE_IP`, LAN CIDR) before use.

## Origin

This project was bootstrapped by a single-shot installer script. The Ansible roles are the "v2" that codifies, extends, and fixes that script for repeatable fleet management.

## License

[MIT](LICENSE)
