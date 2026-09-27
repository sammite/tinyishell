"""Comprehensive parity and integration tests for native Python tsh_client and tsh_pel."""

import hashlib
import os
import subprocess

from tsh_pel import load_key_seed


def get_sha256(path: str) -> str:
    """Computes SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_python_client_direct_cli_ls(tshd_daemon):
    """Verify single-shot CLI 'ls' invocation matching C tsh."""
    config = tshd_daemon
    cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "localhost",
        "ls",
        "/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0
    assert "etc" in res.stdout or "bin" in res.stdout


def test_python_client_direct_cli_exec(tshd_daemon):
    """Verify single-shot CLI 'exec' invocation matching C tsh."""
    config = tshd_daemon
    cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "localhost",
        "exec",
        "/usr/bin/true",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0
    assert "Exit code: 0" in res.stdout


def test_python_client_direct_cli_put_get_integrity(tshd_daemon, tmp_path):
    """Verify single-shot CLI 'put' and 'get' file integrity with binary data."""
    config = tshd_daemon

    # Generate 64KB of random binary data
    payload = os.urandom(65536)
    local_src = tmp_path / "bin_source.dat"
    local_src.write_bytes(payload)
    orig_hash = get_sha256(str(local_src))

    remote_dest_dir = "/var/tmp"
    remote_file = "/var/tmp/bin_source.dat"

    # Put file
    put_cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "localhost",
        "put",
        str(local_src),
        remote_dest_dir,
    ]
    put_res = subprocess.run(put_cmd, capture_output=True, text=True, check=False)
    assert put_res.returncode == 0
    assert "done." in put_res.stdout

    # Get file back
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    get_cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "localhost",
        "get",
        remote_file,
        str(download_dir),
    ]
    get_res = subprocess.run(get_cmd, capture_output=True, text=True, check=False)
    assert get_res.returncode == 0
    assert "done." in get_res.stdout

    downloaded_file = download_dir / "bin_source.dat"
    assert downloaded_file.exists()
    assert get_sha256(str(downloaded_file)) == orig_hash

    # Cleanup remote file
    cleanup_cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "localhost",
        "exec",
        f"/bin/rm -f {remote_file}",
    ]
    subprocess.run(cleanup_cmd, capture_output=True, check=False)


def test_python_client_auth_failure_wrong_key(tshd_daemon, tmp_path):
    """Verify that wrong 32-byte key returns exit code 10 and prints to stderr."""
    config = tshd_daemon
    wrong_key = tmp_path / "wrong_key"
    wrong_key.write_bytes(b"\xbb" * 32)
    cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        str(wrong_key),
        "-p",
        str(config["port"]),
        "localhost",
        "ls",
        "/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 10
    assert "Authentication failed." in res.stderr
    assert res.stdout == ""


def test_python_client_auth_failure_missing_key(tshd_daemon):
    """Verify that missing key file returns exit code 1."""
    config = tshd_daemon
    cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        "/path/does/not/exist/missing_key",
        "-p",
        str(config["port"]),
        "localhost",
        "ls",
        "/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 1
    assert "Key file not found" in res.stderr or "No such file" in res.stderr
    assert res.stdout == ""


def test_python_client_raw_key_seed_derivation(tmp_path):
    """Verify loading raw 32-byte Ed25519 seed from file."""
    seed_bytes = os.urandom(32)
    key_file = tmp_path / "ed25519.seed"
    key_file.write_bytes(seed_bytes)

    signing_key = load_key_seed(str(key_file))
    assert bytes(signing_key) == seed_bytes
