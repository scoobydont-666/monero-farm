#!/usr/bin/env bash
set -euo pipefail

# Monero Farm — Backup
# Backs up configs, wallet data, and P2Pool state
# Does NOT back up the blockchain (re-sync is cheaper than storing ~200GB)

DEST="${1:-/opt/monero-farm/backups}"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$DEST/$DATE"

echo "Monero Farm Backup — $DATE"
mkdir -p "$BACKUP_DIR"

# Monero Farm project files (configs, scripts)
echo "Backing up project files..."
tar czf "$BACKUP_DIR/monero-farm-project.tar.gz" \
    --exclude='.git' \
    --exclude='backups' \
    -C /opt monero-farm/

# P2Pool state (small — sidechain data)
if [[ -d /var/lib/p2pool ]]; then
    echo "Backing up P2Pool state..."
    tar czf "$BACKUP_DIR/p2pool-state.tar.gz" -C /var/lib p2pool/
fi

# Wallet files (if any exist) — encrypted with GPG
if compgen -G "/home/*/Monero/wallets/*" >/dev/null 2>&1; then
    PASSPHRASE_FILE="/root/.wallet-backup-passphrase"
    if [[ -f "$PASSPHRASE_FILE" ]]; then
        echo "Backing up wallet files (encrypted)..."
        WALLET_ARCHIVE="$BACKUP_DIR/wallet-keys.tar.gz.gpg"
        find /home -path "*/Monero/wallets/*" -name "*.keys" -print0 | \
            tar czf - --null -T - | \
            gpg --batch --symmetric --cipher-algo AES256 \
                --passphrase-file "$PASSPHRASE_FILE" \
                -o "$WALLET_ARCHIVE"
        echo "  Encrypted wallet keys: $WALLET_ARCHIVE"
        echo "  Restore: gpg --batch --decrypt --passphrase-file $PASSPHRASE_FILE $WALLET_ARCHIVE | tar xzf -"
    else
        echo "WARNING: $PASSPHRASE_FILE not found — skipping wallet backup"
        echo "  Create it: openssl rand -hex 32 | sudo tee $PASSPHRASE_FILE && sudo chmod 0400 $PASSPHRASE_FILE"
    fi
fi

# Systemd unit snapshots
echo "Backing up systemd units..."
mkdir -p "$BACKUP_DIR/systemd"
for svc in monerod p2pool xmrig; do
    [[ -f "/etc/systemd/system/${svc}.service" ]] && \
        cp "/etc/systemd/system/${svc}.service" "$BACKUP_DIR/systemd/"
done

echo ""
echo "Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR/"
echo "Total: $(du -sh "$BACKUP_DIR" | cut -f1)"
