# Operational Scripts

Utility scripts for day-to-day Monero Farm operations. These are standalone bash scripts that work independently of Ansible.

## health-check.sh

Full service health audit. Checks monerod sync state, P2Pool stratum, XMRig hashrate, hugepages configuration, and disk space.

```bash
./health-check.sh
```

Returns exit code = number of issues found (0 = all healthy).

## hashrate-summary.sh

Polls XMRig HTTP API across all miners and displays a formatted table of hashrates, accepted shares, and uptime.

```bash
# One-shot
./hashrate-summary.sh

# Live refresh every 10 seconds
./hashrate-summary.sh --watch
```

## restart-all.sh

Orchestrated restart that respects service dependencies:

1. Stop XMRig
2. Restart P2Pool
3. Restart monerod (15s init wait)
4. Start XMRig

```bash
sudo ./restart-all.sh
```

## backup.sh

Backs up configs, P2Pool state, and wallet key files to a timestamped directory. Does **not** backup the blockchain (~250 GB — cheaper to re-sync).

```bash
./backup.sh /path/to/backup/destination
```

Creates: `$DEST/YYYY-MM-DD/` with tar archives and copied key files.
