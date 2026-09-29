import sys
import unittest
from unittest import mock

sys.path.insert(0, "src")

import deb


class TestDebTimeout(unittest.TestCase):
    def test_download_timeout(self):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            raise TimeoutError("timed out")

        with mock.patch.object(deb.requests, "get", side_effect=fake_get):
            pkg = deb.DebPackage("http://example.invalid/x.deb")
        pkg.close()
        self.assertIsNone(pkg.tar)
        self.assertIn("timed out", pkg.error)
        self.assertEqual(calls[0].get("timeout"), (10, 30))


if __name__ == "__main__":
    unittest.main()
