"""Valgrind memory leak and safety integration tests for Tiny SHell."""

import os
import shutil
import subprocess
import time

import pytest

VALGRIND_FLAGS = [
    "--leak-check=full",
    "--show-leak-kinds=all",
    "--track-origins=yes",
    "--error-exitcode=1",
    "--errors-for-leak-kinds=all",
    "--trace-children=yes",
]


def is_valgrind_available():
    """Check if valgrind is installed in PATH."""
    return shutil.which("valgrind") is not None


@pytest.fixture(scope="module", autouse=True)
def check_valgrind_prerequisites(request):
    """Skip Valgrind tests when testing static musl or when valgrind is missing."""
    if request.config.getoption("--musl", default=False):
        pytest.skip("Valgrind analysis requires dynamic glibc build (not static musl)")
    if not is_valgrind_available():
        pytest.skip("valgrind executable not found in PATH")


def test_valgrind_pel_unit():
    """Verify PEL cryptographic unit tests pass cleanly under Valgrind Memcheck."""
    build_cmd = [
        "gcc",
        "-O1",
        "-g",
        "-fno-inline",
        "-Wall",
        "-Wextra",
        "-fno-omit-frame-pointer",
        "-I.",
        "test/test_pel_unit.c",
        "pel.c",
        "monocypher.c",
        "monocypher-ed25519.c",
        "-o",
        "test/test_pel_unit",
    ]
    compile_res = subprocess.run(build_cmd, capture_output=True, text=True, check=False)
    assert compile_res.returncode == 0, f"Compilation failed: {compile_res.stderr}"

    valgrind_cmd = ["valgrind"] + VALGRIND_FLAGS + ["./test/test_pel_unit"]
    res = subprocess.run(valgrind_cmd, capture_output=True, text=True, check=False)

    try:
        assert (
            res.returncode == 0
        ), f"Valgrind failed with exit code {res.returncode}:\n{res.stderr}"
        assert "ERROR SUMMARY: 0 errors from 0 contexts" in res.stderr
        assert "All heap blocks were freed -- no leaks are possible" in res.stderr
    finally:
        subprocess.run(["rm", "-f", "test/test_pel_unit"], check=False)


def test_valgrind_client_transactions(tmp_path):
    """Verify both tsh client and daemon safety under Valgrind during transactions."""
    cflags = "-O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer -DSERVER_PORT=8765"
    build_client = f"gcc {cflags} -o tsh_valgrind pel.c monocypher.c monocypher-ed25519.c tsh.c"
    build_server = (
        f"gcc {cflags} -DLINUX -o tshd_valgrind pel.c monocypher.c monocypher-ed25519.c"
        " tshd.c -lutil"
    )

    subprocess.run(build_client, shell=True, check=True)
    subprocess.run(build_server, shell=True, check=True)

    server_log_prefix = str(tmp_path / "valgrind_server.log")
    server_cmd = (
        ["valgrind"]
        + VALGRIND_FLAGS
        + [f"--log-file={server_log_prefix}.%p", "./tshd_valgrind", "-f"]
    )

    test_file = tmp_path / "valgrind_payload.bin"
    test_data = os.urandom(16384)
    test_file.write_bytes(test_data)
    rx_dir = tmp_path / "rx"
    rx_dir.mkdir()

    with subprocess.Popen(server_cmd) as server_proc:
        time.sleep(0.6)
        try:
            # 1. tsh ls under Valgrind
            cmd_ls = (
                ["valgrind"]
                + VALGRIND_FLAGS
                + ["./tsh_valgrind", "-p", "8765", "127.0.0.1", "ls", str(tmp_path)]
            )
            res_ls = subprocess.run(cmd_ls, capture_output=True, text=True, check=False)
            assert res_ls.returncode == 0, f"tsh ls failed:\n{res_ls.stderr}"
            assert "ERROR SUMMARY: 0 errors from 0 contexts" in res_ls.stderr
            assert "All heap blocks were freed -- no leaks are possible" in res_ls.stderr

            # 2. tsh put under Valgrind
            cmd_put = (
                ["valgrind"]
                + VALGRIND_FLAGS
                + [
                    "./tsh_valgrind",
                    "-p",
                    "8765",
                    "127.0.0.1",
                    "put",
                    str(test_file),
                    str(rx_dir),
                ]
            )
            res_put = subprocess.run(cmd_put, capture_output=True, text=True, check=False)
            assert res_put.returncode == 0, f"tsh put failed:\n{res_put.stderr}"
            assert "ERROR SUMMARY: 0 errors from 0 contexts" in res_put.stderr
            assert "All heap blocks were freed -- no leaks are possible" in res_put.stderr

            # 3. tsh get under Valgrind
            get_dest_dir = tmp_path / "get_rx"
            get_dest_dir.mkdir()
            remote_put_file = rx_dir / "valgrind_payload.bin"
            cmd_get = (
                ["valgrind"]
                + VALGRIND_FLAGS
                + [
                    "./tsh_valgrind",
                    "-p",
                    "8765",
                    "127.0.0.1",
                    "get",
                    str(remote_put_file),
                    str(get_dest_dir),
                ]
            )
            res_get = subprocess.run(cmd_get, capture_output=True, text=True, check=False)
            assert res_get.returncode == 0, f"tsh get failed:\n{res_get.stderr}"
            assert "ERROR SUMMARY: 0 errors from 0 contexts" in res_get.stderr
            assert "All heap blocks were freed -- no leaks are possible" in res_get.stderr

            # Verify integrity of transfer
            retrieved_file = get_dest_dir / "valgrind_payload.bin"
            assert retrieved_file.read_bytes() == test_data

            # 4. tsh remote exec under Valgrind
            cmd_exec = (
                ["valgrind"]
                + VALGRIND_FLAGS
                + [
                    "./tsh_valgrind",
                    "-p",
                    "8765",
                    "127.0.0.1",
                    "exec",
                    "/usr/bin/true",
                ]
            )
            res_exec = subprocess.run(cmd_exec, capture_output=True, text=True, check=False)
            assert res_exec.returncode == 0, f"tsh exec failed:\n{res_exec.stderr}"
            assert "Exit code: 0" in res_exec.stdout
            assert "ERROR SUMMARY: 0 errors from 0 contexts" in res_exec.stderr
            assert "All heap blocks were freed -- no leaks are possible" in res_exec.stderr

        finally:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait()

            # Check server valgrind logs for parent and all forked children
            server_logs = list(tmp_path.glob("valgrind_server.log.*"))
            assert server_logs, "No Valgrind logs generated for server"
            for log_path in server_logs:
                log_text = log_path.read_text()
                assert "ERROR SUMMARY: 0 errors from 0 contexts" in log_text
                assert "All heap blocks were freed -- no leaks are possible" in log_text

            subprocess.run(["rm", "-f", "tsh_valgrind", "tshd_valgrind"], check=False)
