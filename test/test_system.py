"""End-to-end system test for nested Tiny SHell daemon deployment."""

import os
import shutil
import subprocess
import time


def build_custom_tsh(target, secret, port, cb_mode=False, cb_host=None):
    """Clean and build tsh/tshd with specific compile-time definitions."""
    subprocess.run(["make", "clean"], capture_output=True, check=False)

    cmd = ["make", target, f"SECRET_KEY={secret}", f"SERVER_PORT={port}"]
    if cb_mode:
        cmd.append("CB_MODE=1")
    if cb_host:
        cmd.append(f"CB_HOST={cb_host}")

    print(f"Building: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Build failed: {result.stderr}")

    suffix = "_cb" if cb_mode else "_primary"
    tsh_path = f"./tsh{suffix}"
    tshd_path = f"./tshd{suffix}"

    shutil.move("./tsh", tsh_path)
    shutil.move("./tshd", tshd_path)

    return os.path.abspath(tsh_path), os.path.abspath(tshd_path)


def test_system_nested_deployment(request):
    """Test nested deployment of connect-back daemon through primary daemon."""
    if request.config.getoption("--musl"):
        target = "linux_musl"
    elif request.config.getoption("--asan"):
        target = "linux_asan"
    elif request.config.getoption("--valgrind"):
        target = "linux_valgrind"
    else:
        target = "linux"

    secret = "system_test_password"
    primary_port = 1234
    nested_port = 5555

    primary_tsh, primary_tshd = build_custom_tsh(target, secret, primary_port)
    nested_tsh, nested_tshd = build_custom_tsh(
        target, secret, nested_port, cb_mode=True, cb_host="127.0.0.1"
    )

    subprocess.run(["pkill", "-f", "tshd_primary"], capture_output=True, check=False)
    subprocess.run(["pkill", "-f", "tshd_cb"], capture_output=True, check=False)

    with subprocess.Popen([primary_tshd]) as proc_primary:
        proc_primary.wait()
    time.sleep(1)

    res = subprocess.run(
        ["pgrep", "-f", "tshd_primary"], capture_output=True, text=True, check=False
    )
    print(f"DIAGNOSTIC: pgrep tshd_primary: '{res.stdout.strip()}'")

    remote_path = "/tmp/tshd_cb"
    if os.path.exists(remote_path):
        os.remove(remote_path)

    try:
        cmd_put = [
            primary_tsh,
            "-p",
            str(primary_port),
            "-s",
            secret,
            "127.0.0.1",
            "put",
            nested_tshd,
            "/tmp",
        ]
        res = subprocess.run(cmd_put, capture_output=True, text=True, check=False)
        assert (
            res.returncode == 0
        ), f"Failed to put nested binary (ret={res.returncode}): {res.stderr}"

        assert os.path.exists(remote_path), f"Remote binary {remote_path} not found"

        chmod_bin = shutil.which("chmod") or "/bin/chmod"
        cmd_chmod = [
            primary_tsh,
            "-p",
            str(primary_port),
            "-s",
            secret,
            "127.0.0.1",
            "exec",
            f"{chmod_bin} +x {remote_path}",
        ]
        res = subprocess.run(cmd_chmod, capture_output=True, text=True, check=False)
        assert res.returncode == 0, f"Failed to chmod: {res.stderr}"

        cmd_start = [
            primary_tsh,
            "-p",
            str(primary_port),
            "-s",
            secret,
            "127.0.0.1",
            "exec",
            remote_path,
        ]
        res = subprocess.run(cmd_start, capture_output=True, text=True, check=False)
        assert res.returncode == 0, f"Failed to start nested daemon: {res.stderr}"

        time.sleep(1)
        res = subprocess.run(
            ["pgrep", "-f", "tshd_cb"], capture_output=True, text=True, check=False
        )
        print(f"DIAGNOSTIC: pgrep tshd_cb: '{res.stdout.strip()}'")

        print("Waiting for connect-back (at least 5s)...")
        time.sleep(7)

        cmd_cb = [primary_tsh, "-p", str(nested_port), "-s", secret, "cb", "ls", "/"]
        res = subprocess.run(cmd_cb, capture_output=True, text=True, timeout=20, check=False)

        assert res.returncode == 0, f"Connect-back 'ls' failed: {res.stderr}"
        assert any(d in res.stdout for d in ("etc", "bin", "usr"))
        print("Nested deployment successful!")

    finally:
        subprocess.run(["pkill", "-f", "tshd_primary"], capture_output=True, check=False)
        subprocess.run(["pkill", "-f", "tshd_cb"], capture_output=True, check=False)
        if os.path.exists(remote_path):
            os.remove(remote_path)
        for binary in (primary_tsh, primary_tshd, nested_tsh, nested_tshd):
            if os.path.exists(binary):
                os.remove(binary)
