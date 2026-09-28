---
name: pwninit
description: Set up CTF pwn challenges for exploitation and debugging. Given a binary and its libc, downloads the matching glibc loader and required libraries (including non-libc deps like libcrypto or libseccomp), unstrips libc for source-level GDB, and patches the binary to run against the target libc. Also fetches glibc source files such as malloc.c for GDB source stepping. Use when a task involves a pwn binary plus libc, preparing a challenge before writing an exploit, or debugging glibc internals.
---

# pwninit

pwninit prepares a pwn challenge for exploitation and debugging: it downloads the dynamic loader and any extra shared libraries matching the challenge's libc, optionally unstrips libc (source-level GDB), and patches the binary to run against the target libc instead of the system one.

## Tools

- `setup_challenge(bin_path, libc_path?, ld_path?, no_unstrip?, no_patch?, use_patchelf?, libs_dir?)`: full setup; returns `{"success", "artifacts", "log"}`.
- `fetch_glibc_source(libc_path, files?, source_archive?)`: fetch glibc source matching the libc and extract files (e.g. `["malloc.c"]`) next to the libc for GDB source stepping.

Everything bootstraps automatically on first launch (Python deps and system packages); agents just call the tools.

## Results and verification

All artifacts are written next to the binary, regardless of where you invoke the tool:

- `<bin>_patched`: the binary, patched to run with the challenge libc. Run it to verify: `./chall_patched`.
- `ld`, `libc` (and other libs): relative symlinks to the fetched loader/libraries; keep them beside the binary.
- Unstripped `libc.so.6`/`ld`: with debug symbols when unstripping succeeded (better GDB output).

Exploit against the patched binary with pwntools: `process("./chall_patched")`.

## Notes

- pwninit does NOT generate an exploit script. Write `solve.py` yourself.
- If the challenge needs non-libc libraries (libcrypto, libseccomp, ...), pwninit resolves them automatically from their NEEDED entries.
- If a tool fails with a message about missing system packages, relay the install command from the log to the user (one-time root setup), then retry.
