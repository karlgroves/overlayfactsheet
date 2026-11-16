"""Tests for scripts/verify-build.sh. Run: python3 -m unittest discover .github/scripts"""

import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "verify-build.sh"
)

CONFIG = """baseURL = 'https://example.org/'
[languages]
  [languages.en]
    weight = 1
    [languages.en.params]
      languageName = 'english'
  [languages.pt-br]
    weight = 2
    [languages.pt-br.params]
      languageName = 'português'
"""


class VerifyBuildTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_script(self):
        return subprocess.run(
            ["bash", SCRIPT, self.root], capture_output=True, text=True, check=False
        )

    def build_all(self):
        self.write("config.toml", CONFIG)
        self.write("public/index.html", "<html></html>")
        self.write("public/en/index.html", "<html>en</html>")
        self.write("public/pt-br/index.html", "<html>pt</html>")

    def test_passes_when_every_language_has_a_page(self):
        self.build_all()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("ok  public/en/index.html", result.stdout)
        self.assertIn("ok  public/pt-br/index.html", result.stdout)

    def test_fails_on_a_missing_language_page(self):
        self.build_all()
        os.remove(os.path.join(self.root, "public/pt-br/index.html"))
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("public/pt-br/index.html is missing or empty", result.stdout)

    def test_fails_on_an_empty_language_page(self):
        self.build_all()
        self.write("public/en/index.html", "")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("public/en/index.html is missing or empty", result.stdout)

    def test_fails_on_a_missing_root_index(self):
        self.build_all()
        os.remove(os.path.join(self.root, "public/index.html"))
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("public/index.html is missing or empty", result.stdout)

    def test_fails_on_an_empty_root_index(self):
        self.build_all()
        self.write("public/index.html", "")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("public/index.html is missing or empty", result.stdout)

    def test_fails_when_config_lists_no_languages(self):
        self.build_all()
        self.write("config.toml", "baseURL = 'https://example.org/'\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("No [languages.*] entries found", result.stdout)


if __name__ == "__main__":
    unittest.main()
