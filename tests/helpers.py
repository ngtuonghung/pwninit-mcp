"""Hermetic test fixtures: crafted ELF libraries and a fake .deb built with ar.

Everything is generated in temp dirs at test time, so the repo ships no
binary fixtures.
"""
import shutil
import subprocess
import tarfile
import tempfile
import io
from pathlib import Path

UBUNTU_VERSION_LINE = (
    "GNU C Library (Ubuntu GLIBC 2.43-2ubuntu2.3) stable release version 2.43."
)
LIBC_DEB_NAME = "libc6_2.43-2ubuntu2.3_amd64.deb"
LD_NAME = "ld-linux-x86-64.so.2"
LD_ARCHIVE_PATH = "./usr/lib/x86_64-linux-gnu/" + LD_NAME


def require_tool(name):
    return shutil.which(name) is not None


def compile_shared_lib(out_path, extra_sources=""):
    """Build a minimal shared object. extra_sources is appended to the C
    source (e.g. a glibc version string constant)."""
    source = Path(out_path).with_suffix(".c")
    source.write_text(f"const char version[] = \"{extra_sources}\";\nint _unused;\n")
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-o", str(out_path), str(source)],
        check=True,
    )


def compile_binary(out_path, static=False):
    source = Path(out_path).with_suffix(".c")
    source.write_text('#include <stdio.h>\nint main(void){puts("hello");return 0;}\n')
    cmd = ["gcc", "-o", str(out_path), str(source)]
    if static:
        cmd.append("-static")
    subprocess.run(cmd, check=True)


def make_deb(out_path, members):
    """Build a minimal .deb with `ar`. members maps archive paths -> bytes."""
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "debian-binary").write_bytes(b"2.0\n")
        control = tmp / "control.tar.gz"
        with tarfile.open(control, "w:gz"):
            pass
        data = tmp / "data.tar.gz"
        with tarfile.open(data, "w:gz") as tar:
            for arcname, payload in members.items():
                info = tarfile.TarInfo(arcname)
                info.size = len(payload)
                info.mode = 0o755
                tar.addfile(info, io.BytesIO(payload))
        subprocess.run(
            ["ar", "rcs", str(out_path), "debian-binary", control.name, data.name],
            cwd=tmp,
            check=True,
        )
    return out_path


def seed_deb_cache(fake_home, ld_bytes):
    """Place a fake libc6 deb (containing only ld) in <fake_home>/.cache/pwninit
    so pwninit hits the cache and never touches the network."""
    cache_dir = Path(fake_home) / ".cache" / "pwninit"
    cache_dir.mkdir(parents=True)
    return make_deb(cache_dir / LIBC_DEB_NAME, {LD_ARCHIVE_PATH: ld_bytes})
