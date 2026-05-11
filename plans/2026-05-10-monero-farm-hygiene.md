# Monero Farm Hygiene — 2026-05-10

**Status**: Active (Josh-approved via 6-item directive)
**Owner**: Josh
**Operator**: Claude on MECHA

## Scope

Five-item hygiene pass on `/opt/monero-farm`, derived from the 5-persona audit on 2026-05-10. SSH blast-radius work is deferred to `plans/ssh-blast-radius-remediation.md`.

## Approved items

1. **Sanitize repo** — backup tarball excludes `.mcp.json`, `.env`, `.env.*`, `*.key`, `*.pem`, SSH key files. No history rewrite needed (history already clean).
2. **XMRig mining gate** — keep the role and templates intact; gate the `site.yml` play behind `mining_enabled: false` default with an `assert` pre-check. Unlock pattern: `-e mining_enabled=true`. Decision filed 2026-04-06.
3. **Port reality canonical** — reconcile `config/monerod.conf` and `config/p2pool-flags.conf` to match observed live values on miniboss (ZMQ 18083 not 18082; no `restricted-rpc=1`; document per-instance P2Pool flags).
4. **(deferred)** SSH blast-radius — see `plans/ssh-blast-radius-remediation.md`.
5. **restricted-rpc reconcile** — folded into item 3. Live deliberately omits `restricted-rpc=1` because exporters require admin RPC methods (template already comments this). Reference file is the drift; updated to match.
6. **Inventory + wallet** — create `ansible/inventory/hosts.yml` (gitignored) with live values; replace `TODO_YOUR_PRIMARY_ADDRESS` sentinel in `ansible/roles/p2pool/defaults/main.yml` with empty string + add pre-flight assert in `ansible/roles/p2pool/tasks/main.yml`.

## Files touched

- `scripts/backup.sh` — add tar excludes for secrets
- `ansible/site.yml` — gate XMRig play behind `mining_enabled`
- `config/monerod.conf` — port reality + remove drift
- `config/p2pool-flags.conf` — port reality + per-instance documentation
- `ansible/inventory/hosts.yml` — create (gitignored)
- `ansible/roles/p2pool/defaults/main.yml` — replace TODO sentinel with empty default
- `ansible/roles/p2pool/tasks/main.yml` — add pre-flight wallet assert

## Verification

- `ansible-playbook -i inventory/hosts.yml site.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml site.yml --check --diff` against miniboss — expect zero changes on port/config files since live already matches the new canonical values
- `bash -n scripts/backup.sh` for syntax
- `git diff --stat` review
- Confirm `git status` shows `ansible/inventory/hosts.yml` as ignored (not staged)
- Confirm `grep -r 'TODO_YOUR_PRIMARY_ADDRESS' ansible/` returns no hits
- Confirm `grep -r '49cuJEMVhN' /opt/monero-farm/ --include='*.yml' --include='*.j2' --include='*.conf' --include='*.sh' --include='*.md'` returns hits ONLY in `ansible/inventory/hosts.yml` (the gitignored file)

## Rollback

Per-file `git checkout <path>` reverts; no service-level changes in this plan (config files are reference/documentation; live monerod and P2Pool stay running unchanged).

## Out of scope

- SSH blast-radius (separate plan)
- Ansible CI/CD wiring (DevOps audit recommendation; separate work)
- Drift detection automation (separate work)
- Backup off-host destination (separate work)
- New exporter alerts (separate work)
