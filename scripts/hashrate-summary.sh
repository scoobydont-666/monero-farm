#!/usr/bin/env bash
set -euo pipefail

# Monero Farm — Hashrate Summary
# Polls XMRig HTTP API on all known miners
# Usage: ./hashrate-summary.sh [--watch]

MINERS=("127.0.0.1:8082")
# Add remote miners here:
# MINERS+=("192.168.x.x:8082" "192.168.x.x:8082")

WATCH=false
JSON=false
[[ "${1:-}" == "--watch" ]] && WATCH=true
[[ "${1:-}" == "--json" ]] && JSON=true

print_summary() {
    local total_hr=0
    local total_shares=0

    printf "%-20s %12s %10s %10s\n" "HOST" "HASHRATE" "ACCEPTED" "UPTIME"
    printf "%-20s %12s %10s %10s\n" "----" "--------" "--------" "------"

    for host in "${MINERS[@]}"; do
        local data
        data=$(curl -s --max-time 3 "http://${host}/2/summary" 2>/dev/null || echo "")
        if [[ -n "$data" ]]; then
            local hr shares uptime
            hr=$(echo "$data" | jq -r '.hashrate.total[0] // 0' 2>/dev/null)
            shares=$(echo "$data" | jq -r '.results.shares_good // 0' 2>/dev/null)
            uptime=$(echo "$data" | jq -r '.uptime // 0' 2>/dev/null)
            local uptime_h=$((uptime / 3600))
            printf "%-20s %10.1f H/s %10s %8sh\n" "$host" "$hr" "$shares" "$uptime_h"
            total_hr=$(echo "$total_hr + $hr" | bc)
            total_shares=$((total_shares + shares))
        else
            printf "%-20s %12s %10s %10s\n" "$host" "OFFLINE" "-" "-"
        fi
    done

    printf "%-20s %12s %10s\n" "----" "--------" "--------"
    printf "%-20s %10.1f H/s %10s\n" "TOTAL" "$total_hr" "$total_shares"
    echo ""
    echo "Updated: $(date)"
}

print_json() {
    local miners_json="[]"
    for host in "${MINERS[@]}"; do
        local data
        data=$(curl -s --max-time 3 "http://${host}/2/summary" 2>/dev/null || echo "")
        if [[ -n "$data" ]]; then
            local hr shares uptime
            hr=$(echo "$data" | jq -r '.hashrate.total[0] // 0' 2>/dev/null)
            shares=$(echo "$data" | jq -r '.results.shares_good // 0' 2>/dev/null)
            uptime=$(echo "$data" | jq -r '.uptime // 0' 2>/dev/null)
            miners_json=$(echo "$miners_json" | jq --arg h "$host" --argjson hr "$hr" --argjson s "$shares" --argjson u "$uptime" '. + [{"host":$h,"hashrate":$hr,"shares":$s,"uptime":$u,"status":"online"}]')
        else
            miners_json=$(echo "$miners_json" | jq --arg h "$host" '. + [{"host":$h,"hashrate":0,"shares":0,"uptime":0,"status":"offline"}]')
        fi
    done
    local total_hr
    total_hr=$(echo "$miners_json" | jq '[.[].hashrate] | add')
    jq -n --argjson miners "$miners_json" --argjson total "$total_hr" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{"timestamp":$ts,"total_hashrate":$total,"miners":$miners}'
}

if $JSON; then
    print_json
elif $WATCH; then
    while true; do
        clear
        echo "═══ Monero Farm — Live Hashrate ═══"
        echo ""
        print_summary
        sleep 10
    done
else
    print_summary
fi
