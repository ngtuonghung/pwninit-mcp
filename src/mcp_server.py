#!/usr/bin/python3
"""MCP server exposing pwninit as tools for Codex agents."""
import os
import subprocess
import sys

from fastmcp import FastMCP

SRC_DIR = os.path.dirname(os.path.abspath(__file__))

mcp = FastMCP("pwninit")


def _run_cli(script, args, cwd):
    proc = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, script)] + args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        text=True,
        timeout=600,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode == 0, proc.stdout.strip()


def _run_cli_safe(script, args, cwd):
    try:
        return _run_cli(script, args, cwd)
    except subprocess.TimeoutExpired:
        return False, f"timed out after 600s: {' '.join(args)}"


def _new_files(directory, before):
    try:
        return sorted(set(os.listdir(directory)) - before)
    except OSError:
        return []


@mcp.tool
def setup_challenge(
    bin_path: str,
    libc_path: str = "",
    ld_path: str = "",
    no_unstrip: bool = False,
    no_patch: bool = False,
    use_patchelf: bool = False,
    libs_dir: str = "",
) -> dict:
    """Set up a CTF pwn challenge: download the matching dynamic loader and
    required libraries, optionally unstrip libc for GDB, and patch the binary
    to run against the supplied libc. All artifacts (patched binary, symlinks,
    fetched libraries) are written next to bin_path.

    Args:
        bin_path: Path to the challenge binary.
        libc_path: Path to the target libc.so (optional; auto-detected in the
            binary's directory when empty).
        ld_path: Path to the target dynamic loader (optional).
        no_unstrip: Skip downloading debug symbols for libc.
        no_patch: Skip patching the binary.
        use_patchelf: Use patchelf instead of direct byte replacement.
        libs_dir: Directory to store resolved libraries in (optional).

    Returns:
        {"success": bool, "artifacts": [new file names], "log": str}
    """
    bin_path = os.path.abspath(bin_path)
    if not os.path.isfile(bin_path):
        return {"success": False, "artifacts": [], "log": f"binary not found: {bin_path}"}
    cwd = os.path.dirname(bin_path)
    before = set(os.listdir(cwd))
    args = ["--bin", bin_path]
    if libc_path:
        args += ["--libc", os.path.abspath(libc_path)]
    if ld_path:
        args += ["--ld", os.path.abspath(ld_path)]
    if no_unstrip:
        args.append("--no-unstrip")
    if no_patch:
        args.append("--no-patch")
    if use_patchelf:
        args.append("--use-patchelf")
    if libs_dir:
        args += ["--libs", os.path.abspath(libs_dir)]
    success, log = _run_cli_safe("pwninit.py", args, cwd)
    return {"success": success, "artifacts": _new_files(cwd, before), "log": log}


@mcp.tool
def fetch_glibc_source(
    libc_path: str,
    files: list[str] | None = None,
    source_archive: str = "",
) -> dict:
    """Download the glibc source archive matching the given libc and extract
    specific source files for source-level GDB debugging.

    Args:
        libc_path: Path to the challenge's libc.so — its version determines
            which glibc source archive to fetch.
        files: Source files to extract, e.g. ["malloc.c"] or
            ["glibc-2.31/malloc/malloc.c"]. When empty, only the archive is
            fetched.
        source_archive: Existing glibc-source .tar archive to extract from,
            skipping the download.

    Returns:
        {"success": bool, "artifacts": [new file names], "log": str}
    """
    libc_path = os.path.abspath(libc_path)
    if not os.path.isfile(libc_path):
        return {"success": False, "artifacts": [], "log": f"libc not found: {libc_path}"}
    cwd = os.path.dirname(libc_path)
    before = set(os.listdir(cwd))
    args = ["--libc", libc_path]
    if source_archive:
        args += ["--source", os.path.abspath(source_archive)]
    if files:
        args += ["--files"] + list(files)
    success, log = _run_cli_safe("pwnsrc.py", args, cwd)
    return {"success": success, "artifacts": _new_files(cwd, before), "log": log}


if __name__ == "__main__":
    mcp.run(show_banner=False)
