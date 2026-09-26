"""Integration tests for file transfer operations (put and get) in Tiny SHell."""

import hashlib
import os
import subprocess

import pytest


def get_file_hash(path):
    """Computes SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_put_get_integrity(tshd_daemon, tmp_path):
    """Test file put and get round-trip integrity to an isolated destination directory."""
    config = tshd_daemon

    # 1. Create a local file with specific content
    content = "test_content_for_integrity_check"
    local_file = tmp_path / "tmpfile"
    local_file.write_text(content)

    remote_path = "/var/tmp"
    remote_file = "/var/tmp/tmpfile"

    # 2. Put the file to the remote server
    put_res = subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "put",
            str(local_file),
            remote_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert put_res.returncode == 0, f"Put failed: {put_res.stderr}"

    # 3. Get the file back into an isolated destination folder
    download_dir = tmp_path / "downloaded_single"
    download_dir.mkdir()
    get_res = subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "get",
            remote_file,
            str(download_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert get_res.returncode == 0, f"Get failed: {get_res.stderr}"

    # Check integrity
    downloaded_file = download_dir / "tmpfile"
    assert downloaded_file.exists()
    assert downloaded_file.read_text() == content

    # 4. Cleanup remote file via exec
    subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "exec",
            f"/bin/rm -f {remote_file}",
        ],
        check=False,
    )


@pytest.mark.parametrize("size_kb", [0, 1, 16, 64, 128, 256, 512, 1024])  # 0KB up to 1MB range
def test_large_file_integrity(tshd_daemon, tmp_path, size_kb):
    """Verify integrity of various file sizes across put and get, including 0-byte edge case."""
    config = tshd_daemon
    local_file = tmp_path / f"test_payload_{size_kb}kb"
    remote_path = "/var/tmp"
    remote_file = f"/var/tmp/test_payload_{size_kb}kb"

    # 1. Generate local file with random binary data
    local_file.write_bytes(os.urandom(size_kb * 1024))
    original_hash = get_file_hash(local_file)

    # 2. Put to remote
    put_res = subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "put",
            str(local_file),
            remote_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert put_res.returncode == 0

    # 3. Get back to an isolated local directory
    download_dir = tmp_path / f"downloaded_{size_kb}kb"
    download_dir.mkdir()
    get_res = subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "get",
            remote_file,
            str(download_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert get_res.returncode == 0

    downloaded_file = download_dir / f"test_payload_{size_kb}kb"
    assert downloaded_file.exists()
    downloaded_hash = get_file_hash(downloaded_file)

    # 4. Validate hash integrity
    assert original_hash == downloaded_hash

    # 5. Cleanup remote file
    subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "exec",
            f"/bin/rm -f {remote_file}",
        ],
        check=False,
    )
