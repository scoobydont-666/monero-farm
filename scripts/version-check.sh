#!/usr/bin/env bash
set -euo pipefail
#
# Check installed vs latest versions of monerod, P2Pool, XMRig.
# Also checks for FCMP++ hard fork announcements.
#
# Usage:
#   ./version-check.sh          # One-shot check
#   ./version-check.sh --json   # JSON output (for cron/monitoring)

JSON_MODE=false
[[ "${1:-}" == "--json" ]] && JSON_MODE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

check_version() {
  local name="$1" installed="$2" latest="$3"
  if [[ "$installed" == "$latest" ]]; then
    printf "  ${GREEN}%-10s  %-14s  %-14s  ✓ current${NC}\n" "$name" "$installed" "$latest"
  else
    printf "  ${YELLOW}%-10s  %-14s  %-14s  ⚠ update available${NC}\n" "$name" "$installed" "$latest"
  fi
}

# --- monerod ---
MONEROD_INSTALLED=$(monerod --version 2>/dev/null | grep -oP 'v\d+\.\d+\.\d+\.\d+' || echo "not installed")
MONEROD_LATEST=$(curl -sf https://api.github.com/repos/monero-project/monero/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo "unknown")

# --- P2Pool ---
P2POOL_BIN="/opt/p2pool/p2pool"
[[ -x "$P2POOL_BIN" ]] || P2POOL_BIN="/opt/p2pool/build/p2pool"
P2POOL_INSTALLED=$($P2POOL_BIN --version 2>/dev/null | grep -oP 'v\d+\.\d+' || echo "not installed")
P2POOL_LATEST=$(curl -sf https://api.github.com/repos/SChernykh/p2pool/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo "unknown")

# --- XMRig ---
XMRIG_INSTALLED=$(xmrig --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1 || echo "not installed")
XMRIG_LATEST=$(curl -sf https://api.github.com/repos/xmrig/xmrig/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))" 2>/dev/null || echo "unknown")

# --- FCMP++ hard fork check ---
FCMP_STATUS=$(curl -sf https://api.github.com/repos/monero-project/monero/milestones 2>/dev/null | python3 -c "
import sys, json
milestones = json.load(sys.stdin)
for m in milestones:
    title = m.get('title', '').lower()
    if 'fcmp' in title or 'hard fork' in title or 'hardfork' in title:
        due = m.get('due_on', 'no date')
        state = m.get('state', 'unknown')
        print(f\"{m['title']} | state={state} | due={due}\")
        break
else:
    print('no FCMP++ milestone found')
" 2>/dev/null || echo "could not check")

if $JSON_MODE; then
  cat << JSONEOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "monerod": {"installed": "$MONEROD_INSTALLED", "latest": "$MONEROD_LATEST"},
  "p2pool": {"installed": "$P2POOL_INSTALLED", "latest": "$P2POOL_LATEST"},
  "xmrig": {"installed": "${XMRIG_INSTALLED:-not installed}", "latest": "$XMRIG_LATEST"},
  "fcmp_status": "$FCMP_STATUS"
}
JSONEOF
else
  echo ""
  echo "  Monero Farm — Version Check ($(date +%Y-%m-%d))"
  echo "  ─────────────────────────────────────────────"
  printf "  %-10s  %-14s  %-14s  %s\n" "Component" "Installed" "Latest" "Status"
  printf "  %-10s  %-14s  %-14s  %s\n" "─────────" "─────────" "──────" "──────"

  check_version "monerod" "$MONEROD_INSTALLED" "$MONEROD_LATEST"
  check_version "P2Pool" "$P2POOL_INSTALLED" "$P2POOL_LATEST"
  check_version "XMRig" "${XMRIG_INSTALLED:-not installed}" "v$XMRIG_LATEST"

  echo ""
  echo "  FCMP++ Hard Fork: $FCMP_STATUS"
  echo ""
fi
