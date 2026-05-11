#!/usr/bin/env bash
set -euo pipefail

# Monero Farm — Orchestrated Restart
# Correct dependency order:
#   stop xmrig (no-op if not running) → stop all p2pool instances
#   → restart monerod → poll RPC until synchronized → restart p2pool instances
#   → start xmrig (gated on systemd unit being enabled)

P2POOL_INSTANCES=(p2pool-main p2pool-mini p2pool-nano)
MONEROD_RPC="http://127.0.0.1:18081/json_rpc"
SYNC_POLL_INTERVAL=5
SYNC_TIMEOUT=300

echo "Monero Farm — Orchestrated Restart"
echo "==================================="

echo "[1/5] Stopping xmrig (no-op if not running)..."
systemctl stop xmrig 2>/dev/null || true

echo "[2/5] Stopping all P2Pool instances..."
for svc in "${P2POOL_INSTANCES[@]}"; do
    systemctl stop "$svc" 2>/dev/null && echo "  stopped $svc" || echo "  $svc not running"
done

echo "[3/5] Restarting monerod..."
systemctl restart monerod

echo "[4/5] Waiting for monerod to synchronize (timeout ${SYNC_TIMEOUT}s)..."
elapsed=0
while true; do
    if curl -sf --max-time 3 -X POST "$MONEROD_RPC" \
        -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' \
        | grep -q '"synchronized":true'; then
        echo "  monerod synchronized."
        break
    fi
    if (( elapsed >= SYNC_TIMEOUT )); then
        echo "ERROR: monerod did not synchronize within ${SYNC_TIMEOUT}s — aborting P2Pool start." >&2
        exit 1
    fi
    sleep "$SYNC_POLL_INTERVAL"
    (( elapsed += SYNC_POLL_INTERVAL ))
    echo "  ...waiting (${elapsed}s elapsed)"
done

echo "[5/5] Starting P2Pool instances..."
for svc in "${P2POOL_INSTANCES[@]}"; do
    systemctl start "$svc" 2>/dev/null && echo "  started $svc" || echo "  $svc not enabled"
done

# XMRig: start only if the unit is enabled (rainbow is the mining host; this is a no-op on miniboss)
if systemctl is-enabled xmrig 2>/dev/null | grep -q "^enabled$"; then
    echo "Starting xmrig..."
    systemctl start xmrig
fi

echo ""
echo "Service status:"
for svc in monerod "${P2POOL_INSTANCES[@]}" xmrig; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
    printf "  %-16s %s\n" "$svc" "$STATUS"
done

echo ""
echo "Done. Run ./health-check.sh for full verification."
