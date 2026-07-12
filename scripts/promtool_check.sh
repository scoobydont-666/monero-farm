#!/usr/bin/env bash
# promtool rules check + live target verification
# Usage: ./scripts/promtool_check.sh [check|targets]

set -euo pipefail

PROMTOOL="$(command -v promtool || echo /usr/bin/promtool)"
PROMETHEUS_CONFIG="/etc/prometheus/prometheus.yml"
PROMETHEUS_ALERTS="/etc/prometheus/monerod_p2pool_alerts.yml"

check_rules() {
    echo "=== promtool check rules ==="
    "$PROMTOOL" check rules "$PROMETHEUS_ALERTS" || {
        echo "ERROR: Rule validation failed"
        return 1
    }
    echo "Rules OK"
}

check_config() {
    echo "=== promtool check config ==="
    "$PROMTOOL" check config "$PROMETHEUS_CONFIG" || {
        echo "ERROR: Config validation failed"
        return 1
    }
    echo "Config OK"
}

check_targets() {
    echo "=== Live target verification ==="
    # Query Prometheus API for active targets
    local prom_url="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
    
    echo "Querying $prom_url/api/v1/targets ..."
    curl -sf "$prom_url/api/v1/targets" | jq -r '
        .data.activeTargets[] 
        | "\(.labels.job): \(.health) - \(.scrapeUrl) - lastError: \(.lastError // "none")"
    ' || {
        echo "WARNING: Could not query Prometheus targets"
        return 1
    }
}

case "${1:-all}" in
    rules) check_rules ;;
    config) check_config ;;
    targets) check_targets ;;
    all) check_rules && check_config && check_targets ;;
    *) echo "Usage: $0 [rules|config|targets|all]"; exit 1 ;;
esac