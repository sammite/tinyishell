"""AddressSanitizer (ASan) memory safety integration tests for Tiny SHell."""

import os
import subprocess
import time

import pytest

ASAN_CFLAGS = "-fsanitize=address -g -O1 -fno-omit-frame-pointer"
ASAN_ENV = {
    **os.environ,
    "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1:halt_on_error=1",
}


@pytest.fixture(scope="module", autouse=True)
def check_asan_prerequisites(request):
    """Skip ASan tests when testing static musl build."""
    if request.config.getoption("--musl", default=False):
        pytest.skip("AddressSanitizer requires dynamic glibc build (not static musl)")


def test_asan_pel_unit():
    """Verify PEL cryptographic unit tests pass cleanly with AddressSanitizer."""
    build_cmd = [
        "gcc",
        "-fsanitize=address",
        "-g",
        "-O1",
        "-fno-omit-frame-pointer",
        "-Wall",
        "-Wextra",
        "-I.",
        "test/test_pel_unit.c",
        "pel.c",
        "monocypher.c",
        "monocypher-ed25519.c",
        "-o",
        "test/test_pel_unit_asan",
    ]
    compile_res = subprocess.run(build_cmd, capture_output=True, text=True, check=False)
    assert compile_res.returncode == 0, f"Compilation failed: {compile_res.stderr}"

    run_cmd = ["./test/test_pel_unit_asan"]
    res = subprocess.run(
        run_cmd,
        capture_output=True,
        text=True,
        check=False,
        env=ASAN_ENV,
    )

    try:
        assert res.returncode == 0, f"ASan test failed with code {res.returncode}:\n{res.stderr}"
        assert "All PEL C cryptographic unit tests passed successfully!" in res.stdout
    finally:
        subprocess.run(["rm", "-f", "test/test_pel_unit_asan"], check=False)


def test_asan_client_transactions(tmp_path):
    """Verify tsh client and daemon safety under AddressSanitizer during transactions."""
    cflags = f"{ASAN_CFLAGS} -Wall -Wextra -DSERVER_PORT=8767"
    build_client = f"gcc {cflags} -o tsh_asan pel.c monocypher.c monocypher-ed25519.c tsh.c"
    build_server = (
        f"gcc {cflags} -DLINUX -o tshd_asan pel.c monocypher.c monocypher-ed25519.c"
        " tshd.c -lutil"
    )

    subprocess.run(build_client, shell=True, check=True)
    subprocess.run(build_server, shell=True, check=True)

    server_log_prefix = str(tmp_path / "asan_server.log")
    server_env = {
        **os.environ,
        "ASAN_OPTIONS": (
            f"log_path={server_log_prefix}:detect_leaks=1:abort_on_error=1:halt_on_error=1"
        ),
    }

    test_file = tmp_path / "asan_payload.bin"
    test_data = os.urandom(32768)
    test_file.write_bytes(test_data)
    rx_dir = tmp_path / "rx"
    rx_dir.mkdir()

    with subprocess.Popen(["./tshd_asan", "-f"], env=server_env) as server_proc:
        time.sleep(0.5)
        try:
            # 1. tsh ls with ASan
            cmd_ls = ["./tsh_asan", "-p", "8767", "127.0.0.1", "ls", str(tmp_path)]
            res_ls = subprocess.run(
                cmd_ls, capture_output=True, text=True, check=False, env=ASAN_ENV
            )
            assert res_ls.returncode == 0, f"tsh ls failed:\n{res_ls.stderr}"

            # 2. tsh put with ASan
            cmd_put = [
                "./tsh_asan",
                "-p",
                "8767",
                "127.0.0.1",
                "put",
                str(test_file),
                str(rx_dir),
            ]
            res_put = subprocess.run(
                cmd_put, capture_output=True, text=True, check=False, env=ASAN_ENV
            )
            assert res_put.returncode == 0, f"tsh put failed:\n{res_put.stderr}"

            # 3. tsh get with ASan
            get_dest_dir = tmp_path / "get_rx"
            get_dest_dir.mkdir()
            remote_put_file = rx_dir / "asan_payload.bin"
            cmd_get = [
                "./tsh_asan",
                "-p",
                "8767",
                "127.0.0.1",
                "get",
                str(remote_put_file),
                str(get_dest_dir),
            ]
            res_get = subprocess.run(
                cmd_get, capture_output=True, text=True, check=False, env=ASAN_ENV
            )
            assert res_get.returncode == 0, f"tsh get failed:\n{res_get.stderr}"

            # Verify payload integrity
            retrieved_file = get_dest_dir / "asan_payload.bin"
            assert retrieved_file.read_bytes() == test_data

            # 4. tsh remote exec under ASan
            cmd_exec = [
                "./tsh_asan",
                "-p",
                "8767",
                "127.0.0.1",
                "exec",
                "/usr/bin/true",
            ]
            res_exec = subprocess.run(
                cmd_exec, capture_output=True, text=True, check=False, env=ASAN_ENV
            )
            assert res_exec.returncode == 0, f"tsh exec failed:\n{res_exec.stderr}"
            assert "Exit code: 0" in res_exec.stdout

        finally:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait()

            assert server_proc.returncode == 0, f"Server exited with {server_proc.returncode}"

            # Check that no ASan crash or leak reports were generated
            for log_file in tmp_path.glob("asan_server.log.*"):
                content = log_file.read_text()
                assert "ERROR: AddressSanitizer" not in content
                assert "ERROR: LeakSanitizer" not in content

            subprocess.run(["rm", "-f", "tsh_asan", "tshd_asan"], check=False)
