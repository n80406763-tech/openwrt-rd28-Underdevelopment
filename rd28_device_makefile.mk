# Xiaomi RD28 (AX3000 NE) device definition for OpenWrt
# Place in: target/linux/qualcommax/image/ipq50xx.mk
# Add before the final $(eval ...) calls

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
  DEVICE_PACKAGES := ath11k-firmware-ipq5018-qcn6122 \
	kmod-ath11k-ahb \
	kmod-ath11k-pci \
	ipq-wifi-xiaomi_rd28
endef
TARGET_DEVICES += xiaomi_rd28
