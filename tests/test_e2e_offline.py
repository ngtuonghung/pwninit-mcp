import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from elftools.elf.elffile import ELFFile

import helpers


def get_interp_and_needed(path):
    with open(path, "rb") as f:
        elf = ELFFile(f)
        interp = None
        seg = elf.get_section_by_name(".interp")
        if seg is not None:
            # PT_INTERP is NUL-terminated; bytes after the first NUL are
            # leftover from the original (longer) path and ignored by the loader
            interp = seg.data().split(b"\x00")[0].decode()
        dynamic = elf.get_section_by_name(".dynamic")
        needed = [tag.needed for tag in dynamic.iter_tags() if tag.entry["d_tag"] == "DT_NEEDED"]
    return interp, needed


@unittest.skipUnless(helpers.require_tool("gcc"), "gcc not available")
@unittest.skipUnless(helpers.require_tool("ar"), "ar not available")
class TestOfflineE2E(unittest.TestCase):
    """End-to-end runs of src/pwninit.py against a seeded fake deb cache.
    No network access happens: the libc6 deb is pre-placed in a fake HOME."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.chal = self.base / "chal"
        self.chal.mkdir()
        self.fake_home = self.base / "home"
        self.fake_home.mkdir()

        # fake ld shipped inside the deb
        self.ld_build = self.base / "ld-linux-x86-64.so.2"
        helpers.compile_shared_lib(self.ld_build)
        helpers.seed_deb_cache(self.fake_home, self.ld_build.read_bytes())

        # fake libc carrying a parseable glibc version string
        self.libc = self.chal / "libc.so.6"
        helpers.compile_shared_lib(self.libc, extra_sources=helpers.UBUNTU_VERSION_LINE)

        # target binary
        self.binary = self.chal / "chall"
        helpers.compile_binary(self.binary)

    def tearDown(self):
        self.tmp.cleanup()

    def run_pwninit(self, cwd, args):
        env = {**os.environ, "HOME": str(self.fake_home)}
        return subprocess.run(
            [sys.executable, os.path.join(REPO, "src", "pwninit.py")] + args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def assert_patched(self):
        patched = self.chal / "chall_patched"
        self.assertTrue(patched.is_file(), "patched binary missing")
        interp, needed = get_interp_and_needed(patched)
        self.assertEqual(interp, "./ld")
        self.assertEqual(needed, ["./libc"])
        self.assertTrue((self.chal / helpers.LD_NAME).is_file(), "ld not fetched")
        ld_link = self.chal / "ld"
        libc_link = self.chal / "libc"
        self.assertTrue(ld_link.is_symlink() and libc_link.is_symlink(), "symlinks missing")
        # symlinks must be relative so the challenge dir stays relocatable
        self.assertFalse(os.readlink(ld_link).startswith("/"))
        self.assertFalse(os.readlink(libc_link).startswith("/"))
        return patched

    def test_run_from_chall_dir(self):
        proc = self.run_pwninit(self.chal, ["-nu"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_patched()
        # template generation was removed
        self.assertFalse((self.chal / "solve.py").exists())

    def test_run_from_other_cwd(self):
        """Regression: artifacts land in the binary's dir, not the caller's cwd."""
        caller = self.base / "caller"
        caller.mkdir()
        proc = self.run_pwninit(
            caller, ["-nu", "--bin", str(self.binary), "--libc", str(self.libc)]
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_patched()
        self.assertEqual(list(caller.iterdir()), [], "caller cwd polluted")

    def test_unstrip_step_is_non_fatal(self):
        """Our crafted libs have no .gnu_debuglink; unstrip must warn and continue."""
        proc = self.run_pwninit(self.chal, [])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_patched()

    def test_libs_dir(self):
        libs = "libs"
        proc = self.run_pwninit(self.chal, ["-nu", "-l", libs])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.chal / libs / helpers.LD_NAME).is_file(), "ld not moved into libs dir")
        ld_link = self.chal / "ld"
        self.assertTrue(ld_link.is_symlink())
        self.assertEqual(os.readlink(ld_link), os.path.join(libs, helpers.LD_NAME))

    def test_static_binary(self):
        static_bin = self.chal / "static_chall"
        helpers.compile_binary(static_bin, static=True)
        proc = self.run_pwninit(self.chal, ["--bin", str(static_bin)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("statically linked", proc.stdout)
        self.assertFalse((self.chal / "static_chall_patched").exists())


if __name__ == "__main__":
    unittest.main()
