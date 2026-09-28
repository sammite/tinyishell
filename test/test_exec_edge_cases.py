"""Integration tests for remote execution edge cases in Tiny SHell."""

import os
import stat
import subprocess

from tsh_client import TshRepl
from tsh_pel import TshClient


def test_exec_relative_path_resolution(tshd_daemon):
    """Verify that relative paths in exec are resolved against remote_cwd in the REPL."""
    config = tshd_daemon
    script_path = "/var/tmp/tsh_rel_test.sh"
    with open(script_path, "w") as f:
        f.write("#!/bin/sh\nexit 42\n")
    os.chmod(script_path, 0o755)

    try:
        repl = TshRepl(
            host="localhost",
            secret=config["secret"],
            port=config["port"],
            initial_dir="/var/tmp",
        )
        repl.get_or_create_session()

        repl.do_exec("./tsh_rel_test.sh")
        assert repl.last_exit_code == 42
    finally:
        if os.path.exists(script_path):
            os.unlink(script_path)


def test_exec_command_not_found_returns_127(tshd_daemon):
    """Verify that executing a non-existent binary returns standard POSIX 127 exit code."""
    config = tshd_daemon
    client = TshClient(
        host="localhost",
        port=config["port"],
        keyfile=config["key_path"],
    )

    res = client.run_exec("/nonexistent/binary/path_987654", capture_output=True)
    assert res.returncode == 127


def test_exec_permission_denied_returns_126(tshd_daemon):
    """Verify that executing a file without execute permission returns standard POSIX 126 exit code."""
    config = tshd_daemon
    test_file = "/var/tmp/non_exec_test_file.txt"
    with open(test_file, "w") as f:
        f.write("plain text file without execute bit")
    os.chmod(test_file, 0o644)

    try:
        client = TshClient(
            host="localhost",
            port=config["port"],
            keyfile=config["key_path"],
        )

        res = client.run_exec(test_file, capture_output=True)
        assert res.returncode == 126
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)


def test_exec_quoted_arguments(tshd_daemon):
    """Verify executing shell commands with arguments containing spaces and quotes."""
    config = tshd_daemon
    client = TshClient(
        host="localhost",
        port=config["port"],
        keyfile=config["key_path"],
    )

    marker = "/var/tmp/quoted_test_marker"
    if os.path.exists(marker):
        os.unlink(marker)

    try:
        res = client.run_exec(f"/usr/bin/touch {marker}", capture_output=True)
        assert res.returncode == 0
        assert os.path.exists(marker)
    finally:
        if os.path.exists(marker):
            os.unlink(marker)
