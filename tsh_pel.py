"""tsh_pel.py - Native Python Packet Encryption Layer (PEL) implementation for Tiny SHell.

Implements the PEL protocol using PyNaCl (X25519, Ed25519, ChaCha20-Poly1305, BLAKE2b),
matching the C implementation in pel.c and tshd.c.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import hashlib
import hmac
import os
import posixpath
import socket
import struct
import sys

import nacl.bindings as nb
import nacl.exceptions
import nacl.public
import nacl.signing

# Action codes (from tsh.h)
GET_FILE = 1
PUT_FILE = 2
LS_DIR = 4
EXEC_BIN = 5

BUFSIZE = 4096

# PEL protocol constants (from pel.h)
PEL_SUCCESS = 1
PEL_FAILURE = 0

PEL_SYSTEM_ERROR = -1
PEL_CONN_CLOSED = -2
PEL_WRONG_CHALLENGE = -3
PEL_BAD_MSG_LENGTH = -4
PEL_CORRUPTED_DATA = -5
PEL_UNDEFINED_ERROR = -6


class PelError(Exception):
    """Base exception for PEL protocol errors."""

    errno: int = PEL_UNDEFINED_ERROR


class PelConnClosedError(PelError):
    """Connection closed by remote peer."""

    errno: int = PEL_CONN_CLOSED


class PelWrongChallengeError(PelError):
    """Authentication challenge mismatch."""

    errno: int = PEL_WRONG_CHALLENGE


class PelBadMsgLengthError(PelError):
    """Invalid message length."""

    errno: int = PEL_BAD_MSG_LENGTH


class PelCorruptedDataError(PelError):
    """Ciphertext corrupted or Poly1305 MAC tag verification failed."""

    errno: int = PEL_CORRUPTED_DATA


class PelSystemError(PelError):
    """Underlying socket or I/O system error."""

    errno: int = PEL_SYSTEM_ERROR


def load_key_seed(key_source: str | bytes) -> nacl.signing.SigningKey:
    """Loads a 32-byte Ed25519 signing seed from a file path or raw bytes."""
    if isinstance(key_source, bytes):
        seed = key_source
    elif isinstance(key_source, str):
        if not os.path.exists(key_source):
            raise FileNotFoundError(f"{key_source}: No such file or directory")
        with open(key_source, "rb") as f:
            seed = f.read(32)
    else:
        seed = bytes(key_source)

    if len(seed) < 32:
        raise ValueError(f"{key_source}: Key file must be at least 32 bytes")

    return nacl.signing.SigningKey(seed[:32])


def recv_all(sock: socket.socket, length: int) -> bytes:
    """Reliably receives an exact number of bytes from the socket."""
    buf = bytearray()
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            if len(buf) == 0:
                raise PelConnClosedError("Connection closed by peer")
            raise PelSystemError("Unexpected EOF while reading socket")
        buf.extend(chunk)
    return bytes(buf)


class PelSession:
    """Encapsulates an authenticated and encrypted PEL communication session."""

    def __init__(self, sock: socket.socket, signing_key: nacl.signing.SigningKey):
        self.sock = sock
        self.signing_key = signing_key
        self.send_key: bytes = b""
        self.recv_key: bytes = b""
        self.send_nonce_base: bytes = b""
        self.recv_nonce_base: bytes = b""
        self.send_seq: int = 0
        self.recv_seq: int = 0

    def handshake(self) -> None:
        """Executes client-side PEL session handshake matching pel.c:pel_client_init."""
        # 1. Recv Msg 1 from Server: s_epk (32B) || n_s (16B) = 48B
        msg1 = recv_all(self.sock, 48)
        s_epk = msg1[:32]
        n_s = msg1[32:48]

        # 2. Ephemeral client keypair (c_esk, c_epk)
        c_esk = nacl.public.PrivateKey.generate()
        c_epk = bytes(c_esk.public_key)

        # 3. Construct transcript: s_epk (32) || c_epk (32) || n_s (16) = 80B
        transcript = s_epk + c_epk + n_s

        # 4. Sign transcript with developer Ed25519 key
        sig = self.signing_key.sign(transcript).signature

        # 5. Send Msg 2 to Server: c_epk (32B) || sig (64B) = 96B
        msg2 = c_epk + sig
        self.sock.sendall(msg2)

        # 6. Compute ECDH shared secret (X25519)
        k_shared = nb.crypto_scalarmult(bytes(c_esk), s_epk)

        # 7. Derive directional keys and nonce bases via keyed BLAKE2b
        self.send_key = hashlib.blake2b(b"c2s", key=k_shared, digest_size=32).digest()
        self.recv_key = hashlib.blake2b(b"s2c", key=k_shared, digest_size=32).digest()
        self.send_nonce_base = hashlib.blake2b(b"nc2s", key=k_shared, digest_size=16).digest()
        self.recv_nonce_base = hashlib.blake2b(b"ns2c", key=k_shared, digest_size=16).digest()
        self.send_seq = 0
        self.recv_seq = 0

        # 8. Recv Server Confirmation Msg 3 (16B)
        try:
            s_confirm = recv_all(self.sock, 16)
        except (PelConnClosedError, PelSystemError) as exc:
            raise PelWrongChallengeError(
                "Server closed connection during authentication challenge"
            ) from exc

        expected_confirm = hashlib.blake2b(b"server-ok", key=k_shared, digest_size=16).digest()
        if not hmac.compare_digest(s_confirm, expected_confirm):
            raise PelWrongChallengeError("Server confirmation verification failed")

    def send_msg(self, data: bytes) -> None:
        """Sends an authenticated and encrypted message using XChaCha20-Poly1305.

        Wire format:
        [0..1]  = 16-bit big-endian length L
        [2..17] = 16-byte Poly1305 MAC tag
        [18..]  = ciphertext (L bytes)
        """
        length = len(data)
        if length > BUFSIZE:
            raise PelBadMsgLengthError(f"Message length {length} exceeds maximum {BUFSIZE}")

        len_bytes = struct.pack(">H", length)
        seq_bytes = struct.pack(">Q", self.send_seq)
        nonce = self.send_nonce_base + seq_bytes
        ad = len_bytes + seq_bytes

        ct_and_mac = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(data, ad, nonce, self.send_key)
        ct = ct_and_mac[:-16]
        mac = ct_and_mac[-16:]
        self.send_seq += 1

        self.sock.sendall(len_bytes + mac + ct)

    def recv_msg(self) -> bytes | None:
        """Receives and decrypts an authenticated message.

        Returns None if remote peer has closed connection cleanly.
        """
        try:
            hdr = recv_all(self.sock, 2)
        except PelConnClosedError:
            return None

        length = struct.unpack(">H", hdr)[0]
        if length > BUFSIZE:
            raise PelBadMsgLengthError(
                f"Received message length {length} exceeds maximum {BUFSIZE}"
            )

        needed = 16 + length
        payload = recv_all(self.sock, needed)
        mac = payload[:16]
        ct = payload[16:]

        seq_bytes = struct.pack(">Q", self.recv_seq)
        nonce = self.recv_nonce_base + seq_bytes
        ad = hdr + seq_bytes

        try:
            plain = nb.crypto_aead_xchacha20poly1305_ietf_decrypt(
                ct + mac, ad, nonce, self.recv_key
            )
        except nacl.exceptions.CryptoError as exc:
            raise PelCorruptedDataError(
                "Decryption failed: corrupted data or MAC mismatch"
            ) from exc

        self.recv_seq += 1
        return plain

    def close(self) -> None:
        """Closes the underlying socket."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


@dataclasses.dataclass
class TshResult:
    """Result of a tsh command invocation."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class TshClient:
    """Complete Python client replacing tsh.c operations."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1234,
        keyfile: str | bytes = "./tsh_key",
    ):
        self.host = host
        self.port = port
        self.keyfile = keyfile

    def _open_session(self) -> PelSession:
        """Connects and performs handshake with tshd using the private key seed."""
        signing_key = load_key_seed(self.keyfile)

        if self.host == "cb":
            sys.stderr.write("Waiting for the server to connect...")
            sys.stderr.flush()
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", self.port))
            listener.listen(5)
            sock, _ = listener.accept()
            listener.close()
            sys.stderr.write("connected.\n")
            sys.stderr.flush()
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))

        session = PelSession(sock, signing_key)
        try:
            session.handshake()
            return session
        except (PelWrongChallengeError, PelError):
            session.close()
            raise

    def run_ls(self, remote_dir: str, capture_output: bool = True) -> TshResult:
        """Performs remote directory listing (LS_DIR)."""
        session = self._open_session()
        try:
            session.send_msg(bytes([LS_DIR]))
            session.send_msg(remote_dir.encode("utf-8"))

            chunks: list[bytes] = []
            while True:
                chunk = session.recv_msg()
                if chunk is None:
                    break
                if capture_output:
                    chunks.append(chunk)
                else:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.flush()

            out_str = b"".join(chunks).decode("utf-8", errors="replace") if capture_output else ""
            return TshResult(0, stdout=out_str)
        finally:
            session.close()

    def run_exec(self, cmd_str: str, capture_output: bool = True) -> TshResult:
        """Executes a command on the remote server (EXEC_BIN)."""
        session = self._open_session()
        try:
            session.send_msg(bytes([EXEC_BIN]))
            session.send_msg(cmd_str.encode("utf-8"))

            res = session.recv_msg()
            if res is None or len(res) != 1:
                err_msg = "Unexpected response length from server.\n"
                if not capture_output:
                    sys.stderr.write(err_msg)
                return TshResult(39, stderr=err_msg)

            exit_code = int(res[0])
            out_str = f"Exit code: {exit_code}\n"
            if not capture_output:
                sys.stdout.write(out_str)
                sys.stdout.flush()
            return TshResult(exit_code, stdout=out_str)
        finally:
            session.close()

    def run_get(self, remote_src: str, local_dst: str, capture_output: bool = True) -> TshResult:
        """Downloads a remote file (GET_FILE)."""
        # Determine local pathname matching tsh.c tsh_get_file
        filename = posixpath.basename(remote_src.rstrip("/"))
        if os.path.isdir(local_dst):
            local_path = os.path.join(local_dst, filename)
        else:
            local_path = local_dst

        try:
            with open(local_path, "wb") as fd:
                session = self._open_session()
                try:
                    session.send_msg(bytes([GET_FILE]))
                    session.send_msg(remote_src.encode("utf-8"))

                    total = 0
                    while True:
                        chunk = session.recv_msg()
                        if chunk is None:
                            break
                        fd.write(chunk)
                        total += len(chunk)
                        if not capture_output:
                            sys.stdout.write(f"{total}\r")
                            sys.stdout.flush()

                    done_msg = f"{total} done.\n"
                    if not capture_output:
                        sys.stdout.write(done_msg)
                        sys.stdout.flush()
                    return TshResult(0, stdout=done_msg)
                finally:
                    session.close()
        except OSError as exc:
            err_msg = f"creat: {exc}\n"
            if not capture_output:
                sys.stderr.write(err_msg)
            return TshResult(14, stderr=err_msg)

    def read_file_bytes(self, remote_src: str) -> bytes | None:
        """Retrieves a remote file directly into memory as bytes.

        Returns None if connection fails or if remote file is inaccessible.
        """
        try:
            session = self._open_session()
        except Exception:
            return None

        try:
            session.send_msg(bytes([GET_FILE]))
            session.send_msg(remote_src.encode("utf-8"))

            buf = bytearray()
            while True:
                chunk = session.recv_msg()
                if chunk is None:
                    break
                buf.extend(chunk)
            return bytes(buf)
        except Exception:
            return None
        finally:
            session.close()

    def run_put(self, local_src: str, remote_dst: str, capture_output: bool = True) -> TshResult:
        """Uploads a local file to the remote server (PUT_FILE)."""
        filename = os.path.basename(local_src)
        if remote_dst.endswith("/"):
            remote_pathname = remote_dst + filename
        else:
            remote_pathname = remote_dst + "/" + filename

        try:
            with open(local_src, "rb") as fd:
                session = self._open_session()
                try:
                    session.send_msg(bytes([PUT_FILE]))
                    session.send_msg(remote_pathname.encode("utf-8"))

                    total = 0
                    while True:
                        chunk = fd.read(BUFSIZE)
                        if not chunk:
                            break
                        session.send_msg(chunk)
                        total += len(chunk)
                        if not capture_output:
                            sys.stdout.write(f"{total}\r")
                            sys.stdout.flush()

                    done_msg = f"{total} done.\n"
                    if not capture_output:
                        sys.stdout.write(done_msg)
                        sys.stdout.flush()
                    return TshResult(0, stdout=done_msg)
                finally:
                    session.close()
        except OSError as exc:
            err_msg = f"open: {exc}\n"
            if not capture_output:
                sys.stderr.write(err_msg)
            return TshResult(19, stderr=err_msg)

    def run_ps(self, capture_output: bool = True) -> TshResult:
        """Retrieves and displays running processes from remote /proc."""
        ls_res = self.run_ls("/proc", capture_output=True)
        if ls_res.returncode != 0 or not ls_res.stdout:
            err = "Error: /proc pseudo-filesystem not found or inaccessible on remote target\n"
            if not capture_output:
                sys.stderr.write(err)
            return TshResult(1, stderr=err)

        pids: list[tuple[int, int]] = []
        for line in ls_res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and parts[4].isdigit():
                pids.append((int(parts[4]), int(parts[1])))

        if not pids:
            err = "Error: No active processes found in /proc on remote target\n"
            if not capture_output:
                sys.stderr.write(err)
            return TshResult(1, stderr=err)

        def fetch_proc(pid: int, uid: int) -> dict | None:
            stat_bytes = self.read_file_bytes(f"/proc/{pid}/stat")
            if not stat_bytes:
                return None

            stat_str = stat_bytes.decode("utf-8", errors="replace").strip()
            l = stat_str.find("(")
            r = stat_str.rfind(")")
            if l == -1 or r == -1 or r < l:
                return None

            comm = stat_str[l + 1 : r]
            rest = stat_str[r + 1 :].strip().split()
            if len(rest) < 22:
                return None

            state = rest[0]
            ppid = rest[1]
            try:
                rss_pages = int(rest[21])
                rss_bytes = rss_pages * 4096
            except (ValueError, IndexError):
                rss_bytes = 0

            cmdline_bytes = self.read_file_bytes(f"/proc/{pid}/cmdline")
            if cmdline_bytes:
                cmd = (
                    cmdline_bytes.replace(b"\x00", b" ")
                    .decode("utf-8", errors="replace")
                    .strip()
                )
            else:
                cmd = ""

            if not cmd:
                cmd = f"[{comm}]"

            user_str = "root" if uid == 0 else str(uid)
            return {
                "pid": pid,
                "ppid": int(ppid),
                "user": user_str,
                "stat": state,
                "rss": rss_bytes,
                "cmd": cmd,
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_pid = {executor.submit(fetch_proc, pid, uid): pid for pid, uid in pids}
            procs = []
            for future in concurrent.futures.as_completed(future_to_pid):
                try:
                    res = future.result()
                    if res:
                        procs.append(res)
                except Exception:
                    pass

        procs.sort(key=lambda x: x["pid"])

        def format_rss(n_bytes: int) -> str:
            if n_bytes == 0:
                return "0B"
            if n_bytes < 1024 * 1024:
                return f"{n_bytes // 1024}K"
            return f"{n_bytes / (1024 * 1024):.1f}M"

        lines = [f"{'PID':>6} {'PPID':>6} {'USER':<8} {'STAT':<4} {'RSS':>8} {'COMMAND'}"]
        for p in procs:
            lines.append(
                f"{p['pid']:>6} {p['ppid']:>6} {p['user']:<8} {p['stat']:<4} {format_rss(p['rss']):>8} {p['cmd']}"
            )
        output_str = "\n".join(lines) + "\n"

        if not capture_output:
            sys.stdout.write(output_str)
            sys.stdout.flush()

        return TshResult(0, stdout=output_str)

    def execute(self, action: str, *args, capture_output: bool = True) -> TshResult:
        """Dispatches an action string (matching the CLI verbs)."""
        try:
            if action == "ls":
                target = args[0] if args else "/"
                return self.run_ls(target, capture_output=capture_output)
            if action == "exec":
                cmd_str = args[0] if args else ""
                return self.run_exec(cmd_str, capture_output=capture_output)
            if action == "get":
                remote_src = args[0]
                local_dst = args[1] if len(args) > 1 else "."
                return self.run_get(remote_src, local_dst, capture_output=capture_output)
            if action == "put":
                local_src = args[0]
                remote_dst = args[1] if len(args) > 1 else "."
                return self.run_put(local_src, remote_dst, capture_output=capture_output)
            if action == "ps":
                return self.run_ps(capture_output=capture_output)
            return TshResult(1, stderr=f"Unknown action: {action}\n")
        except (FileNotFoundError, ValueError) as exc:
            err = f"{exc}\n"
            if not capture_output:
                sys.stderr.write(err)
            return TshResult(1, stderr=err)
        except PelWrongChallengeError:
            err = "Authentication failed.\n"
            if not capture_output:
                sys.stderr.write(err)
            return TshResult(10, stderr=err)
        except (PelConnClosedError, socket.error) as exc:
            err = f"Connection error: {exc}\n"
            if not capture_output:
                sys.stderr.write(err)
            return TshResult(4, stderr=err)
        except PelError as exc:
            err = f"Protocol error: {exc}\n"
            if not capture_output:
                sys.stderr.write(err)
            return TshResult(11, stderr=err)
