# Disaster Recovery Guide

## Failure Scenarios

### 1. miniboss Failure (P2Pool + monerod)

**Symptom**: P2Pool stratum unreachable, monerod not responding

**Restore time**: ~2 hours (blockchain re-sync if no backup)

#### Recovery Steps:
```bash
# On new host:
git clone https://github.com/scoobydont-666/monero-farm.git
cd monero-farm

# Configure inventory with new host IP
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
# Edit hosts.yml with new host details

# Deploy full stack
ansible-playbook -i ansible/inventory/hosts.yml ansible/site.yml \
  --tags monero,p2pool,monitoring \
  --connection=local

# If blockchain backup exists:
tar xzf /path/to/monero-blockchain-backup.tar.gz -C /var/lib/monero/
systemctl start monerod
```

### 2. monerod Corruption

**Symptom**: monerod won't start, blockchain.db corrupted

**Recovery**:
```bash
systemctl stop monerod
mv /var/lib/monero/lmdb /var/lib/monero/lmdb.corrupted

# Option A: Pruned resync (faster, ~200 GB)
monerod --prune-blockchain --data-dir /var/lib/monero --no-igd

# Option B: Full resync (slower, ~250 GB)
monerod --data-dir /var/lib/monero --no-igd

# When synced:
systemctl start monerod
```

### 3. P2Pool Out-of-Sync

**Symptom**: P2Pool shows "No blocks found", hashrate drops to 0

**Diagnosis**:
```bash
# Check monerod sync state:
curl -s http://127.0.0.1:18081/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' \
  | jq .result.synchronized

# Check P2Pool connections:
curl -s http://127.0.0.1:37900/local/stats | python3 -m json.tool
```

**Recovery**:
```bash
systemctl restart p2pool-mini
systemctl restart p2pool-main
# nano is optional — can omit if not needed
```

### 4. Disk Full

**Symptom**: services crash, monerod stops syncing

**Thresholds**:
- ⚠️ WARN: >80% full
- 🔴 CRIT: >95% full

**Action**:
```bash
# Check disk
df -h /var/lib/monero

# Prune blockchain (if not already pruned)
monerod --prune-blockchain --data-dir /var/lib/monero

# Or move to larger disk
systemctl stop monerod
rsync -av /var/lib/monero/ /new/disk/monero-data/
# Update mounts + restart
```

### 5. Security Breach

**Symptom**: Unknown processes, network connections, unauthorized access

**Immediate Steps**:
1. Disconnect host from network
2. Rotate ALL credentials (vault password, SSH keys, wallet)
3. Generate new wallet and transfer remaining funds
4. Rebuild from clean OS + Ansible

## Backup Strategy

| Data | Frequency | Method | Retention |
|------|-----------|--------|-----------|
| Blockchain state | Weekly | tar + compress | 4 weeks |
| Wallet keys | After each tx | paper wallet + USB | Permanent |
| Ansible configs | Git commit | GitHub | Permanent |
| Prometheus data | Daily | promtool backup | 90 days |

### Backup Commands

```bash
# Blockchain backup
# Requires monerod STOPPED for consistent snapshot
systemctl stop monerod
tar czf /tmp/monero-backup-$(date +%Y%m%d).tar.gz \
  -C /var/lib/monero lmdb --exclude lmdb/blockchain.bin-lock
systemctl start monerod

# Config backup
rsync -av /etc/monero/ /backup/monero-config/
rsync -av /opt/p2pool/ /backup/p2pool-config/
```

## Monitoring Alerts Recovery

See `monitoring/alert-rules.md` for detailed alert responses:

| Alert | Action |
|-------|--------|
| MonerodDown | Check process, restart service |
| MonerodNotSyncing | Verify network, check disk space |
| P2PoolNoStratumConnections | Verify monerod sync, check port |
| P2PoolLowHashrate | Check XMRig processes, verify stratum |
| HighDiskUsage | Archive/prune blockchain |

## Contact

| Role | Contact | SLA |
|------|---------|-----|
| On-call | DM Josh | 1 hour |
| Security | security@scoobydont-666.example | 2 hours |
