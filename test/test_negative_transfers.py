"""Negative and boundary integration tests for Tiny SHell file transfers."""

import os
import subprocess

from tsh_pel import TshClient


def test_get_nonexistent_remote_file_preserves_local(tshd_daemon, tmp_path):
    """Verify downloading a non-existent remote file fails with exit code 2 and leaves local file intact."""
    config = tshd_daemon
    local_target = tmp_path / "protected_target.txt"
    initial_content = "DO_NOT_TRUNCATE_THIS_PAYLOAD"
    local_target.write_text(initial_content)

    res = subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "get",
            "/var/tmp/nonexistent_remote_file_83749.bin",
            str(local_target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode != 0
    assert "not found or inaccessible" in res.stderr
    assert local_target.exists()
    assert local_target.read_text() == initial_content


def test_get_remote_directory_fails_cleanly(tshd_daemon, tmp_path):
    """Verify attempting to get a remote directory fails and does not create a local file."""
    config = tshd_daemon
    local_target = tmp_path / "should_not_exist.bin"

    res = subprocess.run(
        [
            config["tsh_path"],
            "-s",
            config["secret"],
            "localhost",
            "get",
            "/etc",
            str(local_target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode != 0
    assert not local_target.exists()


def test_put_to_invalid_remote_destination_recovers(tshd_daemon, tmp_path):
    """Verify uploading to an unwritable remote path fails with code 21 and preserves session lockstep."""
    config = tshd_daemon
    local_file = tmp_path / "upload_payload.txt"
    local_file.write_text("sample content")

    client = TshClient(
        host="localhost",
        port=config["port"],
        keyfile=config["key_path"],
    )

    with client.session() as sess:
        # Attempt to put to a path inside read-only /proc
        res_put = client.run_put(
            str(local_file),
            "/proc/nonexistent_dir",
            capture_output=True,
            session=sess,
        )
        assert res_put.returncode == 21
        assert "Server write error" in res_put.stderr

        # Verify session remains in sync and can immediately execute next command
        res_next = client.run_exec("/usr/bin/true", capture_output=True, session=sess)
        assert res_next.returncode == 0
