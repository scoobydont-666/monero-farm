#!/usr/bin/env bash
set -euo pipefail

# Monero Farm — Health Check
# Checks monerod, p2pool, xmrig status

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; ERRORS=$((ERRORS + 1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $*"; }

ERRORS=0

echo "═══════════════════════════════════════════════════"
echo "  Monero Farm — Health Check"
echo "  $(date)"
echo "═══════════════════════════════════════════════════"
echo ""

# --- monerod ---
echo "monerod:"
if systemctl is-active --quiet monerod 2>/dev/null; then
    pass "systemd: active"
else
    fail "systemd: not running"
fi

MONEROD_RESPONSE=$(curl -s --max-time 5 -w '\n%{http_code}' http://127.0.0.1:18081/json_rpc \
    -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' 2>/dev/null)
MONEROD_HTTP_CODE=$(echo "$MONEROD_RESPONSE" | tail -1)
MONEROD_INFO=$(echo "$MONEROD_RESPONSE" | sed '$d')
if [[ "$MONEROD_HTTP_CODE" == "200" && -n "$MONEROD_INFO" ]]; then
    SYNCED=$(echo "$MONEROD_INFO" | jq -r '.result.synchronized // false' 2>/dev/null || echo "false")
    HEIGHT=$(echo "$MONEROD_INFO" | jq -r '.result.height // "?"' 2>/dev/null || echo "?")
    TARGET=$(echo "$MONEROD_INFO" | jq -r '.result.target_height // "?"' 2>/dev/null || echo "?")
    CONNECTIONS=$(echo "$MONEROD_INFO" | jq -r '.result.outgoing_connections_count // 0' 2>/dev/null || echo "0")
    if [[ "$SYNCED" == "true" ]]; then
        pass "sync: complete (height: ${HEIGHT})"
    else
        warn "sync: in progress (${HEIGHT} / ${TARGET})"
    fi
    pass "connections: ${CONNECTIONS} outbound"
else
    fail "RPC: not responding on 127.0.0.1:18081"
fi

echo ""

# --- P2Pool ---
echo "p2pool:"
if systemctl is-active --quiet p2pool 2>/dev/null; then
    pass "systemd: active"
elif pgrep -x p2pool >/dev/null 2>&1; then
    warn "running (not via systemd)"
else
    fail "not running"
fi

if ss -tlnp | grep -q ':3333 ' 2>/dev/null; then
    pass "stratum: listening on :3333"
else
    fail "stratum: not listening on :3333"
fi

echo ""

# --- XMRig ---
echo "xmrig:"
if systemctl is-active --quiet xmrig 2>/dev/null; then
    pass "systemd: active"
elif pgrep -x xmrig >/dev/null 2>&1; then
    warn "running (not via systemd)"
else
    warn "not running (may be managed externally)"
fi

XMRIG_SUMMARY=$(curl -s --max-time 5 http://127.0.0.1:8082/2/summary 2>/dev/null || echo "")
if [[ -n "$XMRIG_SUMMARY" ]]; then
    HASHRATE=$(echo "$XMRIG_SUMMARY" | jq -r '.hashrate.total[0] // 0' 2>/dev/null || echo "0")
    ACCEPTED=$(echo "$XMRIG_SUMMARY" | jq -r '.results.shares_good // 0' 2>/dev/null || echo "0")
    pass "hashrate: ${HASHRATE} H/s"
    pass "accepted shares: ${ACCEPTED}"
else
    warn "HTTP API: not responding on 127.0.0.1:8082"
fi

echo ""

# --- Hugepages ---
echo "system:"
HP_TOTAL=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo "0")
if [[ "$HP_TOTAL" -ge 1280 ]]; then
    pass "hugepages: ${HP_TOTAL} (>= 1280 needed for RandomX)"
else
    fail "hugepages: ${HP_TOTAL} (need >= 1280)"
fi

# Disk space for blockchain
MONERO_DISK=$(df -BG /var/lib/monero 2>/dev/null | awk 'NR==2{print $4}' || echo "?")
pass "disk free (/var/lib/monero): ${MONERO_DISK}"

echo ""
echo "═══════════════════════════════════════════════════"
if [[ $ERRORS -eq 0 ]]; then
    echo -e "  ${GREEN}All checks passed${NC}"
else
    echo -e "  ${RED}${ERRORS} check(s) failed${NC}"
fi
echo "═══════════════════════════════════════════════════"
exit $ERRORS
