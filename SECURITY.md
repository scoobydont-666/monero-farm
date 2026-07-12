# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Reporting a Vulnerability

**Do not file public issues for security vulnerabilities.**

Email security findings to: **security@scoobydont-666.example** (or DM the repo owner)

You will receive an acknowledgment within 48 hours. If the issue is confirmed, we will:
1. Privately coordinate a fix
2. Release a patch
3. Publicly disclose with CVE assignment (if applicable)

## Threat Model

This project manages Monero (XMR) mining infrastructure. Key assets:

| Asset | Risk | Mitigation |
|-------|------|------------|
| Monero wallet addresses | Theft of mining rewards | Vault-stored, never in repo |
| P2Pool stratum credentials | Hashrate hijacking | Vault + mTLS on stratum |
| SSH access to fleet hosts | Full compromise | Key-only auth, UFW deny-by-default |
| Ansible Vault secrets | Credential leakage | AES-256, vault passwords not committed |

## Hardening Baseline (enforced by Ansible)

- **Base role**: UFW deny-by-default + allowlist, fail2ban, auditd, no-root-SSH
- **monerod role**: Runs as `monero` user (uid 998), read-only config, data dir 0700
- **p2pool role**: Runs as `p2pool` user (uid 997), dedicated systemd units per sidechain
- **xmrig role**: Runs as `xmrig` user (uid 996), API bound to localhost + Tailscale only
- **Exporter role**: Runs as `monero-exporter` user (uid 995), Prometheus metrics only

## Secret Handling

- All secrets in `ansible-vault` (see `ansible/group_vars/all/vault.yml`)
- `ansible-vault view` requires vault password from password manager
- **Never** commit unencrypted secrets
- CI runs `gitleaks` on every PR

## Dependency Security

- Container images: `docker.io/library/...` pinned by digest where possible
- Python deps: `uv.lock` + `pip-audit` in CI
- Ansible roles: pinned galaxy versions in `requirements.yml`

## Disclosure Timeline

| Severity | Target Fix | Disclosure |
|----------|------------|------------|
| Critical | 7 days     | 30 days    |
| High     | 14 days    | 45 days    |
| Medium   | 30 days    | 90 days    |
| Low      | 90 days    | 180 days   |

## Contact

- Primary: Josh (repo owner) — DM via GitHub or email above
- Secondary: Open an issue with `security` label (will be made private)
