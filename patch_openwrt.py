#!/usr/bin/env python3
"""Patches OpenWrt tree for Xiaomi RD28 support."""
import sys, re, os

openwrt = sys.argv[1] if len(sys.argv) > 1 else "openwrt"

# 1. Append device entry to ipq50xx.mk
mk_path = f"{openwrt}/target/linux/qualcommax/image/ipq50xx.mk"
if not os.path.exists(mk_path):
    print(f"ERROR: {mk_path} not found"); sys.exit(1)

with open(mk_path) as f:
    mk = f.read()

if "xiaomi_rd28" not in mk:
    entry = """
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
  DEVICE_PACKAGES := ath11k-firmware-ipq5018-qcn6122 kmod-ath11k-ahb kmod-ath11k-pci
endef
TARGET_DEVICES += xiaomi_rd28
"""
    with open(mk_path, "a") as f:
        f.write(entry)
    print("Added xiaomi_rd28 to ipq50xx.mk")
else:
    print("xiaomi_rd28 already in ipq50xx.mk")

# 2. Add network config for rd28
net_path = f"{openwrt}/target/linux/qualcommax/ipq50xx/base-files/etc/board.d/02_network"
if os.path.exists(net_path):
    with open(net_path) as f:
        net = f.read()
    if "xiaomi,rd28" not in net:
        rd28_case = "\nxiaomi,rd28)\n\tucidef_set_interfaces_lan_wan \"lan\" \"wan\"\n\t;;"
        net = re.sub(r'(\n\t\*\))', rd28_case + r'\n\1', net, count=1)
        with open(net_path, "w") as f:
            f.write(net)
        print("Added xiaomi,rd28 to 02_network")
else:
    print(f"NOTE: {net_path} not found, skipping")

print("Patching done.")
