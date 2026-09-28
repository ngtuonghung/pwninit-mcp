---
name: pwninit
description: Set up CTF pwn challenges — fetch the matching glibc loader and libraries, unstrip libc for GDB, and patch a binary to run against its target libc. Use when a task involves a pwn binary plus libc, or fetching glibc source for debugging.
---

# pwninit

pwninit prepares a pwn challenge for exploitation and debugging: it downloads the dynamic loader and any extra shared libraries matching the challenge's libc, optionally unstrips libc (source-level GDB), and patches the binary to run against the target libc instead of the system one.

## MCP tools (preferred when available)

- `setup_challenge(bin_path, libc_path?, ld_path?, no_unstrip?, no_patch?, use_patchelf?, libs_dir?)` — full setup; returns `{"success", "artifacts", "log"}`.
- `fetch_glibc_source(libc_path, files?, source_archive?)` — fetch glibc source matching the libc and extract files (e.g. `["malloc.c"]`) next to the libc for GDB source stepping.

If these tools are not available, use the CLI below.

## CLI

One-time setup (installs system deps, creates `.venv`, registers the `pwninit` alias):

```bash
./setup.sh && source ~/.bashrc
```

Run inside the challenge directory that contains the binary and `libc.so.6`:

```bash
pwninit
```

Or point at files explicitly from anywhere:

```bash
pwninit --bin ./chall --libc ./libc.so.6
```

Useful flags: `--no-unstrip` (skip debug symbols), `--no-patch`, `--use-patchelf`, `-l <dir>` (store libs elsewhere), `-o <file>` (patched output path).

Source-level GDB (optional):

```bash
.venv/bin/python src/pwnsrc.py --files malloc.c
```

## Results and verification

All artifacts are written next to the binary, regardless of where you invoke the tool:

- `<bin>_patched` — the binary, patched to run with the challenge libc. Run it to verify: `./chall_patched`.
- `ld`, `libc` (and other libs) — relative symlinks to the fetched loader/libraries; keep them beside the binary.
- Unstripped `libc.so.6`/`ld` — with debug symbols when unstripping succeeded (better GDB output).

Exploit against the patched binary with pwntools: `process("./chall_patched")`.

## Notes

- pwninit does NOT generate an exploit script. Write `solve.py` yourself.
- If the challenge needs non-libc libraries (libcrypto, libseccomp, ...), pwninit resolves them automatically from their NEEDED entries.
