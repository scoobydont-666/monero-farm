# XMRig Reactivation Guide

## Current State: MAINTENANCE MODE

**Mining is STOPPED as of 2026-04-06.** XMRig is disabled across all fleet hosts (giga, mecha, mega, mongo). Only P2Pool relay on miniboss remains active.

This document describes how to safely reactivate mining when conditions change.

## Prerequisites for Reactivation

Before re-enabling XMRig, verify:

- [ ] **Economic viability**: XMR price / difficulty / electricity cost supports positive margin
- [ ] **Hardware available**: GPU hosts have capacity (no AI training conflicts)
- [ ] **Cooling adequate**: GPU temps under 80°C sustained
- [ ] **Wallet ready**: Ansible Vault has valid `monero_wallet_address`
- [ ] **P2Pool healthy**: monerod synced, stratum accepting shares
- [ ] **Monitoring armed**: Prometheus alerts configured for XMRig

## Reactivation Procedure

### 1. Update Inventory

```bash
cd /opt/monero-farm
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml

# Edit hosts.yml:
# - Add miners under [miners] group
# - Set ansible_host, ansible_user
# - Configure xmrig_threads, xmrig_api_port
# - Set xmrig_autostart: true
```

### 2. Validate Hugepages

```bash
# On each miner host:
ssh <miner-host> "cat /proc/sys/vm/nr_hugepages"
# Must be >= 1280 (base role handles this via sysctl)
```

### 3. Deploy XMRig Role Only

```bash
# Dry run first:
ansible-playbook -i ansible/inventory/hosts.yml ansible/site.yml \
  --tags xmrig --check --diff

# Then deploy:
ansible-playbook -i ansible/inventory/hosts.yml ansible/site.yml \
  --tags xmrig
```

### 4. Verify Mining

```bash
# Per host:
curl -s http://<host>:8082/2/summary | jq .hashrate

# Fleet summary:
./scripts/hashrate-summary.sh

# Check P2Pool miner count:
curl -s http://miniboss:37900/local/stats | jq .miners
```

### 5. Enable Autostart

```bash
# On each miner host:
systemctl enable xmrig
systemctl start xmrig
```

## Pool Selection Logic

| Fleet Hashrate | P2Pool Sidechain | Command |
|----------------|------------------|---------|
| < 1 KH/s       | nano             | Enable nano in P2Pool vars |
| 1–10 KH/s      | mini             | Default (enabled) |
| > 10 KH/s      | main             | Default (enabled) |

Current P2Pool config in `ansible/roles/p2pool/defaults/main.yml`:
```yaml
p2pool_instances:
  - name: mini
    stratum_port: 3333
  - name: main
    stratum_port: 4444
# nano disabled by default
```

## Monitoring Reactivation

Add XMRig to monitoring:

```bash
# Deploy exporter
ansible-playbook -i ansible/inventory/hosts.yml ansible/site.yml \
  --tags monitoring,xmrig-exporter
```

Grafana dashboard: `Monero Farm > XMRig Hashrate`

## Rollback Procedure

If issues arise:

```bash
# Stop XMRig everywhere
ansible all -i ansible/inventory/hosts.yml -m systemd \
  -a "name=xmrig state=stopped" --become

# Disable autostart
ansible all -i ansible/inventory/hosts.yml -m systemd \
  -a "name=xmrig enabled=no" --become

# Update MAINTENANCE MODE note in README.md
# Commit + PR
```

## Historical Context

| Date | Event |
|------|-------|
| 2026-01-15 | Initial mining on giga (single RTX 3090) |
| 2026-02-03 | Expanded to mecha + mega |
| 2026-03-15 | Peak: 4.2 KH/s across 3 hosts |
| 2026-04-06 | **STOPPED** — AI GPU workload priority |
| 2026-07-08 | This doc created (task-11771 ST-2) |

## FAQ

**Q: Can I run XMRig on miniboss?**
A: **NO.** Global rule: "miniboss is NOT a miner — do not deploy XMRig here." miniboss runs P2Pool + monerod only.

**Q: What if GPU hosts are busy with AI training?**
A: XMRig and vLLM/Ollama cannot share GPU. Reactivate only when GPU slots are free.

**Q: How do I switch P2Pool sidechains?**
A: Edit `ansible/roles/p2pool/defaults/main.yml` to enable/disable instances, re-deploy p2pool role.
