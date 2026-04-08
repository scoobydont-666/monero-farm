#!/usr/bin/env bash
set -euo pipefail

# Basic validation tests for monero-farm bash scripts
# Requires: shellcheck, bash

SCRIPTS_DIR="$(cd "$(dirname "$0")/../scripts" && pwd)"
PASS=0
FAIL=0
TOTAL=0

pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); echo "  FAIL: $1"; }

echo "=== monero-farm script tests ==="
echo ""

# ── Shellcheck ────────────────────────────────────────────────────
echo "--- Shellcheck validation ---"

for script in "$SCRIPTS_DIR"/*.sh; do
    name="$(basename "$script")"
    if shellcheck -S warning "$script" 2>/dev/null; then
        pass "shellcheck $name"
    else
        # Allow SC2034 (unused var) as it's cosmetic
        errors=$(shellcheck -S warning "$script" 2>&1 | grep -v SC2034 | grep -c "SC[0-9]" || true)
        if [ "$errors" -eq 0 ]; then
            pass "shellcheck $name (SC2034 warning only)"
        else
            fail "shellcheck $name"
        fi
    fi
done

# ── Shebang check ────────────────────────────────────────────────
echo ""
echo "--- Shebang validation ---"

for script in "$SCRIPTS_DIR"/*.sh; do
    name="$(basename "$script")"
    first_line=$(head -1 "$script")
    if [[ "$first_line" == "#!/usr/bin/env bash" ]] || [[ "$first_line" == "#!/bin/bash" ]]; then
        pass "shebang $name"
    else
        fail "shebang $name (got: $first_line)"
    fi
done

# ── set -euo pipefail check ──────────────────────────────────────
echo ""
echo "--- Safety flags (set -euo pipefail) ---"

for script in "$SCRIPTS_DIR"/*.sh; do
    name="$(basename "$script")"
    # Skip migrate scripts which may have different requirements
    if [[ "$script" == *"/migrate/"* ]]; then
        continue
    fi
    if grep -q "set -euo pipefail" "$script"; then
        pass "safety flags $name"
    else
        fail "safety flags $name (missing set -euo pipefail)"
    fi
done

# ── Syntax check ─────────────────────────────────────────────────
echo ""
echo "--- Bash syntax validation ---"

for script in "$SCRIPTS_DIR"/*.sh; do
    name="$(basename "$script")"
    if bash -n "$script" 2>/dev/null; then
        pass "syntax $name"
    else
        fail "syntax $name"
    fi
done

# ── No hardcoded wallet addresses ─────────────────────────────────
echo ""
echo "--- Security: no hardcoded wallet addresses ---"

for script in "$SCRIPTS_DIR"/*.sh; do
    name="$(basename "$script")"
    # Monero addresses start with 4 and are 95 chars
    if grep -qP '4[0-9A-Za-z]{94}' "$script" 2>/dev/null; then
        fail "hardcoded wallet address in $name"
    else
        pass "no wallet address $name"
    fi
done

# ── No hardcoded IPs (should use hostnames) ───────────────────────
echo ""
echo "--- Convention: prefer hostnames over IPs ---"

for script in "$SCRIPTS_DIR"/*.sh; do
    name="$(basename "$script")"
    # Skip migrate scripts which deal with raw network config
    if [[ "$script" == *"/migrate/"* ]]; then
        continue
    fi
    # Check for hardcoded 192.168.x.x IPs (should use hostname vars)
    if grep -qP '192\.168\.\d+\.\d+' "$script" 2>/dev/null; then
        fail "hardcoded IP in $name (should use hostname variable)"
    else
        pass "no hardcoded IP $name"
    fi
done

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed, $TOTAL total ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
