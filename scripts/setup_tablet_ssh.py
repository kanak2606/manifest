#!/usr/bin/env python3
"""
Setup Passwordless SSH Key on Tablet
Generates ~/.ssh/id_tablet (unencrypted) if missing, and installs it onto the tablet using password '123'.
"""
import os
import sys
import subprocess
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("[!] paramiko not found in current Python, attempting import fallback...")
    paramiko = None


def setup_tablet_ssh(tablet_ip="192.168.10.105", ports=(5022, 8022), user="u0_a221", password="123"):
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    key_path = ssh_dir / "id_tablet"
    pub_key_path = ssh_dir / "id_tablet.pub"

    # Step 1: Ensure unencrypted key exists
    if not key_path.exists() or not pub_key_path.exists():
        print(f"[*] Generating unencrypted ed25519 key at {key_path}...")
        res = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path), "-C", "notetrace-tablet", "-q"],
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            print(f"[X] Failed to generate key: {res.stderr}")
            return False

    pub_key_str = pub_key_path.read_text(encoding="utf-8").strip()
    print(f"[*] Local public key: {pub_key_str[:30]}...{pub_key_str[-15:]}")

    # Step 2: Connect to tablet via paramiko using password
    if paramiko is None:
        print("[X] Paramiko is required to push the key without password prompt.")
        return False

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connected = False
    connected_port = None
    for p in ports:
        try:
            print(f"[*] Connecting to {tablet_ip}:{p} with user '{user}'...")
            client.connect(tablet_ip, port=p, username=user, password=password, timeout=5, look_for_keys=False)
            connected = True
            connected_port = p
            print(f"[✓] Connected to tablet on port {p}!")
            break
        except Exception as e:
            print(f"[-] Port {p} failed: {e}")

    if not connected:
        print(f"[X] Could not connect to tablet {tablet_ip} on any port {ports}.")
        return False

    # Step 3: Append public key to ~/.ssh/authorized_keys
    remote_sh = (
        "mkdir -p ~/.ssh && "
        "touch ~/.ssh/authorized_keys && "
        f"grep -q -F '{pub_key_str}' ~/.ssh/authorized_keys || echo '{pub_key_str}' >> ~/.ssh/authorized_keys && "
        "chmod 700 ~/.ssh && "
        "chmod 600 ~/.ssh/authorized_keys && "
        "echo KEY_INSTALLED_OK"
    )

    stdin, stdout, stderr = client.exec_command(remote_sh)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    client.close()

    if "KEY_INSTALLED_OK" in out:
        print(f"[✓] Successfully authorized id_tablet on tablet {tablet_ip}:{connected_port}!")
    else:
        print(f"[!] Warning: Unexpected remote response: {out} {err}")

    # Step 4: Configure ~/.ssh/config entry
    config_path = ssh_dir / "config"
    tablet_config_block = f"""
# Manifest & NoteTrace Android Tablet Configuration
Host tablet
    HostName {tablet_ip}
    User {user}
    Port {connected_port or 5022}
    IdentityFile ~/.ssh/id_tablet
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR

Host {tablet_ip}
    User {user}
    Port {connected_port or 5022}
    IdentityFile ~/.ssh/id_tablet
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
"""
    existing_config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    # Strip existing tablet block if any
    cleaned_lines = []
    skip = False
    for line in existing_config.splitlines():
        if line.strip().startswith("Host tablet") or line.strip().startswith(f"Host {tablet_ip}"):
            skip = True
        elif skip and line.strip().startswith("Host "):
            skip = False
        if not skip and line.strip() != "# Manifest & NoteTrace Android Tablet Configuration":
            cleaned_lines.append(line)

    new_config = "\n".join(cleaned_lines).strip() + "\n" + tablet_config_block.strip() + "\n"
    config_path.write_text(new_config, encoding="utf-8")
    print(f"[✓] Updated {config_path} with dedicated id_tablet identity mapping.")

    # Step 5: Test OpenSSH client connection with id_tablet
    print("[*] Testing zero-prompt OpenSSH connection...")
    test_cmd = [
        "ssh",
        "-i", str(key_path),
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",
        "-p", str(connected_port or 5022),
        f"{user}@{tablet_ip}",
        "echo ZERO_PROMPT_SUCCESS"
    ]
    test_res = subprocess.run(test_cmd, capture_output=True, text=True)
    if "ZERO_PROMPT_SUCCESS" in test_res.stdout:
        print("[✓] 100% AUTOMATIC CONNECTION VERIFIED! No passphrase, no password prompt!")
        return True
    else:
        print(f"[!] Test connection output: {test_res.stdout} (err: {test_res.stderr})")
        return False


if __name__ == "__main__":
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.10.105"
    success = setup_tablet_ssh(tablet_ip=ip)
    sys.exit(0 if success else 1)
