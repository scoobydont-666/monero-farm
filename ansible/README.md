# Ansible — Monero Farm Fleet Management

## Overview

Five roles deployed in dependency order via `site.yml`:

```
base → monero → p2pool → monitoring → xmrig
```

## Inventory Setup

```bash
cp inventory/hosts.yml.example inventory/hosts.yml
# Edit: set wallet address, host IPs, SSH user
```

### Host Groups

| Group | Purpose | Roles Applied |
|-------|---------|---------------|
| `all` | Every host in the fleet | base |
| `fullnode` | Runs monerod + P2Pool + monitoring (typically 1 host) | monero, p2pool, monitoring |
| `miners` | Runs XMRig (can be many hosts) | xmrig |

A single host can be in both `fullnode` and `miners` groups.

## Usage

```bash
# Full deploy
ansible-playbook -i inventory/hosts.yml site.yml --connection=local

# Dry run — always do this first
ansible-playbook -i inventory/hosts.yml site.yml --check --diff --connection=local

# Single role
ansible-playbook -i inventory/hosts.yml site.yml --tags base
ansible-playbook -i inventory/hosts.yml site.yml --tags monero
ansible-playbook -i inventory/hosts.yml site.yml --tags p2pool
ansible-playbook -i inventory/hosts.yml site.yml --tags monitoring
ansible-playbook -i inventory/hosts.yml site.yml --tags xmrig
```

## Role Reference

### base

Creates system users (`monero`, `miner`), configures hugepages for RandomX, sets up UFW with LAN-only access, enables NTP.

**Key variables** (`roles/base/defaults/main.yml`):
- `hugepages_count`: Number of 2MB hugepages (default: 1280 = 2.5 GB)
- `lan_subnet`: CIDR for UFW source restriction (default: `192.168.0.0/16` — override in inventory for your actual LAN)

### monero

Downloads and installs monerod, deploys config file and systemd unit.

**Key variables** (`roles/monero/defaults/main.yml`):
- `monero_version`: Binary version to download (default: `0.18.4.6`)
- `monero_zmq_port`: ZMQ port for P2Pool (default: `18083`)
- `monero_prune_blockchain`: Enable pruning (default: `true`)

### p2pool

Downloads P2Pool binary, deploys multiple sidechain instances via loop. Each instance gets its own systemd unit, stratum port, P2P port, and local API port.

**Key variables** (`roles/p2pool/defaults/main.yml`):
- `p2pool_version`: Binary version (default: `4.14`)
- `p2pool_instances`: List of `{mode, stratum_port, p2p_port, local_api_port}` dicts
- `monero_wallet_address`: Set in inventory, not here

### monitoring

Deploys four Prometheus exporters, Prometheus config with alert rules, and Grafana with file-provisioned datasource and dashboard.

**Key variables** (`roles/monitoring/defaults/main.yml`):
- `monerod_exporter_port`: Default `18090`
- `unified_exporter_port`: Default `18096`
- `observer_exporter_port`: Default `8000`
- `prometheus_scrape_interval`: Default `5s`

### xmrig

Downloads XMRig binary, deploys config and systemd unit. Points at the P2Pool stratum specified in inventory.

**Key variables** (`roles/xmrig/defaults/main.yml`):
- `xmrig_version`: Binary version (default: `6.25.0`)
- `xmrig_threads`: `auto` or integer thread count
- `xmrig_http_port`: API port (default: `8082`, NOT 8080)

## Adding a New Miner

Edit `inventory/hosts.yml`:

```yaml
miners:
  hosts:
    existing-miner:
      ansible_host: 192.168.x.x
      # ...
    new-miner:
      ansible_host: 192.168.x.x
      ansible_user: youruser
      xmrig_threads: auto
      xmrig_api_port: 8082
```

Then run:

```bash
ansible-playbook -i inventory/hosts.yml site.yml --tags base,xmrig --limit new-miner
```

## Upgrading Binaries

Update the version in the appropriate `defaults/main.yml` and re-run:

```bash
# Example: upgrade monerod
# Edit roles/monero/defaults/main.yml → monero_version: "0.18.4.7"
ansible-playbook -i inventory/hosts.yml site.yml --tags monero
```

The role checks the installed version and only downloads if it doesn't match.
