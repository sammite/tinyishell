"""test_client_repl.py - Tests for the tsh_client Python REPL wrapper."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tsh_client import TshRepl, safe_shlex_split  # pylint: disable=wrong-import-position


def test_safe_shlex_split():
    assert safe_shlex_split('foo "bar baz"') == ["foo", "bar baz"]
    assert safe_shlex_split('unclosed "quote') is None


def test_repl_path_resolution():
    repl = TshRepl(host="test_host", initial_dir="/")
    assert repl.remote_cwd == "/"
    assert repl.prompt == "tsh [test_host:/]$ "

    assert repl.resolve_remote_path("") == "/"
    assert repl.resolve_remote_path(".") == "/"
    assert repl.resolve_remote_path("var") == "/var"
    assert repl.resolve_remote_path("var/tmp") == "/var/tmp"
    assert repl.resolve_remote_path("/etc") == "/etc"
    assert repl.resolve_remote_path("/etc/../var/tmp") == "/var/tmp"

    repl.remote_cwd = "/var/tmp"
    repl.update_prompt()
    assert repl.prompt == "tsh [test_host:/var/tmp]$ "
    assert repl.resolve_remote_path(".") == "/var/tmp"
    assert repl.resolve_remote_path("..") == "/var"
    assert repl.resolve_remote_path("../../etc") == "/etc"
    assert repl.resolve_remote_path("../etc") == "/var/etc"
    assert repl.resolve_remote_path("subdir/file") == "/var/tmp/subdir/file"


def test_repl_cd_and_pwd(tshd_daemon):
    config = tshd_daemon
    repl = TshRepl(
        host="localhost",
        secret=config["secret"],
        port=config["port"],
        tsh_bin=config["tsh_path"],
        initial_dir="/",
    )

    # Initial directory
    assert repl.remote_cwd == "/"
    assert repl.prompt == "tsh [localhost:/]$ "

    # Change directory to /var/tmp with quotes
    repl.do_cd('"/var/tmp"')
    assert repl.remote_cwd == "/var/tmp"
    assert repl.prompt == "tsh [localhost:/var/tmp]$ "
    assert repl.last_exit_code == 0

    # Relative change directory to ..
    repl.do_cd("..")
    assert repl.remote_cwd == "/var"
    assert repl.prompt == "tsh [localhost:/var]$ "
    assert repl.last_exit_code == 0

    # Attempt to change to non-existent directory
    repl.do_cd("nonexistent_dir_random_12345")
    assert repl.remote_cwd == "/var"
    assert repl.prompt == "tsh [localhost:/var]$ "
    assert repl.last_exit_code == 1

    # Attempt to change with malformed quotes
    repl.do_cd('"unclosed')
    assert repl.last_exit_code == 1


def test_repl_ls_and_file_ops(tshd_daemon, tmp_path, capsys):
    config = tshd_daemon
    repl = TshRepl(
        host="localhost",
        secret=config["secret"],
        port=config["port"],
        tsh_bin=config["tsh_path"],
        initial_dir="/var/tmp",
    )

    # Create a local test file
    local_file = tmp_path / "repl_test.txt"
    test_content = "hello from tsh python repl\n"
    local_file.write_text(test_content)

    # Put file into remote_cwd (/var/tmp)
    repl.do_put(f'"{local_file}"')
    assert repl.last_exit_code == 0

    # List directory without arguments (should default to remote_cwd: /var/tmp)
    repl.do_ls("")
    captured = capsys.readouterr()
    assert "repl_test.txt" in captured.out
    assert repl.last_exit_code == 0

    # Get the file back into tmp_path
    dest_dir = tmp_path / "downloads"
    dest_dir.mkdir()
    repl.do_get(f'repl_test.txt "{dest_dir}"')
    assert repl.last_exit_code == 0

    downloaded = dest_dir / "repl_test.txt"
    assert downloaded.exists()
    assert downloaded.read_text() == test_content

    # Cleanup remote file via exec rm
    repl.do_exec("/bin/rm -f /var/tmp/repl_test.txt")
    assert repl.last_exit_code == 0


def test_repl_onecmd_flag(tshd_daemon):
    config = tshd_daemon
    # Success case
    res = subprocess.run(
        [
            "python3",
            "tsh_client.py",
            "-s",
            config["secret"],
            "-p",
            str(config["port"]),
            "--tsh-bin",
            config["tsh_path"],
            "-d",
            "/var/tmp",
            "-c",
            "pwd",
            "localhost",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0
    assert "/var/tmp" in res.stdout.strip()

    # Failure exit code propagation
    res_fail = subprocess.run(
        [
            "python3",
            "tsh_client.py",
            "-s",
            config["secret"],
            "-p",
            str(config["port"]),
            "--tsh-bin",
            config["tsh_path"],
            "-c",
            "cd /nonexistent_dir_random_9999",
            "localhost",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res_fail.returncode == 1


def test_repl_piped_interactive_session(tshd_daemon):
    config = tshd_daemon
    input_cmds = "pwd\ncd /var/tmp\npwd\ncd ..\npwd\nexit\n"
    res = subprocess.run(
        [
            "python3",
            "tsh_client.py",
            "-s",
            config["secret"],
            "-p",
            str(config["port"]),
            "--tsh-bin",
            config["tsh_path"],
            "localhost",
        ],
        input=input_cmds,
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0
    stdout = res.stdout
    assert "tsh [localhost:/]$ /" in stdout
    assert "tsh [localhost:/var/tmp]$ /var/tmp" in stdout
    assert "tsh [localhost:/var]$ /var" in stdout


def test_repl_local_dirs(tmp_path):
    repl = TshRepl(host="test_host", initial_dir="/")
    original_cwd = os.getcwd()
    try:
        repl.do_lcd(str(tmp_path))
        assert os.getcwd() == str(tmp_path)
        assert repl.last_exit_code == 0

        # Test lls
        repl.do_lls("")
        assert repl.last_exit_code == 0
    finally:
        os.chdir(original_cwd)


def test_repl_license_and_version(capsys):
    repl = TshRepl(host="test_host")
    repl.do_version("")
    out = capsys.readouterr().out
    assert "Monocypher" in out
    assert "2-Clause BSD" in out

    repl.do_license("")
    out_lic = capsys.readouterr().out
    assert "LICENSE.monocypher" in out_lic
