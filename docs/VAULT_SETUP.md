# Ansible Vault Setup Guide

## Overview

All secrets in this project are encrypted with **Ansible Vault** (AES-256). The vault password is **never stored in the repo** — it lives in your password manager.

## Quick Start

### 1. Get the Vault Password

Ask the repo owner (Josh) for the vault password. Store it in your password manager.

### 2. Set Environment Variable (per session)

```bash
export ANSIBLE_VAULT_PASSWORD_FILE=~/.vault-pass.txt
echo "your-vault-password-here" > ~/.vault-pass.txt
chmod 600 ~/.vault-pass.txt
```

### 3. Verify Access

```bash
cd /opt/monero-farm
ansible-vault view ansible/group_vars/all/vault.yml
```

You should see decrypted content (wallet address, P2Pool credentials, etc.)

## File Structure

```
ansible/
├── group_vars/
│   └── all/
│       ├── vault.yml          # ENCRYPTED - production secrets
│       └── vault.yml.example  # PLAINTEXT template
└── inventory/
    └── hosts.yml.example      # PLAINTEXT template
```

## Common Operations

### View Secrets
```bash
ansible-vault view ansible/group_vars/all/vault.yml
```

### Edit Secrets
```bash
ansible-vault edit ansible/group_vars/all/vault.yml
```

### Encrypt a New File
```bash
ansible-vault encrypt ansible/group_vars/all/new-secrets.yml
```

### Decrypt for Inspection (careful!)
```bash
ansible-vault decrypt ansible/group_vars/all/vault.yml
# RE-ENCRYPT IMMEDIATELY AFTER:
ansible-vault encrypt ansible/group_vars/all/vault.yml
```

### Rotate Vault Password
```bash
ansible-vault rekey ansible/group_vars/all/vault.yml
```

## Vault Contents (what's inside)

| Key | Description | Example |
|-----|-------------|---------|
| `monero_wallet_address` | Primary mining wallet (XMR) | `44AFFq5k...` |
| `p2pool_stratum_password` | P2Pool stratum auth | `strong-random-string` |
| `xmrig_http_password` | XMRig API basic auth | `another-random-string` |
| `ssh_known_hosts` | Host key fingerprints for verify | `sha256:...` |

## CI/CD Integration

GitHub Actions has the vault password as a **Repository Secret** named `ANSIBLE_VAULT_PASSWORD`.

Workflow decrypts automatically:
```yaml
- name: Decrypt vault
  run: echo "${{ secrets.ANSIBLE_VAULT_PASSWORD }}" > /tmp/vault-pass && chmod 600 /tmp/vault-pass
  env:
    ANSIBLE_VAULT_PASSWORD_FILE: /tmp/vault-pass
```

## Emergency Access

If you lose the vault password:
1. Recreate secrets from password manager / secure backup
2. Re-encrypt all vault files with new password
3. Update GitHub Actions secret
4. Notify all contributors

**There is no backdoor.** Ansible Vault uses PBKDF2 + AES-256. Lost password = lost secrets.
