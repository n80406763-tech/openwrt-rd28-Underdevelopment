#!/bin/bash
# OpenWrt RD28 build setup for WSL2 Ubuntu 22.04
# Run: bash /mnt/c/Users/Nikita/Downloads/openwrt-ra82-main/wsl_build_setup.sh

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err() { echo -e "${RED}[!]${NC} $1"; }

WIN_DIR="/mnt/c/Users/Nikita/Downloads/openwrt-ra82-main"
WORK_DIR="$HOME/openwrt-rd28"

log "=== OpenWrt RD28 (Xiaomi AX3000 NE) Build ==="
log "Work dir: $WORK_DIR"
log "Windows files: $WIN_DIR"
echo ""

# ── Step 1: Dependencies ──────────────────────────────────────────────────────
log "[1/7] Installing build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    build-essential clang flex bison g++ gawk gcc-multilib g++-multilib \
    gettext git libncurses-dev libssl-dev python3-distutils rsync unzip \
    zlib1g-dev file wget python3-setuptools swig libpython3-dev \
    libelf-dev pkg-config lzma quilt 2>/dev/null
log "Dependencies installed"

# ── Step 2: Clone OpenWrt ─────────────────────────────────────────────────────
log "[2/7] Cloning OpenWrt (mainline, qualcommax branch)..."
# Use mainline OpenWrt - it has ipq50xx support via PR #17182
if [ ! -d "$WORK_DIR/.git" ]; then
    git clone --depth=1 \
        https://github.com/openwrt/openwrt.git \
        "$WORK_DIR"
    log "Cloned mainline OpenWrt"
else
    warn "Already cloned, updating..."
    git -C "$WORK_DIR" pull --depth=1
fi

# ── Step 3: Add RD28 device files ─────────────────────────────────────────────
log "[3/7] Adding RD28 device support..."

DTS_DIR="$WORK_DIR/target/linux/qualcommax/files/arch/arm/boot/dts"
mkdir -p "$DTS_DIR"

# Copy DTS
cp "$WIN_DIR/qcom-ipq5018-rd28.dts" "$DTS_DIR/"
log "  Copied DTS: qcom-ipq5018-rd28.dts"

# Add device entry to ipq50xx.mk Makefile
IPQ50XX_MK="$WORK_DIR/target/linux/qualcommax/image/ipq50xx.mk"
if [ -f "$IPQ50XX_MK" ]; then
    if ! grep -q "xiaomi_rd28" "$IPQ50XX_MK"; then
        # Insert before the last $(eval ...) block
        python3 - "$IPQ50XX_MK" << 'PYEOF'
import sys

filepath = sys.argv[1]
with open(filepath, 'r') as f:
    content = f.read()

rd28_def = '''
define Device/xiaomi_rd28
  $(call Device/FitImage)
  $(call Device/UbiFit)
  DEVICE_VENDOR := Xiaomi
  DEVICE_MODEL := RD28
  DEVICE_VARIANT := AX3000 NE
  SOC := ipq5018
  DEVICE_DTS_CONFIG := config@mp03.3
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  KERNEL_IN_UBI := 1
  DEVICE_PACKAGES := ath11k-firmware-ipq5018-qcn6122 \\
\tipq-wifi-xiaomi_rd28
endef
TARGET_DEVICES += xiaomi_rd28
'''

# Insert before the last eval line
last_eval = content.rfind('$(eval $(call BuildImage))')
if last_eval != -1:
    content = content[:last_eval] + rd28_def + '\n' + content[last_eval:]
else:
    content += rd28_def

with open(filepath, 'w') as f:
    f.write(content)

print('  RD28 device entry added to ipq50xx.mk')
PYEOF
    else
        warn "  xiaomi_rd28 already in ipq50xx.mk"
    fi
else
    err "ipq50xx.mk not found at $IPQ50XX_MK!"
    err "Check that the repo has ipq50xx support (mainline OpenWrt)"
fi

# ── Step 4: Add ART/caldata extraction script ─────────────────────────────────
log "[4/7] Adding caldata extraction script..."

CALDATA_DIR="$WORK_DIR/target/linux/qualcommax/ipq50xx/base-files/lib/firmware"
mkdir -p "$CALDATA_DIR"

HOTPLUG_DIR="$WORK_DIR/target/linux/qualcommax/ipq50xx/base-files/etc/hotplug.d/firmware"
mkdir -p "$HOTPLUG_DIR"

cat > "$HOTPLUG_DIR/11-ath11k-caldata-rd28" << 'CALEOF'
#!/bin/sh
# Xiaomi RD28 - Extract ath11k calibration from ART partition (mtd13)
# ART layout:
#   0x0000: MAC addresses (WAN + LAN, 12 bytes)
#   0x1000: QCA5018 2.4GHz calibration data
#   0x28000: QCN6122 5GHz calibration region start

[ "$(board_name)" = "xiaomi,rd28" ] || exit 0

# Find ART MTD partition
ART_MTD=$(cat /proc/mtd | awk -F: '/0:ART/{print $1}')
[ -n "$ART_MTD" ] || ART_MTD="mtd13"

# QCA5018 (2.4GHz, AHB - integrated)
mkdir -p /lib/firmware/ath11k/IPQ5018/hw1.0
dd if=/dev/${ART_MTD} of=/lib/firmware/ath11k/IPQ5018/hw1.0/caldata.bin \
    bs=4096 skip=1 count=256 2>/dev/null

# QCN6122 (5GHz, PCIe)
mkdir -p /lib/firmware/ath11k/QCN6122/hw1.0
dd if=/dev/${ART_MTD} of=/lib/firmware/ath11k/QCN6122/hw1.0/caldata.bin \
    bs=4096 skip=40 count=256 2>/dev/null
CALEOF
chmod +x "$HOTPLUG_DIR/11-ath11k-caldata-rd28"
log "  Caldata extraction script created"

# ── Step 5: Add network config ─────────────────────────────────────────────────
log "[5/7] Adding network configuration..."

BOARD_DIR="$WORK_DIR/target/linux/qualcommax/ipq50xx/base-files/etc/board.d"
mkdir -p "$BOARD_DIR"

# Add to 02_network (append xiaomi,rd28 case)
NETWORK_FILE="$BOARD_DIR/02_network"
if [ -f "$NETWORK_FILE" ]; then
    if ! grep -q "xiaomi,rd28" "$NETWORK_FILE"; then
        # Find the esac and insert before it
        python3 - "$NETWORK_FILE" << 'PYEOF'
import sys, re

filepath = sys.argv[1]
with open(filepath, 'r') as f:
    content = f.read()

rd28_case = '''
xiaomi,rd28)
\tucidef_set_interfaces_lan_wan "lan" "wan"
\tucidef_set_network_device_conduit "wan" "eth0"
\tucidef_set_network_device_conduit "lan" "eth1"
\t;;'''

# Insert before the wildcard/esac
content = content.replace('\n\t*)', rd28_case + '\n\n\t*)')

with open(filepath, 'w') as f:
    f.write(content)
print('  Added xiaomi,rd28 to 02_network')
PYEOF
    fi
fi

# ── Step 6: Update feeds and configure ────────────────────────────────────────
log "[6/7] Updating feeds..."
cd "$WORK_DIR"
./scripts/feeds update -a 2>&1 | tail -3
./scripts/feeds install -a 2>&1 | tail -3

# Create .config
cat > "$WORK_DIR/.config" << 'CONFIG_EOF'
CONFIG_TARGET_qualcommax=y
CONFIG_TARGET_qualcommax_ipq50xx=y
CONFIG_TARGET_MULTI_PROFILE=n
CONFIG_TARGET_qualcommax_ipq50xx_DEVICE_xiaomi_rd28=y
CONFIG_TARGET_ROOTFS_SQUASHFS=y
CONFIG_PACKAGE_kmod-ath11k=y
CONFIG_PACKAGE_kmod-ath11k-ahb=y
CONFIG_PACKAGE_kmod-ath11k-pci=y
CONFIG_PACKAGE_ath11k-firmware-ipq5018-qcn6122=y
CONFIG_PACKAGE_ppp=y
CONFIG_PACKAGE_ppp-mod-pppoe=y
CONFIG_PACKAGE_nano=y
# CONFIG_PACKAGE_luci is not set
# CONFIG_TARGET_ROOTFS_JFFS2 is not set
# CONFIG_TARGET_ROOTFS_EXT4FS is not set
CONFIG_EOF

make defconfig 2>&1 | tail -3
log "Build config created"

# ── Step 7: Build ─────────────────────────────────────────────────────────────
log "[7/7] Starting build..."
warn "This will take 1-4 hours depending on CPU cores ($(nproc) cores available)"
warn "Log: $WORK_DIR/build.log"
echo ""

# Start build in background with logging
make -j$(nproc) V=s 2>&1 | tee "$WORK_DIR/build.log"

BUILD_EXIT=$?
if [ $BUILD_EXIT -eq 0 ]; then
    log "=== BUILD SUCCESSFUL ==="
    log "Images at: $WORK_DIR/bin/targets/qualcommax/ipq50xx/"
    ls -la "$WORK_DIR/bin/targets/qualcommax/ipq50xx/"*rd28* 2>/dev/null || \
        ls -la "$WORK_DIR/bin/targets/qualcommax/ipq50xx/"

    # Copy to Windows
    cp "$WORK_DIR/bin/targets/qualcommax/ipq50xx/"*rd28*.ubi "$WIN_DIR/" 2>/dev/null || true
    log "Copied .ubi images to: $WIN_DIR"
else
    err "Build failed! Check: $WORK_DIR/build.log"
    tail -30 "$WORK_DIR/build.log"
fi
