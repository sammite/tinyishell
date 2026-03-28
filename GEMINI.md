# Tiny SHell (tsh) Embedded Debugging - Best Practices

This project repurposes `tsh` as a lightweight, secure remote shell and file transfer tool for resource-constrained embedded systems.

## Core Principles

-   **Secure by Default:** Use existing AES-CBC-128 and HMAC-SHA1 encryption for all communication.
-   **Direct Library Calls:** Implement operations like `ls`, `getfile`, and `putfile` as direct library calls within `tshd` to minimize reliance on external system commands.
-   **Minimal Dependencies:** Keep the codebase small and portable to various embedded targets.
-   **Quality of Life:** Simplify the build process via `Makefile` enhancements for easier cross-compilation.

## Development Workflow

1.  **Architecture First:** Define the high-level goal and documentation before making code changes.
2.  **Surgical Edits:** Apply targeted changes to achieve specific debugging features.
3.  **Cross-Platform Support:** Ensure the tool remains compatible with various embedded operating systems and architectures.
