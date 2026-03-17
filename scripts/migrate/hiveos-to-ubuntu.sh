#!/usr/bin/env bash
set -euo pipefail
#
# HiveOS → Ubuntu 24.04 In-Place Migration (debootstrap method)
# Runs FROM miniboss, orchestrates the target over SSH.
#
# Method:
#   1. debootstrap Ubuntu 24.04 (noble) into RAM (tmpfs) on the target
#   2. Configure the tmpfs rootfs with networking + SSH
#   3. pivot_root into the tmpfs system
#   4. Wipe and partition the SSD
#   5. debootstrap again onto the SSD
#   6. Full configuration (kernel, grub, SSH, XMRig, hugepages, UFW)
#   7. Reboot into Ubuntu 24.04
#
# WARNING: This DESTROYS all data on the target. Non-reversible.

TARGET_IP="${1:?Usage: $0 <target-ip> [ssh-user]}"
SSH_USER="${2:-root}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MINIBOSS_IP="192.168.200.213"
MINIBOSS_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ4Svr/7k1zZJfzyunjidvtA3tVozh7Pt2MZchDP+e1X josh@miniboss"
XMRIG_VERSION="6.25.0"
P2POOL_HOST="192.168.200.213"
P2POOL_PORT="3333"

echo "============================================="
echo "  HiveOS → Ubuntu 24.04 In-Place Migration"
echo "  (debootstrap method)"
echo "============================================="
echo "  Target:    ${SSH_USER}@${TARGET_IP}"
echo ""
echo "  WARNING: This will DESTROY all data on ${TARGET_IP}."
echo ""
read -p "  Type 'WIPE' to continue: " CONFIRM
if [[ "$CONFIRM" != "WIPE" ]]; then
  echo "Aborted."
  exit 1
fi

# --- Step 0: Verify SSH and gather info ---
echo ""
echo ">>> Step 0: Verifying target..."
TARGET_HOSTNAME=$(ssh -o ConnectTimeout=5 "${SSH_USER}@${TARGET_IP}" "hostname")
echo "    Connected to ${TARGET_HOSTNAME} (${TARGET_IP})"

TARGET_DISK=$(ssh "${SSH_USER}@${TARGET_IP}" "lsblk -d -n -o NAME,TYPE | grep disk | head -1 | awk '{print \$1}'")
echo "    Target disk: /dev/${TARGET_DISK}"

TARGET_RAM=$(ssh "${SSH_USER}@${TARGET_IP}" "free -g | awk '/Mem/{print \$2}'")
echo "    Target RAM: ${TARGET_RAM}GB"

if [[ "${TARGET_RAM}" -lt 4 ]]; then
  echo "ERROR: Need at least 4GB RAM for tmpfs debootstrap. Have ${TARGET_RAM}GB."
  exit 1
fi

# Detect network interface name
TARGET_IFACE=$(ssh "${SSH_USER}@${TARGET_IP}" "ip route show default | awk '{print \$5}' | head -1")
echo "    Network interface: ${TARGET_IFACE}"

# Check EFI
TARGET_EFI=$(ssh "${SSH_USER}@${TARGET_IP}" "[ -d /sys/firmware/efi ] && echo yes || echo no")
echo "    EFI boot: ${TARGET_EFI}"

echo ""
echo "    This will:"
echo "      - Wipe /dev/${TARGET_DISK}"
echo "      - Install Ubuntu 24.04 LTS"
echo "      - Configure XMRig ${XMRIG_VERSION} → ${P2POOL_HOST}:${P2POOL_PORT}"
echo "      - Set up SSH key auth for josh"
echo ""
read -p "    Press Enter to begin, or Ctrl+C to abort..."

# --- Step 1: debootstrap into tmpfs ---
echo ""
echo ">>> Step 1: Building Ubuntu rootfs in RAM..."
ssh "${SSH_USER}@${TARGET_IP}" "
  set -e
  # Create tmpfs for the new rootfs (use 4GB)
  mkdir -p /tmp/newroot
  mount -t tmpfs -o size=4G tmpfs /tmp/newroot

  # debootstrap noble (24.04)
  echo '    Running debootstrap noble...'
  debootstrap --variant=minbase noble /tmp/newroot http://archive.ubuntu.com/ubuntu

  echo '    debootstrap complete.'
  ls /tmp/newroot/bin/bash && echo '    rootfs OK'
" 2>&1 | grep -E "^    |Retrieving|Extracting|I:|W:" | tail -20

echo "    Ubuntu rootfs built in tmpfs."

# --- Step 2: Configure tmpfs rootfs for network + SSH ---
echo ""
echo ">>> Step 2: Configuring tmpfs rootfs..."
ssh "${SSH_USER}@${TARGET_IP}" "
  set -e

  # Mount essential filesystems
  mount --bind /dev /tmp/newroot/dev
  mount --bind /dev/pts /tmp/newroot/dev/pts
  mount -t proc proc /tmp/newroot/proc
  mount -t sysfs sysfs /tmp/newroot/sys
  mount --bind /sys/firmware/efi/efivars /tmp/newroot/sys/firmware/efi/efivars 2>/dev/null || true

  # DNS
  cp /etc/resolv.conf /tmp/newroot/etc/resolv.conf

  # Configure apt sources
  cat > /tmp/newroot/etc/apt/sources.list << 'APT_EOF'
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-security main restricted universe multiverse
APT_EOF

  # Install essential packages in chroot
  chroot /tmp/newroot /bin/bash -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends \
      linux-generic grub-efi-amd64 efibootmgr \
      openssh-server parted dosfstools e2fsprogs \
      sudo curl wget jq htop ufw \
      systemd systemd-sysv dbus \
      iproute2 iputils-ping netplan.io \
      ca-certificates
  '
  echo '    Packages installed in chroot.'
"

echo "    tmpfs rootfs configured."

# --- Step 3: Partition and format the SSD ---
echo ""
echo ">>> Step 3: Partitioning /dev/${TARGET_DISK}..."
ssh "${SSH_USER}@${TARGET_IP}" "
  set -e
  DISK=/dev/${TARGET_DISK}

  # Stop XMRig to free resources
  killall xmrig 2>/dev/null || true
  sleep 2

  # Unmount existing partitions (except tmpfs)
  umount \${DISK}3 2>/dev/null || true  # EFI
  umount \${DISK}1 2>/dev/null || true
  swapoff -a 2>/dev/null || true

  # Wipe and create fresh GPT
  wipefs -a \${DISK}
  parted -s \${DISK} mklabel gpt

  # EFI System Partition (512MB)
  parted -s \${DISK} mkpart esp fat32 1MiB 513MiB
  parted -s \${DISK} set 1 esp on

  # Root partition (rest)
  parted -s \${DISK} mkpart root ext4 513MiB 100%

  # Format
  mkfs.vfat -F32 \${DISK}1
  mkfs.ext4 -F \${DISK}2

  echo '    Partitions created:'
  lsblk \${DISK}
"

echo "    SSD partitioned."

# --- Step 4: Install Ubuntu onto SSD ---
echo ""
echo ">>> Step 4: Installing Ubuntu onto SSD..."
ssh "${SSH_USER}@${TARGET_IP}" "
  set -e
  DISK=/dev/${TARGET_DISK}

  # Mount target
  mkdir -p /mnt/target
  mount \${DISK}2 /mnt/target
  mkdir -p /mnt/target/boot/efi
  mount \${DISK}1 /mnt/target/boot/efi

  # debootstrap onto disk
  echo '    Running debootstrap onto SSD...'
  debootstrap noble /mnt/target http://archive.ubuntu.com/ubuntu

  # Mount virtual filesystems
  mount --bind /dev /mnt/target/dev
  mount --bind /dev/pts /mnt/target/dev/pts
  mount -t proc proc /mnt/target/proc
  mount -t sysfs sysfs /mnt/target/sys
  mount --bind /sys/firmware/efi/efivars /mnt/target/sys/firmware/efi/efivars 2>/dev/null || true

  # Copy DNS
  cp /etc/resolv.conf /mnt/target/etc/resolv.conf

  echo '    Base system installed.'
"

echo "    Ubuntu base on SSD."

# --- Step 5: Full configuration in chroot ---
echo ""
echo ">>> Step 5: Configuring Ubuntu on SSD..."
ssh "${SSH_USER}@${TARGET_IP}" "
  set -e
  DISK=/dev/${TARGET_DISK}

  # Write apt sources
  cat > /mnt/target/etc/apt/sources.list << 'APT_EOF'
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-security main restricted universe multiverse
APT_EOF

  # Write fstab
  ROOT_UUID=\$(blkid -s UUID -o value \${DISK}2)
  EFI_UUID=\$(blkid -s UUID -o value \${DISK}1)
  cat > /mnt/target/etc/fstab << FSTAB_EOF
UUID=\${ROOT_UUID}  /          ext4  errors=remount-ro  0  1
UUID=\${EFI_UUID}   /boot/efi  vfat  umask=0077         0  1
FSTAB_EOF

  # Hostname
  echo 'rainbow' > /mnt/target/etc/hostname
  echo '127.0.1.1 rainbow' >> /mnt/target/etc/hosts

  # Netplan (DHCP on first ethernet)
  mkdir -p /mnt/target/etc/netplan
  cat > /mnt/target/etc/netplan/01-netcfg.yaml << 'NET_EOF'
network:
  version: 2
  renderer: networkd
  ethernets:
    id0:
      match:
        name: \"e*\"
      dhcp4: true
NET_EOF

  # Chroot and install packages + configure
  chroot /mnt/target /bin/bash << 'CHROOT_EOF'
    set -e
    export DEBIAN_FRONTEND=noninteractive

    apt-get update -qq
    apt-get install -y --no-install-recommends \
      linux-generic grub-efi-amd64 efibootmgr \
      openssh-server sudo curl wget jq htop ufw \
      systemd systemd-sysv dbus \
      iproute2 iputils-ping netplan.io \
      ca-certificates

    # Create josh user
    useradd -m -s /bin/bash -G sudo josh
    echo 'josh ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/josh
    chmod 440 /etc/sudoers.d/josh

    # SSH key
    mkdir -p /home/josh/.ssh
    echo '${MINIBOSS_PUBKEY}' > /home/josh/.ssh/authorized_keys
    chmod 700 /home/josh/.ssh
    chmod 600 /home/josh/.ssh/authorized_keys
    chown -R josh:josh /home/josh/.ssh

    # Also allow root SSH for emergencies
    mkdir -p /root/.ssh
    echo '${MINIBOSS_PUBKEY}' > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/authorized_keys

    # SSH hardening — key auth only
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    systemctl enable ssh

    # Hugepages for RandomX (Ryzen 5 9600X)
    echo 'vm.nr_hugepages=1280' > /etc/sysctl.d/99-hugepages.conf

    # Download XMRig
    mkdir -p /opt/xmrig
    wget -q -O /tmp/xmrig.tar.gz \
      "https://github.com/xmrig/xmrig/releases/download/v${XMRIG_VERSION}/xmrig-${XMRIG_VERSION}-linux-static-x64.tar.gz"
    tar -xzf /tmp/xmrig.tar.gz -C /tmp/
    cp /tmp/xmrig-${XMRIG_VERSION}/xmrig /opt/xmrig/xmrig
    chmod 755 /opt/xmrig/xmrig
    ln -sf /opt/xmrig/xmrig /usr/local/bin/xmrig
    rm -rf /tmp/xmrig*

    # XMRig config
    mkdir -p /etc/xmrig
    cat > /etc/xmrig/config.json << 'XMRIG_CFG'
{
    "autosave": true,
    "cpu": {
        "enabled": true,
        "huge-pages": true,
        "huge-pages-jit": true,
        "max-threads-hint": 100
    },
    "pools": [
        {
            "url": "${P2POOL_HOST}:${P2POOL_PORT}",
            "user": "x",
            "keepalive": true,
            "tls": false
        }
    ],
    "http": {
        "enabled": true,
        "host": "127.0.0.1",
        "port": 8082,
        "access-token": null,
        "restricted": true
    },
    "donate-level": 1,
    "log-file": null,
    "print-time": 60
}
XMRIG_CFG

    # XMRig systemd unit
    cat > /etc/systemd/system/xmrig.service << 'XMRIG_UNIT'
[Unit]
Description=XMRig Monero Miner
After=network-online.target
Wants=network-online.target

[Service]
User=root
Group=root
Type=simple
ExecStart=/opt/xmrig/xmrig --config /etc/xmrig/config.json
Restart=always
RestartSec=5
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
XMRIG_UNIT

    systemctl enable xmrig.service

    # UFW
    ufw allow from 192.168.200.0/23 to any port 22 comment 'SSH from LAN'
    ufw --force enable

    # Install GRUB
    grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=ubuntu --recheck
    update-grub

    # Enable serial console for headless debugging
    systemctl enable serial-getty@ttyS0.service 2>/dev/null || true

    echo 'Configuration complete.'
CHROOT_EOF
"

echo "    Ubuntu fully configured."

# --- Step 6: Reboot ---
echo ""
echo "============================================="
echo "  Installation complete!"
echo ""
echo "  Rebooting target into Ubuntu 24.04..."
echo "  After ~60 seconds, connect with:"
echo ""
echo "    ssh josh@${TARGET_IP}"
echo "    sudo systemctl status xmrig"
echo ""
echo "  Expected hashrate: ~10.5 KH/s"
echo "============================================="
echo ""
read -p "  Press Enter to reboot the target, or Ctrl+C to abort..."

ssh "${SSH_USER}@${TARGET_IP}" "
  # Unmount chroot binds
  umount /mnt/target/sys/firmware/efi/efivars 2>/dev/null || true
  umount /mnt/target/dev/pts 2>/dev/null || true
  umount /mnt/target/dev 2>/dev/null || true
  umount /mnt/target/proc 2>/dev/null || true
  umount /mnt/target/sys 2>/dev/null || true
  umount /mnt/target/boot/efi 2>/dev/null || true
  umount /mnt/target 2>/dev/null || true
  sync
  echo 'Rebooting...'
  reboot -f
" || true

echo ""
echo "Target is rebooting. Waiting 60 seconds..."
sleep 60

# Try to connect
echo "Attempting SSH to josh@${TARGET_IP}..."
for i in 1 2 3 4 5; do
  if ssh -o BatchMode=yes -o ConnectTimeout=10 "josh@${TARGET_IP}" "hostname && systemctl is-active xmrig" 2>/dev/null; then
    echo ""
    echo "SUCCESS! Rainbow is back on Ubuntu 24.04 with XMRig running."
    ssh "josh@${TARGET_IP}" "xmrig --version && echo '---' && cat /etc/os-release | head -3"
    exit 0
  fi
  echo "  Attempt $i/5 — not ready yet, waiting 15 seconds..."
  sleep 15
done

echo ""
echo "Target hasn't come back yet. It may still be booting."
echo "Try manually: ssh josh@${TARGET_IP}"
