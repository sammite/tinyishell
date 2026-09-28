#!/usr/bin/env python3
"""tsh_client.py - Standalone Python client and interactive REPL for Tiny SHell (tsh).

Provides both a direct CLI alternative to the C tsh binary and an interactive
shell tracking remote directory state, communicating via native PyNaCl PEL encryption.
"""

from __future__ import annotations

import argparse
import cmd
import os
import posixpath
import shlex
import sys

from tsh_pel import TshClient, TshResult

try:
    import readline  # pylint: disable=unused-import
except ImportError:
    pass

DEFAULT_KEY = os.environ.get("TSH_KEY", "./tsh_key")
DEFAULT_PORT = 1234
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
        host="localhost",
        keyfile=None,
        port=DEFAULT_PORT,
        initial_dir=DEFAULT_REMOTE_CWD,
        stdin=None,
        stdout=None,
        secret=None,
        **_kwargs,
    ):
        super().__init__(stdin=stdin, stdout=stdout)
        self.host = host
        self.keyfile = keyfile or secret or DEFAULT_KEY
        self.port = port

        self.remote_cwd = posixpath.normpath(initial_dir) if initial_dir else DEFAULT_REMOTE_CWD
        if not self.remote_cwd.startswith("/"):
            self.remote_cwd = "/" + self.remote_cwd
        self.last_exit_code = 0

        self.client = TshClient(
            host=self.host,
            port=self.port,
            keyfile=self.keyfile,
        )
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

    def run_tsh(self, *args, capture_output=True) -> TshResult:
        """Executes a command via native TshClient."""
        if not args:
            return TshResult(1, stderr="No command specified\n")

        action = args[0]
        action_args = args[1:]
        return self.client.execute(action, *action_args, capture_output=capture_output)

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

    def do_ps(self, _arg):
        """ps: List running processes on the remote target."""
        res = self.run_tsh("ps")
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        self.last_exit_code = res.returncode

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
            "Cryptographic engine: PyNaCl / Monocypher wire-compatible\n"
            "(c) 2017-2024 Loup Vaillant (2-Clause BSD)"
        )
        self.last_exit_code = 0

    def do_license(self, _arg):
        """license: Display license and third-party cryptographic attribution."""
        print(
            "Tiny SHell (EDS) - GPLv2\n"
            "Cryptographic engine: PyNaCl (Libsodium) / Monocypher wire-compatible\n"
            "See LICENSE.monocypher for server license terms."
        )
        self.last_exit_code = 0

    def emptyline(self):
        """Do nothing on empty line."""


def parse_args():
    """Parses command-line arguments for tsh_client."""
    parser = argparse.ArgumentParser(
        description="tsh_client - Standalone Python client and interactive REPL for Tiny SHell."
    )
    parser.add_argument(
        "host",
        nargs="?",
        default="localhost",
        help="Remote hostname or 'cb' for connect-back (default: localhost)",
    )
    parser.add_argument(
        "action",
        nargs="?",
        help="Single-shot action (ls, exec, get, put, ps)",
    )
    parser.add_argument(
        "action_args",
        nargs="*",
        help="Arguments for single-shot action",
    )
    parser.add_argument(
        "-k",
        "--key",
        default=DEFAULT_KEY,
        help="Path to Ed25519 private key seed file (defaults to TSH_KEY env var or './tsh_key')",
    )
    parser.add_argument(
        "-s",
        "--secret",
        dest="key",
        help="Deprecated alias for -k/--key",
    )
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument(
        "-d",
        "--dir",
        default=DEFAULT_REMOTE_CWD,
        help="Initial remote working directory",
    )
    parser.add_argument("-c", "--command", help="Execute single REPL command string and exit")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=(
            "tsh_client (EDS) - GPLv2\n"
            "Cryptographic engine: PyNaCl (Libsodium) / Monocypher wire-compatible"
        ),
    )
    args = parser.parse_args()

    # Normalize if user ran 'tsh_client.py ls /' without explicit host
    if args.host in ("ls", "exec", "get", "put", "ps") and not args.command:
        real_action = args.host
        real_action_args = ([args.action] if args.action else []) + args.action_args
        args.host = "localhost"
        args.action = real_action
        args.action_args = real_action_args

    return args


def main():
    """Main entry point for tsh_client."""
    args = parse_args()

    # Single-shot CLI mode matching tsh
    if args.action:
        client = TshClient(
            host=args.host,
            port=args.port,
            keyfile=args.key,
        )
        res = client.execute(args.action, *args.action_args, capture_output=False)
        sys.exit(res.returncode)

    # REPL mode
    repl = TshRepl(
        host=args.host,
        keyfile=args.key,
        port=args.port,
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
