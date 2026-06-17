"""
SSH client for legacy Xiaomi router (Dropbear with ssh-rsa / SHA-1).
Patches paramiko to accept old RSA signatures.
"""
import paramiko
from paramiko import RSAKey, Message
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import time

# Patch RSAKey to also verify ssh-rsa (SHA-1) signatures that paramiko 3.x dropped
_orig_verify = RSAKey.verify_ssh_sig

def _patched_verify(self, data, msg):
    try:
        return _orig_verify(self, data, msg)
    except Exception:
        # Try legacy SHA-1 verification
        try:
            msg.rewind()
            keytype = msg.get_text()
            sig = msg.get_binary()
            self.key.verify(sig, data, padding.PKCS1v15(), hashes.SHA1())
            return True
        except Exception:
            return False

RSAKey.verify_ssh_sig = _patched_verify

# Also patch _verify_key to not fail on False return
import paramiko.transport as _pt
_orig_verify_key = _pt.Transport._verify_key

def _patched_verify_key(self, host_key, sig):
    from paramiko.message import Message as Msg
    from paramiko import SSHException
    host_key_type = self.host_key_type
    key = self._key_info[host_key_type](Msg(host_key))
    if not self.get_server_key():
        self.host_key = key
    if not key.verify_ssh_sig(self.H, Msg(sig)):
        # Accept anyway for legacy - just warn
        print('[!] Warning: host key signature could not be verified (legacy SHA-1), proceeding anyway')
    self.host_key = key

_pt.Transport._verify_key = _patched_verify_key

# Now set up transport with RSA key support
class LegacyTransport(paramiko.Transport):
    _preferred_keys = ['ssh-rsa', 'ecdsa-sha2-nistp256', 'rsa-sha2-256', 'ssh-ed25519']
    _preferred_kex = [
        'curve25519-sha256',
        'curve25519-sha256@libssh.org',
        'ecdh-sha2-nistp256',
        'diffie-hellman-group14-sha256',
        'diffie-hellman-group-exchange-sha256',
    ]

paramiko.Transport._key_info['ssh-rsa'] = RSAKey

def run(host, user, password, commands, output_file=None):
    t = LegacyTransport((host, 22))
    t.start_client(timeout=10)
    key = t.get_remote_server_key()
    print(f'[+] Connected to {host}, server key: {key.get_name()}')
    t.auth_password(user, password)
    print(f'[+] Auth OK')

    results = {}
    for cmd in commands:
        ch = t.open_session()
        ch.exec_command(cmd)
        out = b''
        while True:
            if ch.recv_ready():
                out += ch.recv(65536)
            elif ch.exit_status_ready():
                chunk = ch.recv(65536)
                out += chunk
                if not chunk:
                    break
            else:
                time.sleep(0.1)
        decoded = out.decode(errors='replace').strip()
        results[cmd] = decoded
        print(f'\n=== {cmd} ===')
        print(decoded)
        ch.close()

    t.close()

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for cmd, out in results.items():
                f.write(f'\n=== {cmd} ===\n{out}\n')
        print(f'\n[+] Saved to {output_file}')

    return results

COMMANDS = [
    'uname -a',
    'cat /proc/cmdline',
    'cat /proc/mtd',
    'nvram show 2>/dev/null | grep -E "flag_boot|flag_last|flag_try|model|board|hardware|productid|bdata"',
    'cat /proc/device-tree/compatible 2>/dev/null | tr "\\0" "\\n"; echo END',
    'cat /proc/device-tree/model 2>/dev/null; echo',
    'ls /proc/device-tree/ 2>/dev/null',
    'find /proc/device-tree -maxdepth 2 -name "compatible" 2>/dev/null | head -30',
    'dmesg | grep -i -E "soc|ipq|board|machine|nand|ubi|qca|wifi|eth|cpu" | head -60',
    'cat /sys/firmware/devicetree/base/model 2>/dev/null || echo N/A',
    'ip addr show',
    'cat /etc/os-release 2>/dev/null',
    'flash_eraseall --version 2>/dev/null; ubinfo -a 2>/dev/null | head -20',
    'cat /proc/cpuinfo',
    'free',
    'df -h',
    'ls /dev/mtd*',
    'dd if=/dev/mtdblock15 bs=1 count=512 2>/dev/null | strings | head -30',  # bdata: MACs/serial
]

for pwd in ['root', 'Nikita2201', '', 'admin']:
    try:
        run('192.168.31.1', 'root', pwd, COMMANDS, output_file='router_info.txt')
        print(f'\n[+] Done! Password was: "{pwd}"')
        break
    except paramiko.AuthenticationException:
        print(f'[-] Password "{pwd}" rejected')
    except Exception as e:
        import traceback; traceback.print_exc()
        break
