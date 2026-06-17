"""
Flash OpenWrt UBI image to Xiaomi RD28 (Slot A, mtd18).
Boots into OpenWrt using A/B boot system.

Usage: python flash_rd28.py <path-to-openwrt.ubi>
       python flash_rd28.py  (auto-find .ubi in current directory)
"""
import paramiko
from paramiko import RSAKey
from paramiko.kex_group14 import KexGroup14SHA256
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from hashlib import sha1
import base64, os, sys, time, glob

# ── Legacy SSH patches ────────────────────────────────────────────────────────
class KexGroup14SHA1(KexGroup14SHA256):
    name = 'diffie-hellman-group14-sha1'
    hash_algo = sha1
paramiko.Transport._kex_info['diffie-hellman-group14-sha1'] = KexGroup14SHA1

_orig_verify = RSAKey.verify_ssh_sig
def _pv(self, data, msg):
    try:
        return _orig_verify(self, data, msg)
    except Exception:
        try:
            msg.rewind(); msg.get_text(); sig = msg.get_binary()
            self.key.verify(sig, data, padding.PKCS1v15(), hashes.SHA1())
            return True
        except: return False
RSAKey.verify_ssh_sig = _pv

import paramiko.transport as _pt
def _pvk(self, host_key, sig):
    from paramiko.message import Message as M
    key = self._key_info[self.host_key_type](M(host_key))
    key.verify_ssh_sig(self.H, M(sig))
    self.host_key = key
_pt.Transport._verify_key = _pvk
paramiko.Transport._key_info['ssh-rsa'] = RSAKey

class LT(paramiko.Transport):
    _preferred_keys = ['ssh-rsa', 'ecdsa-sha2-nistp256', 'rsa-sha2-256']
    _preferred_kex = ['diffie-hellman-group14-sha256', 'diffie-hellman-group-exchange-sha256',
                      'diffie-hellman-group14-sha1', 'ecdh-sha2-nistp256',
                      'curve25519-sha256', 'curve25519-sha256@libssh.org']

HOST, USER, PASS = '192.168.31.1', 'root', 'Nikita2201'
ROUTER_TMP = '/tmp/openwrt.ubi'
TARGET_MTD = '/dev/mtd18'  # Slot A (rootfs)

def connect():
    t = LT((HOST, 22))
    t.start_client(timeout=10)
    t.auth_password(USER, PASS)
    return t

def run(t, cmd, timeout=30):
    ch = t.open_session()
    ch.exec_command(cmd)
    out = b''
    start = time.time()
    while True:
        if ch.recv_ready(): out += ch.recv(65536)
        elif ch.exit_status_ready(): out += ch.recv(65536); break
        elif time.time()-start > timeout: break
        else: time.sleep(0.1)
    rc = ch.recv_exit_status()
    ch.close()
    return out.decode(errors='replace').strip(), rc

def upload_sftp(t, local_path, remote_path):
    sftp = paramiko.SFTPClient.from_transport(t)
    file_size = os.path.getsize(local_path)
    print(f'  Uploading {os.path.basename(local_path)} ({file_size:,} bytes)...')
    uploaded = [0]
    def progress(done, total):
        pct = done * 100 // total
        bar = '█' * (pct // 5) + '░' * (20 - pct // 5)
        print(f'\r  [{bar}] {pct}% ({done:,}/{total:,})', end='', flush=True)
    sftp.put(local_path, remote_path, callback=progress)
    print()
    sftp.close()

# ── Find UBI image ─────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    ubi_path = sys.argv[1]
else:
    # Auto-find
    candidates = (
        glob.glob('*rd28*.ubi') +
        glob.glob('*ipq50xx*.ubi') +
        glob.glob('*squashfs-nand*.ubi')
    )
    if not candidates:
        print('ERROR: No .ubi file found. Pass path as argument.')
        print('Usage: python flash_rd28.py openwrt-qualcommax-ipq50xx-xiaomi_rd28-squashfs-nand-ubi.bin')
        sys.exit(1)
    ubi_path = candidates[0]

if not os.path.exists(ubi_path):
    print(f'ERROR: File not found: {ubi_path}')
    sys.exit(1)

print(f'\n=== Xiaomi RD28 OpenWrt Flasher ===')
print(f'Image: {ubi_path} ({os.path.getsize(ubi_path):,} bytes)')
print(f'Target: {HOST} -> {TARGET_MTD} (Slot A)')
print()

# ── Safety checks ──────────────────────────────────────────────────────────────
print('[0] Connecting to router...')
t = connect()
print(f'    Connected!')

# Check current state
out, _ = run(t, 'nvram get flag_boot_rootfs && nvram get flag_boot_success')
print(f'    Current boot slot: {out}')

out, _ = run(t, 'cat /proc/mtd | grep rootfs')
print(f'    MTD partitions:\n{out}')

# Free space check
out, _ = run(t, 'df -h /tmp')
print(f'    /tmp free:\n{out}')

print()
input('Press ENTER to continue with flashing (Ctrl+C to abort)...')

# ── Upload image ───────────────────────────────────────────────────────────────
print(f'\n[1] Uploading OpenWrt image to {ROUTER_TMP}...')
upload_sftp(t, ubi_path, ROUTER_TMP)

# Verify upload
out, _ = run(t, f'ls -la {ROUTER_TMP}')
print(f'    Uploaded: {out}')

# Check UBI signature
out, _ = run(t, f'dd if={ROUTER_TMP} bs=1 count=4 2>/dev/null | xxd')
print(f'    UBI signature: {out}')
if 'UBI#' not in out and '55 42 49 23' not in out:
    print('WARNING: UBI signature not found in image! Aborting.')
    t.close()
    sys.exit(1)
print('    UBI signature OK')

# ── Flash to Slot A (mtd18) ───────────────────────────────────────────────────
print(f'\n[2] Flashing to {TARGET_MTD} (Slot A / rootfs)...')
print('    This will take 30-120 seconds...')

cmd = f'ubiformat {TARGET_MTD} -f {ROUTER_TMP} -s 2048 -O 2048 -y'
out, rc = run(t, cmd, timeout=300)
print(f'    ubiformat output:\n{out}')
if rc != 0:
    print(f'ERROR: ubiformat failed with exit code {rc}')
    t.close()
    sys.exit(1)

# Verify flash
out, _ = run(t, f'dd if={TARGET_MTD} bs=1 count=4 2>/dev/null | xxd')
print(f'    Verify signature in mtd18: {out}')

# ── Set boot flags ────────────────────────────────────────────────────────────
print(f'\n[3] Setting boot flags to boot Slot A (OpenWrt)...')
cmds = [
    'nvram set flag_boot_rootfs=0',      # Boot from Slot A
    'nvram set flag_last_success=0',      # Mark as not yet successful
    'nvram set flag_try_sys1_failed=0',   # Reset Slot A fail counter
    'nvram set flag_try_sys2_failed=0',   # Reset Slot B fail counter
    'nvram set flag_boot_success=0',
    'nvram commit',
]
for cmd in cmds:
    out, rc = run(t, cmd)
    print(f'    {cmd}: {"OK" if rc == 0 else f"FAILED ({rc})"} {out}')

# Verify
out, _ = run(t, 'nvram get flag_boot_rootfs && nvram get flag_try_sys1_failed')
print(f'    Verified: flag_boot_rootfs={out.split()[0] if out else "?"}, '
      f'flag_try_sys1_failed={out.split()[1] if len(out.split()) > 1 else "?"}')

# ── Reboot ────────────────────────────────────────────────────────────────────
print(f'\n[4] Rebooting...')
print('    The router will try to boot OpenWrt from Slot A.')
print('    If it fails 3 times, it will automatically fall back to Xiaomi firmware.')
print()
print('    After reboot, OpenWrt should be accessible at: http://192.168.1.1')
print('    SSH: ssh root@192.168.1.1 (no password initially)')
print()
input('Press ENTER to reboot (Ctrl+C to abort)...')

try:
    run(t, 'reboot', timeout=5)
except:
    pass

t.close()
print('\n=== Router is rebooting! ===')
print('Wait 60-90 seconds, then try: http://192.168.1.1 or ssh root@192.168.1.1')
print('If no access, the router fell back to Xiaomi firmware (192.168.31.1)')
