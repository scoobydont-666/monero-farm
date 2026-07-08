# Contributing to Monero Farm

Thank you for your interest in contributing! This project manages Monero mining infrastructure as code.

## Code of Conduct

By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md) (to be created).

## How to Contribute

### 1. Fork & Clone

```bash
git clone https://github.com/YOUR_FORK/monero-farm.git
cd monero-farm
```

### 2. Create a Branch

```bash
git checkout -b feat/your-feature-name
# or
git checkout -b fix/your-bug-description
```

### 3. Make Changes

Follow the project conventions:

- **Ansible**: Roles in `ansible/roles/`, inventory in `ansible/inventory/`
- **Scripts**: Shell scripts in `scripts/`, use `set -euo pipefail`
- **Configs**: Reference configs in `config/`, Ansible templates are authoritative
- **Docs**: Markdown in `docs/`, update CLAUDE.md for architectural changes

### 4. Test Locally

```bash
# Ansible syntax check
ansible-playbook --syntax-check ansible/site.yml

# Dry run (no changes)
ansible-playbook -i ansible/inventory/hosts.yml.example ansible/site.yml --check --diff

# Shellcheck
shellcheck scripts/*.sh

# Lint
yamllint ansible/
```

### 5. Commit

Use conventional commits:

```
feat: add new P2Pool sidechain support
fix: correct monerod ZMQ port binding
docs: update port registry in CLAUDE.md
chore: update monerod version to 0.18.5.0
```

### 6. Push & PR

```bash
git push origin feat/your-feature-name
# Open PR against main branch
```

## Pull Request Requirements

All PRs must pass:

- [ ] CI green (ansible-lint, yamllint, shellcheck, gitleaks)
- [ ] No secrets detected (gitleaks)
- [ ] Conventional commit messages
- [ ] Updated documentation (CLAUDE.md, README.md, architecture.md)
- [ ] No breaking changes without version bump

## Development Environment

### Required Tools

| Tool | Version | Install |
|------|---------|---------|
| Ansible | ≥ 2.15 | `pipx install ansible` |
| Python | ≥ 3.11 | System package manager |
| shellcheck | ≥ 0.9 | `apt install shellcheck` / `brew install shellcheck` |
| yamllint | ≥ 1.35 | `pipx install yamllint` |
| gitleaks | ≥ 8.18 | `brew install gitleaks` |
| uv | ≥ 0.4 | `pipx install uv` |

### Fleet Access

You need SSH access to fleet hosts for live testing:
- **miniboss**: P2Pool relay + monerod full node
- **giga/mecha/mega/mongo**: GPU hosts (XMRig disabled in MAINTENANCE MODE)

## Ansible Role Development

### Role Structure

```
ansible/roles/<role>/
├── tasks/
│   └── main.yml
├── templates/
│   └── *.j2
├── defaults/
│   └── main.yml
├── vars/
│   └── main.yml
├── handlers/
│   └── main.yml
├── meta/
│   └── main.yml
└── README.md
```

### Testing Roles

```bash
# Molecule testing (if configured)
cd ansible/roles/<role>
molecule test

# Or integration test against staging
ansible-playbook -i ansible/inventory/staging.yml site.yml --tags <role>
```

## Security Considerations

- **Never** commit secrets (wallet addresses, API keys, SSH keys)
- All secrets via `ansible-vault` — see `ansible/group_vars/all/vault.yml.example`
- Report security issues privately (see SECURITY.md)

## Documentation Standards

- Update CLAUDE.md for any architectural change
- Port changes → update CLAUDE.md Service Port Map
- New role → add to CLAUDE.md Ansible Roles table
- New exporter → add to CLAUDE.md Monitoring Stack

## Issue Templates

Use the appropriate template:
- `bug_report.md` — Something broken
- `feature_request.md` — New capability
- `security.md` — Vulnerability (private)

## Questions?

- Check existing issues first
- Check CLAUDE.md for architecture
- Open a Discussion for design questions
