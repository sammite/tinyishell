"""UndefinedBehaviorSanitizer (UBSan) safety integration tests for Tiny SHell."""

import os
import subprocess
import time

import pytest

UBSAN_ENV = {
    **os.environ,
    "UBSAN_OPTIONS": "halt_on_error=1:abort_on_error=1:print_stacktrace=1",
}


@pytest.fixture(scope="module", autouse=True)
def check_ubsan_prerequisites(request):
    """Skip UBSan tests when testing static musl build."""
    if request.config.getoption("--musl", default=False):
        pytest.skip("UndefinedBehaviorSanitizer requires dynamic glibc build")


def test_ubsan_pel_unit():
    """Verify PEL cryptographic unit tests pass cleanly under UBSan."""
    build_mono = ["gcc", "-O2", "-c", "monocypher.c", "monocypher-ed25519.c"]
    build_cmd = [
        "gcc",
        "-fsanitize=undefined",
        "-g",
        "-O1",
        "-Wall",
        "-Wextra",
        "-I.",
        "test/test_pel_unit.c",
        "pel.c",
        "monocypher.o",
        "monocypher-ed25519.o",
        "-o",
        "test/test_pel_unit_ubsan",
    ]
    subprocess.run(build_mono, check=True)
    compile_res = subprocess.run(build_cmd, capture_output=True, text=True, check=False)
    assert compile_res.returncode == 0, f"Compilation failed: {compile_res.stderr}"

    run_cmd = ["./test/test_pel_unit_ubsan"]
    res = subprocess.run(
        run_cmd,
        capture_output=True,
        text=True,
        check=False,
        env=UBSAN_ENV,
    )

    try:
        assert res.returncode == 0, f"UBSan test failed with code {res.returncode}:\n{res.stderr}"
        assert "All PEL C cryptographic unit tests passed successfully!" in res.stdout
    finally:
        subprocess.run(
            ["rm", "-f", "test/test_pel_unit_ubsan", "monocypher.o", "monocypher-ed25519.o"],
            check=False,
        )


def test_ubsan_client_transactions(tmp_path):
    """Verify tsh client and daemon safety under UBSan during transactions."""
    build_mono = "gcc -O2 -c monocypher.c monocypher-ed25519.c"
    cflags = "-fsanitize=undefined -g -O1 -Wall -Wextra -DSERVER_PORT=8769"
    build_client = f"gcc {cflags} -o tsh_ubsan pel.c tsh.c monocypher.o monocypher-ed25519.o"
    build_server = (
        f"gcc {cflags} -DLINUX -o tshd_ubsan pel.c tshd.c monocypher.o monocypher-ed25519.o -lutil"
    )

    subprocess.run(build_mono, shell=True, check=True)
    subprocess.run(build_client, shell=True, check=True)
    subprocess.run(build_server, shell=True, check=True)

    test_file = tmp_path / "ubsan_payload.bin"
    test_data = os.urandom(16384)
    test_file.write_bytes(test_data)
    rx_dir = tmp_path / "rx"
    rx_dir.mkdir()

    with subprocess.Popen(["./tshd_ubsan", "-f"], env=UBSAN_ENV) as server_proc:
        time.sleep(0.5)
        try:
            # 1. tsh ls with UBSan
            cmd_ls = ["./tsh_ubsan", "-p", "8769", "127.0.0.1", "ls", str(tmp_path)]
            res_ls = subprocess.run(
                cmd_ls, capture_output=True, text=True, check=False, env=UBSAN_ENV
            )
            assert res_ls.returncode == 0, f"tsh ls failed:\n{res_ls.stderr}"

            # 2. tsh put with UBSan
            cmd_put = [
                "./tsh_ubsan",
                "-p",
                "8769",
                "127.0.0.1",
                "put",
                str(test_file),
                str(rx_dir),
            ]
            res_put = subprocess.run(
                cmd_put, capture_output=True, text=True, check=False, env=UBSAN_ENV
            )
            assert res_put.returncode == 0, f"tsh put failed:\n{res_put.stderr}"

            # 3. tsh get with UBSan
            get_dest_dir = tmp_path / "get_rx"
            get_dest_dir.mkdir()
            remote_put_file = rx_dir / "ubsan_payload.bin"
            cmd_get = [
                "./tsh_ubsan",
                "-p",
                "8769",
                "127.0.0.1",
                "get",
                str(remote_put_file),
                str(get_dest_dir),
            ]
            res_get = subprocess.run(
                cmd_get, capture_output=True, text=True, check=False, env=UBSAN_ENV
            )
            assert res_get.returncode == 0, f"tsh get failed:\n{res_get.stderr}"

            retrieved_file = get_dest_dir / "ubsan_payload.bin"
            assert retrieved_file.read_bytes() == test_data

            # 4. tsh remote exec with UBSan
            cmd_exec = [
                "./tsh_ubsan",
                "-p",
                "8769",
                "127.0.0.1",
                "exec",
                "/usr/bin/true",
            ]
            res_exec = subprocess.run(
                cmd_exec, capture_output=True, text=True, check=False, env=UBSAN_ENV
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

            subprocess.run(
                [
                    "rm",
                    "-f",
                    "tsh_ubsan",
                    "tshd_ubsan",
                    "monocypher.o",
                    "monocypher-ed25519.o",
                ],
                check=False,
            )
