import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import unittest

from pwninit import LibcVersion, get_lib_name, is_libc6_lib


class TestGetLibName(unittest.TestCase):
    def test_common_names(self):
        cases = {
            "libc.so.6": "libc",
            "libc-2.31.so": "libc",
            "libc_2.31.so": "libc",
            "ld-linux-x86-64.so.2": "ld",
            "ld-2.31.so": "ld",
            "ld": "ld",
            "libpthread.so.0": "libpthread",
            "libm.so.6": "libm",
            "libcrypto.so.1.1": "libcrypto",
            "libssl.so.3": "libssl",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(get_lib_name(filename), expected)

    def test_non_library(self):
        self.assertEqual(get_lib_name("chall"), "chall")

    def test_strict_rejects_non_libraries(self):
        self.assertIsNone(get_lib_name("chall", strict=True))
        self.assertIsNone(get_lib_name("careless_patched", strict=True))


class TestIsLibc6Lib(unittest.TestCase):
    def test_glibc_shipped(self):
        for name in ("libc", "ld", "libm", "libpthread", "libdl", "libresolv"):
            self.assertTrue(is_libc6_lib(name))

    def test_external(self):
        for name in ("libcrypto", "libssl", "libseccomp", "libcap", "libz"):
            self.assertFalse(is_libc6_lib(name))

    def test_nss(self):
        self.assertTrue(is_libc6_lib("libnss_files"))


UBUNTU_LINE = "(Ubuntu GLIBC 2.43-2ubuntu2.3) stable release version 2.43."
DEBIAN_LINE = "(Debian GLIBC 2.36-9) stable release version 2.36, by Aurelien Jarno et al."


class TestLibcVersion(unittest.TestCase):
    def test_ubuntu(self):
        v = LibcVersion(UBUNTU_LINE, "amd64")
        self.assertEqual(v.version, (2, 43))
        self.assertEqual(v.version_string, "2.43")
        self.assertEqual(v.os, "Ubuntu")
        self.assertTrue(v.is_stable)
        self.assertFalse(v.is_custom)
        self.assertEqual(v.pkgname, "2.43-2ubuntu2.3")
        self.assertEqual(v.libc_debname, "libc6_2.43-2ubuntu2.3_amd64.deb")
        self.assertEqual(v.libc_dbg_debname, "libc6-dbg_2.43-2ubuntu2.3_amd64.deb")
        self.assertEqual(v.libc_src_debname, "glibc-source_2.43-2ubuntu2.3_all.deb")
        self.assertIn("archive.ubuntu.com", v.base_pkgurl)

    def test_debian(self):
        v = LibcVersion(DEBIAN_LINE, "amd64")
        self.assertEqual(v.os, "Debian")
        self.assertIn("deb.debian.org", v.base_pkgurl)

    def test_custom_build(self):
        v = LibcVersion("(GNU libc) stable release version 2.42.", "amd64")
        self.assertTrue(v.is_custom)
        self.assertEqual(v.os, "GNU")
        self.assertIsNone(v.base_pkgurl)
        self.assertIsNone(v.libc_debname)

    def test_garbage(self):
        v = LibcVersion("not a version line", "amd64")
        self.assertIsNone(v.version)

    def test_libc6_pkg_paths(self):
        v = LibcVersion(UBUNTU_LINE, "amd64")
        paths = v.get_libc6_pkg_paths("ld-linux-x86-64.so.2")
        self.assertIn("./usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2", paths)
        self.assertEqual(paths[0], "./lib/x86_64-linux-gnu/ld-linux-x86-64.so.2")

    def test_supported_architectures(self):
        v = LibcVersion(UBUNTU_LINE, "amd64")
        self.assertIn("amd64", v.supported_architectures)
        self.assertNotIn("mipsel", v.supported_architectures)


if __name__ == "__main__":
    unittest.main()
