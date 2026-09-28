"""Comprehensive parity and integration tests for native Python tsh_client and tsh_pel."""

import hashlib
import os
import subprocess

from tsh_pel import TshClient, load_key_seed


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


def test_python_client_direct_cli_ps(tshd_daemon):
    """Verify single-shot CLI 'ps' invocation parses /proc correctly."""
    config = tshd_daemon
    # With explicit host
    cmd = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "localhost",
        "ps",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0
    assert "PID" in res.stdout and "COMMAND" in res.stdout
    assert "tshd" in res.stdout

    # With implicit host (tsh ps)
    cmd_implicit = [
        "python3",
        "tsh_client.py",
        "-k",
        config["key_path"],
        "-p",
        str(config["port"]),
        "ps",
    ]
    res_implicit = subprocess.run(cmd_implicit, capture_output=True, text=True, check=False)
    assert res_implicit.returncode == 0
    assert "PID" in res_implicit.stdout and "COMMAND" in res_implicit.stdout



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


def test_persistent_session_multi_command(tshd_daemon, tmp_path):
    """Verify that multiple operations execute over a single persistent session."""
    config = tshd_daemon
    client = TshClient(
        host="localhost",
        port=config["port"],
        keyfile=config["key_path"],
    )

    # Run 10 sequential operations within one connection session
    with client.session() as sess:
        # 1. ls root
        res1 = client.run_ls("/", capture_output=True, session=sess)
        assert res1.returncode == 0
        assert "bin" in res1.stdout or "etc" in res1.stdout

        # 2. exec echo
        res2 = client.run_exec("/usr/bin/true", capture_output=True, session=sess)
        assert res2.returncode == 0

        # 3. put a file
        local_file = tmp_path / "session_file.txt"
        local_file.write_text("session content\n")
        res3 = client.run_put(str(local_file), "/var/tmp", capture_output=True, session=sess)
        assert res3.returncode == 0

        # 4. read file bytes back
        data = client.read_file_bytes("/var/tmp/session_file.txt", session=sess)
        assert data == b"session content\n"

        # 5. cleanup file
        res5 = client.run_exec("/bin/rm -f /var/tmp/session_file.txt", capture_output=True, session=sess)
        assert res5.returncode == 0

        # 6. run ps
        res6 = client.run_ps(capture_output=True, session=sess)
        assert res6.returncode == 0
        assert "PID" in res6.stdout and "COMMAND" in res6.stdout


def test_persistent_session_error_lockstep(tshd_daemon):
    """Verify non-existent paths return 0-byte frames and do not desynchronize sequence numbers."""
    config = tshd_daemon
    client = TshClient(
        host="localhost",
        port=config["port"],
        keyfile=config["key_path"],
    )

    with client.session() as sess:
        # Request non-existent directory listing
        res_ls = client.run_ls("/nonexistent_dir_99999", capture_output=True, session=sess)
        assert res_ls.returncode == 0
        assert res_ls.stdout == ""

        # Request non-existent file download
        data = client.read_file_bytes("/nonexistent_file_99999.txt", session=sess)
        assert data == b""

        # Immediately run valid command to prove sequence counters remain in sync
        res_valid = client.run_exec("/usr/bin/true", capture_output=True, session=sess)
        assert res_valid.returncode == 0

