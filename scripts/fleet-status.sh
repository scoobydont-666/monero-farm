#!/usr/bin/env bash
set -euo pipefail

# Monero Farm — Fleet Status
# SSH to all hosts and report combined health + hashrate
# Usage: ./fleet-status.sh [--json]

# Fleet inventory — edit to match your hosts
HOSTS=(
    "miniboss:192.168.200.213:fullnode"
    "rainbow:192.168.200.13:miner"
)

JSON=false
[[ "${1:-}" == "--json" ]] && JSON=true

check_host() {
    local name="$1" ip="$2" role="$3"
    local status="offline" uptime="" cpu="" mem="" services="" hashrate="0"

    if ssh -o ConnectTimeout=3 -o BatchMode=yes "josh@${ip}" "echo ok" &>/dev/null; then
        status="online"
        uptime=$(ssh "josh@${ip}" "uptime -p" 2>/dev/null || echo "?")
        cpu=$(ssh "josh@${ip}" "nproc" 2>/dev/null || echo "?")
        mem=$(ssh "josh@${ip}" "free -h | awk '/^Mem:/{print \$3\"/\"\$2}'" 2>/dev/null || echo "?")

        if [[ "$role" == "fullnode" ]]; then
            # Check monerod + P2Pool
            local monerod_ok p2pool_ok
            monerod_ok=$(ssh "josh@${ip}" "systemctl is-active monerod 2>/dev/null" || echo "inactive")
            p2pool_ok=$(ssh "josh@${ip}" "systemctl is-active p2pool-mini 2>/dev/null" || echo "inactive")
            services="monerod:${monerod_ok},p2pool:${p2pool_ok}"
        fi

        if [[ "$role" == "miner" || "$role" == "fullnode" ]]; then
            # Check XMRig hashrate
            local xmrig_data
            xmrig_data=$(ssh "josh@${ip}" "curl -s --max-time 2 http://127.0.0.1:8082/2/summary 2>/dev/null" || echo "")
            if [[ -n "$xmrig_data" ]]; then
                hashrate=$(echo "$xmrig_data" | jq -r '.hashrate.total[0] // 0' 2>/dev/null || echo "0")
                services="${services:+${services},}xmrig:active"
            else
                services="${services:+${services},}xmrig:inactive"
            fi
        fi
    fi

    if $JSON; then
        jq -n --arg name "$name" --arg ip "$ip" --arg role "$role" \
            --arg status "$status" --arg uptime "$uptime" --arg cpu "$cpu" \
            --arg mem "$mem" --arg services "$services" --argjson hashrate "$hashrate" \
            '{name:$name,ip:$ip,role:$role,status:$status,uptime:$uptime,cpu:$cpu,mem:$mem,services:$services,hashrate:$hashrate}'
    else
        printf "%-12s %-16s %-8s %-8s %-12s %-12s %s\n" \
            "$name" "$ip" "$role" "$status" "${hashrate} H/s" "$mem" "$services"
    fi
}

if ! $JSON; then
    echo "═══ Monero Farm — Fleet Status ═══"
    echo ""
    printf "%-12s %-16s %-8s %-8s %-12s %-12s %s\n" "HOST" "IP" "ROLE" "STATUS" "HASHRATE" "MEMORY" "SERVICES"
    printf "%-12s %-16s %-8s %-8s %-12s %-12s %s\n" "----" "--" "----" "------" "--------" "------" "--------"
fi

json_array="[]"
for entry in "${HOSTS[@]}"; do
    IFS=: read -r name ip role <<< "$entry"
    result=$(check_host "$name" "$ip" "$role")
    if $JSON; then
        json_array=$(echo "$json_array" | jq --argjson r "$result" '. + [$r]')
    else
        echo "$result"
    fi
done

if $JSON; then
    local_total=$(echo "$json_array" | jq '[.[].hashrate] | add')
    jq -n --argjson hosts "$json_array" --argjson total "$local_total" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{"timestamp":$ts,"total_hashrate":$total,"hosts":$hosts}'
else
    echo ""
    echo "Updated: $(date)"
fi
