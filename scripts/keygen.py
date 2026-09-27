#!/usr/bin/env python3
"""keygen.py - Generate Ed25519 keypairs for Tiny SHell (tsh).

Generates:
- <prefix> (32-byte private key seed, mode 0600)
- <prefix>.pub (32-byte public key, mode 0644)
- <prefix>_pubkey.h (C header array for compiling into tshd)
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import nacl.signing
except ImportError:
    print("Error: PyNaCl is required. Run: pip install pynacl", file=sys.stderr)
    sys.exit(1)


def generate_keypair(
    prefix: str = "tsh_key", header_path: str | None = None
) -> tuple[str, str, str | None]:
    """Generates an Ed25519 keypair and writes private, public, and header files."""
    seed = os.urandom(32)
    signing_key = nacl.signing.SigningKey(seed)
    verify_key = bytes(signing_key.verify_key)

    priv_path = prefix
    pub_path = f"{prefix}.pub"
    actual_header_path = header_path if header_path is not None else f"{prefix}_pubkey.h"

    # Write private key seed with restricted 0600 permissions
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(priv_path, flags, 0o600)
    with open(fd, "wb") as f:
        f.write(seed)

    # Write public key with standard 0644 permissions
    with open(pub_path, "wb") as f:
        f.write(verify_key)

    # Write C header
    if actual_header_path:
        c_bytes = ", ".join(f"0x{b:02x}" for b in verify_key)
        header_content = (
            "#ifndef _TSH_PUBKEY_H\n"
            "#define _TSH_PUBKEY_H\n\n"
            "#include <stdint.h>\n\n"
            "/* 32-byte Ed25519 public key */\n"
            f"static const uint8_t default_dev_pk[32] = {{\n    {c_bytes}\n}};\n\n"
            "#endif /* _TSH_PUBKEY_H */\n"
        )
        with open(actual_header_path, "w", encoding="utf-8") as f:
            f.write(header_content)

    return priv_path, pub_path, actual_header_path


def main():
    parser = argparse.ArgumentParser(description="Generate Ed25519 keypair for Tiny SHell")
    parser.add_argument(
        "-o",
        "--output",
        default="tsh_key",
        help="Output key prefix (default: tsh_key)",
    )
    parser.add_argument(
        "--header",
        default="tsh_pubkey.h",
        help="Output C header path (default: tsh_pubkey.h)",
    )
    args = parser.parse_args()

    priv, pub, hdr = generate_keypair(args.output, header_path=args.header)
    print(f"Generated private key: {priv}")
    print(f"Generated public key:  {pub}")
    if hdr:
        print(f"Generated C header:   {hdr}")


if __name__ == "__main__":
    main()
