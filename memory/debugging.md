# Monero Farm — Debugging Log

## Error → Fix Mapping

| # | Error/Symptom | Root Cause | Fix | Date |
|---|---------------|------------|-----|------|
| 1 | (template) | | | |

## Troubleshooting Checklist

### monerod won't start
1. Check disk space: `df -h /var/lib/monero`
2. Check permissions: `ls -la /var/lib/monero` (should be monero:monero)
3. Check logs: `journalctl -u monerod -n 50 --no-pager`
4. Check port conflict: `ss -tlnp | grep 18081`

### P2Pool no shares found
1. Verify monerod is fully synced: health-check.sh
2. Check ZMQ connection: `journalctl -u p2pool -n 50 | grep zmq`
3. Verify wallet address is set (not TODO_YOUR_PRIMARY_ADDRESS)

### XMRig 0 hashrate
1. Check hugepages: `cat /proc/sys/vm/nr_hugepages` (need >= 1280)
2. Check P2Pool stratum: `curl -s http://127.0.0.1:8082/2/summary | jq .connection`
3. Check if running as miner user (not root)

### Low hashrate
1. Verify hugepages: `cat /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages`
2. Check CPU governor: `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` (should be performance)
3. Check NUMA: `numactl --hardware` (bind to local node for best perf)
