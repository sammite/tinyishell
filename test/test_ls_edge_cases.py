"""Integration tests for remote directory listing edge cases (nesting and long names)."""

import os
import shutil
import subprocess


def test_ls_recursive_and_weird_names(tshd_daemon):
    """Test directory listing across deep nesting, long names, and special characters."""
    config = tshd_daemon
    base_dir = "/var/tmp/tsh_ls_test"

    # Define paths with weird characters and long names
    weird_name = "weird_chars_!@#$%^&()_+ -="
    long_name = "L" * 100
    nested_path = os.path.join(base_dir, weird_name, long_name, "depth")

    # 1. Create the directories locally
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
    os.makedirs(nested_path)

    try:
        # 2. Test LS at base
        res = subprocess.run(
            [config["tsh_path"], "-s", config["secret"], "localhost", "ls", base_dir],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0
        assert weird_name in res.stdout

        # 3. Test LS at weird_name level
        target = os.path.join(base_dir, weird_name)
        res = subprocess.run(
            [config["tsh_path"], "-s", config["secret"], "localhost", "ls", target],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0
        assert long_name in res.stdout

        # 4. Test LS at long_name level
        target = os.path.join(base_dir, weird_name, long_name)
        res = subprocess.run(
            [config["tsh_path"], "-s", config["secret"], "localhost", "ls", target],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0
        assert "depth" in res.stdout

    finally:
        # 5. Cleanup
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir)
