import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import helpers
from mcp_server import mcp


def run(coro):
    return asyncio.run(coro)


@unittest.skipUnless(helpers.require_tool("gcc"), "gcc not available")
@unittest.skipUnless(helpers.require_tool("ar"), "ar not available")
class TestMcpTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.chal = self.base / "chal"
        self.chal.mkdir()
        self.fake_home = self.base / "home"
        self.fake_home.mkdir()

        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.fake_home)

        self.ld_build = self.base / "ld-linux-x86-64.so.2"
        helpers.compile_shared_lib(self.ld_build)
        helpers.seed_deb_cache(self.fake_home, self.ld_build.read_bytes())

        self.libc = self.chal / "libc.so.6"
        helpers.compile_shared_lib(self.libc, extra_sources=helpers.UBUNTU_VERSION_LINE)
        self.binary = self.chal / "chall"
        helpers.compile_binary(self.binary)

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def call(self, tool, arguments):
        async def go():
            async with Client(mcp) as client:
                return await client.call_tool(tool, arguments)

        return run(go())

    def test_tools_listed(self):
        async def go():
            async with Client(mcp) as client:
                return {t.name for t in await client.list_tools()}

        self.assertEqual(run(go()), {"setup_challenge", "fetch_glibc_source"})

    def test_launcher_stdio_end_to_end(self):
        """The exact launch path Codex uses: spawn scripts/mcp_launch.sh over
        stdio, handshake, and call a tool for real."""
        async def go():
            transport = StdioTransport(
                "bash", [os.path.join(REPO, "scripts", "mcp_launch.sh")]
            )
            async with Client(transport) as client:
                names = {t.name for t in await client.list_tools()}
                result = await client.call_tool(
                    "setup_challenge",
                    {
                        "bin_path": str(self.binary),
                        "libc_path": str(self.libc),
                        "no_unstrip": True,
                    },
                )
            return names, result

        names, result = run(go())
        self.assertEqual(names, {"setup_challenge", "fetch_glibc_source"})
        data = getattr(result, "data", None) or result.structured_content
        self.assertTrue(data["success"], data["log"])
        self.assertIn("chall_patched", data["artifacts"])

    def test_setup_challenge_end_to_end(self):
        result = self.call(
            "setup_challenge",
            {
                "bin_path": str(self.binary),
                "libc_path": str(self.libc),
                "no_unstrip": True,
            },
        )
        data = getattr(result, "data", None) or result.structured_content
        self.assertTrue(data["success"], data["log"])
        self.assertIn("chall_patched", data["artifacts"])
        self.assertTrue((self.chal / "chall_patched").is_file())
        self.assertTrue((self.chal / "ld").is_symlink())
        self.assertTrue((self.chal / "libc").is_symlink())

    def test_setup_challenge_missing_binary(self):
        result = self.call("setup_challenge", {"bin_path": "/nonexistent/binary"})
        data = getattr(result, "data", None) or result.structured_content
        self.assertFalse(data["success"])
        self.assertIn("not found", data["log"])

    def test_fetch_source_missing_archive_fails_cleanly(self):
        result = self.call(
            "fetch_glibc_source",
            {
                "libc_path": str(self.libc),
                "source_archive": str(self.base / "no-such-archive.tar"),
            },
        )
        data = getattr(result, "data", None) or result.structured_content
        self.assertFalse(data["success"])
        self.assertIn("Can't open glibc-source", data["log"])


if __name__ == "__main__":
    unittest.main()
