"""Tests for release_notes.py. Run: python3 -m unittest discover .github/scripts"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import release_notes as rn  # noqa: E402

TEMPLATE = """<main>
  <h2 id="intro">{{ T "topic01" }}</h2>
  <h3 id="signed-by">{{ T "topic08p06" }}</h3>
  <ul><li>{{ T "topic08p09" }}</li></ul>
  <ol>
    <li>Ada Lovelace, self</li>
    <li>Grace Hopper, Rear Admiral,
      US Navy
    </li>
  </ol>
</main>
<aside class="further-reading">
  <h2 id="additional-reading">{{ T "topic09" }}</h2>
  <ul>
    <li>
      <a href="https://example.com/a">Overlays &amp; you</a>
      <span class="further-reading-source">Jane Doe</span>
    </li>
  </ul>
</aside>
"""

EN = """- id: topic01
  translation: "What is an overlay?"
- id: topic01p01
  translation: "Overlays are a <a href=\\"https://a.example\\">broad</a> term."
"""

CONFIG = """[languages.en]
  [languages.en.params]
    languageName = 'english'
[languages.fr]
  [languages.fr.params]
    languageName = 'français'
"""


def files(template=TEMPLATE, en=EN, **extra):
    out = {"layouts/index.html": template, "i18n/en.yml": en, "config.toml": CONFIG}
    out.update(extra)
    return out


class ParseTemplateTest(unittest.TestCase):
    def test_splits_lists_from_rest(self):
        parsed = rn.parse_template(TEMPLATE)
        self.assertEqual(
            parsed["signatories"], ["Ada Lovelace, self", "Grace Hopper, Rear Admiral, US Navy"]
        )
        self.assertEqual(parsed["reading"], ["Overlays & you — Jane Doe"])
        self.assertNotIn("Ada Lovelace", parsed["rest"])
        # The <ul> of topic08 bullets before the signatory <ol> is not the list.
        self.assertIn("topic08p09", parsed["rest"])

    def test_duplicate_entries_are_counted(self):
        self.assertEqual(rn.list_changes(["A", "B"], ["A", "B", "A"]), (["A"], []))
        self.assertEqual(rn.list_changes(["A", "A", "B"], ["A", "B"]), ([], ["A"]))

    def test_missing_file(self):
        self.assertEqual(rn.parse_template(None)["signatories"], [])


class PlainTextTest(unittest.TestCase):
    def test_strips_tags_without_orphaning_punctuation(self):
        self.assertEqual(rn.plain_text('like <a href="x">Browsealoud</a>.'), "like Browsealoud.")


class WordDiffTest(unittest.TestCase):
    def test_marks_removed_and_added_words(self):
        self.assertEqual(rn.word_diff("a big dog", "a small dog"), "a ~~big~~ **small** dog")

    def test_escapes_markdown(self):
        self.assertEqual(rn.word_diff("x", "*y*"), "~~x~~ **\\*y\\***")

    def test_diffs_unspaced_scripts_by_character(self):
        self.assertEqual(
            rn.word_diff("テキストの読み上げ機能", "テキストの音声読み上げ機能"),
            "テキストの **音声** 読み上げ機能",
        )

    def test_keeps_issue_references_linkable(self):
        self.assertEqual(rn.md_escape("Add name (#1337)"), "Add name (#1337)")


class BuildNotesTest(unittest.TestCase):
    def test_signature_only_change_is_not_substantive(self):
        head = TEMPLATE.replace("<li>Ada Lovelace, self</li>", "<li>Ada Lovelace, self</li>\n<li>Alan Turing, self</li>")
        substantive, notes = rn.build_notes(files(), files(template=head), [("abc123", "Add Alan Turing")])
        self.assertFalse(substantive)
        self.assertIn("1 added", notes)
        self.assertIn("Alan Turing, self", notes)

    def test_text_change_is_substantive_and_diffed(self):
        head_en = EN.replace("term.", "category.")
        substantive, notes = rn.build_notes(files(), files(en=head_en), [])
        self.assertTrue(substantive)
        self.assertIn("### Fact sheet text", notes)
        self.assertIn("`topic01p01` — What is an overlay?", notes)
        self.assertIn("~~term.~~ **category.**", notes)

    def test_link_only_change_says_so(self):
        head_en = EN.replace("https://a.example", "https://b.example")
        substantive, notes = rn.build_notes(files(), files(en=head_en), [])
        self.assertTrue(substantive)
        self.assertIn("links or formatting only", notes)

    def test_further_reading_change(self):
        head = TEMPLATE.replace(
            "</ul>\n</aside>",
            '<li><a href="https://b">New piece</a><span class="further-reading-source">Sam</span></li>\n</ul>\n</aside>',
        )
        substantive, notes = rn.build_notes(files(), files(template=head), [])
        self.assertTrue(substantive)
        self.assertIn("- Added: New piece — Sam", notes)
        self.assertNotIn("Page template", notes)

    def test_template_change_outside_lists(self):
        head = TEMPLATE.replace('id="intro"', 'id="introduction"')
        substantive, notes = rn.build_notes(files(), files(template=head), [])
        self.assertTrue(substantive)
        self.assertIn("Page template", notes)

    def test_new_translation_is_collapsed_with_language_name(self):
        substantive, notes = rn.build_notes(files(), files(**{"i18n/fr.yml": EN}), [])
        self.assertTrue(substantive)
        self.assertIn("<summary>français (fr)</summary>", notes)
        self.assertIn("New translation", notes)

    def test_no_changes(self):
        substantive, notes = rn.build_notes(files(), files(), [])
        self.assertFalse(substantive)
        self.assertEqual(notes, "No content changes.\n")

    def test_notes_are_capped(self):
        many = [(f"{i:07x}", "x" * 200) for i in range(1000)]
        _, notes = rn.build_notes(files(), files(), many, compare_url="https://example/compare")
        self.assertLessEqual(len(notes), rn.MAX_NOTES + 200)
        self.assertTrue(notes.rstrip().endswith("https://example/compare"))
        # The cut lands inside the collapsed commit list; it must be closed or
        # the diff link ends up hidden inside it.
        self.assertEqual(notes.count("<details>"), notes.count("</details>"))


class MainTest(unittest.TestCase):
    """Runs the script against a real git history, as the workflow does."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        self.git("init", "-q")
        os.makedirs("layouts")
        os.makedirs("i18n")
        self.write("layouts/index.html", TEMPLATE)
        self.write("i18n/en.yml", EN)
        self.write("config.toml", CONFIG)
        self.commit("initial")
        self.git("tag", "v2026.01.01")

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def git(self, *args):
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@example.com",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@example.com",
        )
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                       check=True, capture_output=True, env=env)

    def write(self, path, content):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def commit(self, message):
        self.git("add", "layouts/index.html", "i18n/en.yml", "config.toml")
        self.git("commit", "-q", "-m", message)

    def run_main(self):
        out = os.path.join(self._tmp.name, "gh-output")
        open(out, "w").close()
        os.environ["GITHUB_OUTPUT"] = out
        try:
            rn.main(["--base", "v2026.01.01", "--repo", "o/r", "--tag", "v2026.02.02",
                     "--output", "notes.md"])
        finally:
            del os.environ["GITHUB_OUTPUT"]
        with open(out, encoding="utf-8") as fh:
            flag = fh.read()
        with open("notes.md", encoding="utf-8") as fh:
            return flag, fh.read()

    def test_signatures_roll_into_the_next_text_release(self):
        self.write("layouts/index.html", TEMPLATE.replace("<li>Ada Lovelace, self</li>",
                                                          "<li>Ada Lovelace, self</li><li>Alan Turing, self</li>"))
        self.commit("Add Alan Turing")
        flag, _ = self.run_main()
        self.assertEqual(flag, "substantive=false\n")

        self.write("i18n/en.yml", EN.replace("term.", "category."))
        self.commit("Reword topic01p01")
        flag, notes = self.run_main()
        self.assertEqual(flag, "substantive=true\n")
        # Unchanged en.yml/config.toml context is loaded on both sides, so the
        # section heading resolves and English isn't reported as a new language.
        self.assertIn("#### english (en)", notes)
        self.assertIn("`topic01p01` — What is an overlay?", notes)
        self.assertNotIn("New translation", notes)
        # The signature from the earlier, unreleased push is still listed.
        self.assertIn("Alan Turing, self", notes)
        self.assertIn("Reword topic01p01", notes)
        self.assertIn("https://github.com/o/r/compare/v2026.01.01...v2026.02.02", notes)


if __name__ == "__main__":
    unittest.main()
