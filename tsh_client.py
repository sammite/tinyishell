#!/usr/bin/env python3
"""tsh_client.py - Interactive Python REPL wrapper for Tiny SHell (tsh).

Tracks remote directory state and provides an interactive shell experience
without requiring any server-side modifications.
"""

import argparse
import cmd
import os
import posixpath
import shlex
import subprocess
import sys

try:
    import readline  # pylint: disable=unused-import
except ImportError:
    pass

DEFAULT_SECRET = os.environ.get("TSH_SECRET", "1234")
DEFAULT_PORT = 1234
DEFAULT_TSH_BIN = "./tsh"
DEFAULT_REMOTE_CWD = "/"


def safe_shlex_split(arg: str):
    """Safely splits a command argument string, catching unclosed quotes."""
    try:
        return shlex.split(arg)
    except ValueError as exc:
        print(f"Syntax error in arguments: {exc}")
        return None


class TshRepl(cmd.Cmd):
    """Interactive command-line shell tracking remote directory state for tsh."""

    intro = "Connected to Tiny SHell. Type 'help' or '?' to list commands.\n"

    def __init__(
        self,
        host,
        secret=DEFAULT_SECRET,
        port=DEFAULT_PORT,
        tsh_bin=DEFAULT_TSH_BIN,
        initial_dir=DEFAULT_REMOTE_CWD,
        stdin=None,
        stdout=None,
    ):
        super().__init__(stdin=stdin, stdout=stdout)
        self.host = host
        self.secret = secret
        self.port = port
        self.tsh_bin = tsh_bin
        self.remote_cwd = posixpath.normpath(initial_dir) if initial_dir else DEFAULT_REMOTE_CWD
        if not self.remote_cwd.startswith("/"):
            self.remote_cwd = "/" + self.remote_cwd
        self.last_exit_code = 0
        self.update_prompt()

    def update_prompt(self):
        """Updates the command line prompt string with current remote directory."""
        self.prompt = f"tsh [{self.host}:{self.remote_cwd}]$ "

    def resolve_remote_path(self, path: str) -> str:
        """Resolves relative or absolute remote path against current remote_cwd."""
        if not path:
            return self.remote_cwd
        if path.startswith("/"):
            resolved = posixpath.normpath(path)
        else:
            resolved = posixpath.normpath(posixpath.join(self.remote_cwd, path))
        return resolved

    def run_tsh(self, *args, capture_output=True) -> subprocess.CompletedProcess:
        """Executes a command via the tsh binary."""
        cmd_args = [
            self.tsh_bin,
            "-s",
            str(self.secret),
            "-p",
            str(self.port),
            self.host,
            *args,
        ]
        return subprocess.run(cmd_args, capture_output=capture_output, text=True, check=False)

    def check_dir_exists(self, remote_dir: str) -> bool:
        """Validates that a remote directory exists by performing an ls query."""
        res = self.run_tsh("ls", remote_dir)
        # Any valid directory listing will contain at least '.' and '..'
        return res.returncode == 0 and bool(res.stdout and res.stdout.strip())

    # Built-in REPL commands

    def do_pwd(self, _arg):
        """pwd: Display current remote working directory."""
        print(self.remote_cwd)
        self.last_exit_code = 0

    def do_cd(self, arg):
        """cd [dir]: Change remote working directory."""
        parts = safe_shlex_split(arg)
        if parts is None:
            self.last_exit_code = 1
            return

        target = parts[0] if parts else "/"
        resolved = self.resolve_remote_path(target)
        if self.check_dir_exists(resolved):
            self.remote_cwd = resolved
            self.update_prompt()
            self.last_exit_code = 0
        else:
            print(f"cd: {target}: No such directory")
            self.last_exit_code = 1

    def do_ls(self, arg):
        """ls [dir]: List contents of remote directory."""
        parts = safe_shlex_split(arg)
        if parts is None:
            self.last_exit_code = 1
            return

        target = parts[0] if parts else ""
        resolved = self.resolve_remote_path(target) if target else self.remote_cwd
        res = self.run_tsh("ls", resolved)
        if res.stdout:
            sys.stdout.write(res.stdout)
            self.last_exit_code = res.returncode
        elif res.returncode == 0:
            print(f"ls: cannot access '{target or resolved}': No such directory")
            self.last_exit_code = 1
        else:
            self.last_exit_code = res.returncode

        if res.returncode != 0 and res.stderr:
            sys.stderr.write(res.stderr)

    def do_get(self, arg):
        """get <remote_src> [local_dest]: Download remote file."""
        args = safe_shlex_split(arg)
        if args is None:
            self.last_exit_code = 1
            return
        if not args:
            print("Usage: get <remote_src> [local_dest]")
            self.last_exit_code = 1
            return

        remote_src = self.resolve_remote_path(args[0])
        local_dest = args[1] if len(args) > 1 else "."

        res = self.run_tsh("get", remote_src, local_dest)
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        self.last_exit_code = res.returncode

    def do_put(self, arg):
        """put <local_src> [remote_dest]: Upload local file."""
        args = safe_shlex_split(arg)
        if args is None:
            self.last_exit_code = 1
            return
        if not args:
            print("Usage: put <local_src> [remote_dest]")
            self.last_exit_code = 1
            return

        local_src = args[0]
        remote_dest = self.resolve_remote_path(args[1]) if len(args) > 1 else self.remote_cwd

        res = self.run_tsh("put", local_src, remote_dest)
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        self.last_exit_code = res.returncode

    def do_exec(self, arg):
        """exec <remote_cmd>: Execute binary remotely and return exit code."""
        cmd_str = arg.strip()
        if not cmd_str:
            print("Usage: exec <remote_cmd>")
            self.last_exit_code = 1
            return

        res = self.run_tsh("exec", cmd_str)
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        self.last_exit_code = res.returncode

    def do_lpwd(self, _arg):
        """lpwd: Display current local working directory."""
        print(os.getcwd())
        self.last_exit_code = 0

    def do_lcd(self, arg):
        """lcd [dir]: Change local working directory."""
        parts = safe_shlex_split(arg)
        if parts is None:
            self.last_exit_code = 1
            return

        target = parts[0] if parts else os.path.expanduser("~")
        try:
            os.chdir(target)
            print(f"Local directory: {os.getcwd()}")
            self.last_exit_code = 0
        except OSError as exc:
            print(f"lcd: {exc}")
            self.last_exit_code = 1

    def do_lls(self, arg):
        """lls [dir]: List contents of local directory."""
        parts = safe_shlex_split(arg)
        if parts is None:
            self.last_exit_code = 1
            return

        target = parts[0] if parts else "."
        try:
            for item in os.listdir(target):
                print(item)
            self.last_exit_code = 0
        except OSError as exc:
            print(f"lls: {exc}")
            self.last_exit_code = 1

    def do_exit(self, _arg):
        """exit: Exit the interactive shell."""
        return True

    def do_quit(self, _arg):
        """quit: Exit the interactive shell."""
        return True

    def do_EOF(self, _arg):
        """Handle EOF (Ctrl+D) cleanly."""
        print()
        return True

    def do_version(self, _arg):
        """version: Display client version and cryptographic attribution."""
        print(
            "tsh_client (EDS) - GPLv2\n"
            "Cryptographic engine: Monocypher (c) 2017-2024 Loup Vaillant (2-Clause BSD)"
        )
        self.last_exit_code = 0

    def do_license(self, _arg):
        """license: Display license and third-party cryptographic attribution."""
        print(
            "Tiny SHell (EDS) - GPLv2\n"
            "Cryptographic engine: Monocypher (c) 2017-2024 Loup Vaillant (2-Clause BSD)\n"
            "See LICENSE.monocypher for full license terms."
        )
        self.last_exit_code = 0

    def emptyline(self):
        """Do nothing on empty line."""


def parse_args():
    """Parses command-line arguments for tsh_client."""
    parser = argparse.ArgumentParser(
        description="tsh_client - Interactive Python wrapper for Tiny SHell."
    )
    parser.add_argument(
        "host", nargs="?", default="localhost", help="Remote hostname or 'cb' for connect-back"
    )
    parser.add_argument(
        "-s",
        "--secret",
        default=DEFAULT_SECRET,
        help="Secret authentication key (defaults to TSH_SECRET env var or '1234')",
    )
    parser.add_argument(
        "-k",
        "--key",
        help="Path to Ed25519 private key seed file",
    )
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument(
        "-d",
        "--dir",
        default=DEFAULT_REMOTE_CWD,
        help="Initial remote working directory",
    )
    parser.add_argument("--tsh-bin", default=DEFAULT_TSH_BIN, help="Path to tsh binary")
    parser.add_argument("-c", "--command", help="Execute single command string and exit")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=(
            "tsh_client (EDS) - GPLv2\n"
            "Cryptographic engine: Monocypher (c) 2017-2024 Loup Vaillant (2-Clause BSD)"
        ),
    )
    args = parser.parse_args()
    if args.key:
        args.secret = args.key
    return args


def main():
    """Main entry point for tsh_client."""
    args = parse_args()
    repl = TshRepl(
        host=args.host,
        secret=args.secret,
        port=args.port,
        tsh_bin=args.tsh_bin,
        initial_dir=args.dir,
    )

    if args.command:
        repl.onecmd(args.command)
        sys.exit(repl.last_exit_code)
    else:
        try:
            repl.cmdloop()
            sys.exit(repl.last_exit_code)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)


if __name__ == "__main__":
    main()
