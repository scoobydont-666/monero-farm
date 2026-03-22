#!/usr/bin/env bash
set -euo pipefail

# Monero Farm — Orchestrated Restart
# Restarts services in dependency order: monerod → p2pool → xmrig

echo "Monero Farm — Orchestrated Restart"
echo "==================================="

echo "[1/3] Stopping xmrig..."
systemctl stop xmrig 2>/dev/null || true
sleep 2

echo "[2/3] Restarting p2pool..."
systemctl restart p2pool 2>/dev/null || echo "  p2pool not managed by systemd"
sleep 5

echo "[3/3] Restarting monerod..."
systemctl restart monerod 2>/dev/null || echo "  monerod not managed by systemd"
echo "  Waiting for monerod to initialize..."
sleep 15

echo "[4/4] Starting xmrig..."
systemctl start xmrig 2>/dev/null || echo "  xmrig not managed by systemd"
sleep 3

echo ""
echo "Service status:"
for svc in monerod p2pool xmrig; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    printf "  %-10s %s\n" "$svc" "$STATUS"
done

echo ""
echo "Done. Run ./health-check.sh for full verification."
