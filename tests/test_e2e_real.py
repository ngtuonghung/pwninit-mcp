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

import helpers

SYSTEM_LIBC = "/lib/x86_64-linux-gnu/libc.so.6"


@unittest.skipUnless(
    os.environ.get("PWNINIT_E2E_REAL") == "1",
    "set PWNINIT_E2E_REAL=1 to run the real-network end-to-end test",
)
@unittest.skipUnless(helpers.require_tool("gcc"), "gcc not available")
@unittest.skipUnless(os.path.isfile(SYSTEM_LIBC), "system libc not found")
class TestRealE2E(unittest.TestCase):
    """Full flow against real Ubuntu archives, including executing the
    patched binary with the fetched loader/libc pair."""

    def test_full_flow_and_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            binary = tmp / "hello"
            helpers.compile_binary(binary)
            shutil.copy2(SYSTEM_LIBC, tmp / "libc.so.6")

            proc = subprocess.run(
                [sys.executable, os.path.join(REPO, "src", "pwninit.py")],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=600,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            patched = tmp / "hello_patched"
            self.assertTrue(patched.is_file())
            self.assertTrue((tmp / "ld").is_symlink())
            self.assertTrue((tmp / "libc").is_symlink())

            # the patched binary must actually run with the fetched ld/libc
            run = subprocess.run(
                ["./hello_patched"], cwd=tmp, capture_output=True, text=True, timeout=30
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("hello", run.stdout)


if __name__ == "__main__":
    unittest.main()
