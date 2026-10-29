"""Tests for translation_status.py. Run: python3 -m unittest discover .github/scripts"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))

import translation_status as ts  # noqa: E402

EN = """- id: title
  translation: "Overlay Fact Sheet"
- id: topic01
  translation: "What is an overlay?"
- id: topic01p01
  translation: "Overlays apply third-party code."
- id: topic02
  translation: "Privacy"
"""

# Behind by one key (topic02), and topic01 was copied in untranslated.
FR = """- id: title
  translation: "Fiche d'information"
- id: topic01
  translation: "What is an overlay?"
- id: topic01p01
  translation: "Les overlays appliquent du code tiers."
"""

# Carries a key that English dropped, plus a duplicate id.
DE = """- id: title
  translation: "Overlay-Faktenblatt"
- id: topic01
  translation: "Was ist ein Overlay?"
- id: topic01p01
  translation: "Overlays wenden Code von Dritten an."
- id: topic02
  translation: "Datenschutz"
- id: topic07p99
  translation: "Ein Schlussel, den es nicht mehr gibt"
- id: title
  translation: "Noch einmal"
"""

CONFIG = """[languages]
  [languages.en]
    [languages.en.params]
      languageName = 'english'
  [languages.fr]
    [languages.fr.params]
      languageName = 'francais'
  [languages.de]
    [languages.de.params]
      languageName = 'deutsch'
"""


class ParseEntries(unittest.TestCase):
    def test_keeps_file_order(self):
        pairs = ts.parse_entries(EN)
        self.assertEqual(
            [key for key, _ in pairs], ["title", "topic01", "topic01p01", "topic02"]
        )

    def test_reads_translation_text(self):
        self.assertEqual(dict(ts.parse_entries(EN))["topic01"], "What is an overlay?")

    def test_empty_file_is_no_entries(self):
        self.assertEqual(ts.parse_entries(""), [])

    def test_missing_translation_becomes_empty_string(self):
        self.assertEqual(ts.parse_entries("- id: lonely\n"), [("lonely", "")])

    def test_entry_without_id_is_an_error(self):
        with self.assertRaises(ValueError):
            ts.parse_entries('- translation: "no id here"\n')

    def test_mapping_instead_of_list_is_an_error(self):
        with self.assertRaises(ValueError):
            ts.parse_entries("title: Overlay Fact Sheet\n")


class DuplicateIds(unittest.TestCase):
    def test_none_in_a_clean_file(self):
        self.assertEqual(ts.duplicate_ids(ts.parse_entries(EN)), [])

    def test_reports_the_repeated_id(self):
        self.assertEqual(ts.duplicate_ids(ts.parse_entries(DE)), ["title"])


class LanguageNames(unittest.TestCase):
    def test_reads_display_names(self):
        names = ts.language_names(CONFIG)
        self.assertEqual(names["fr"], "francais")
        self.assertEqual(names["de"], "deutsch")

    def test_falls_back_to_the_code(self):
        names = ts.language_names("[languages]\n  [languages.sv]\n")
        self.assertEqual(names["sv"], "sv")


class Compare(unittest.TestCase):
    def setUp(self):
        self.english = ts.parse_entries(EN)

    def test_missing_key_is_listed(self):
        status = ts.compare(self.english, ts.parse_entries(FR))
        self.assertEqual(status["missing"], ["topic02"])

    def test_entry_identical_to_english_is_untranslated(self):
        status = ts.compare(self.english, ts.parse_entries(FR))
        self.assertEqual(status["untranslated"], ["topic01"])

    def test_untranslated_does_not_count_as_translated(self):
        status = ts.compare(self.english, ts.parse_entries(FR))
        # 4 English keys, one missing, one a copy of the English.
        self.assertEqual(status["total"], 4)
        self.assertEqual(status["translated"], 2)

    def test_key_not_in_english_is_unknown(self):
        status = ts.compare(self.english, ts.parse_entries(DE))
        self.assertEqual(status["unknown"], ["topic07p99"])

    def test_duplicate_is_carried_through(self):
        status = ts.compare(self.english, ts.parse_entries(DE))
        self.assertEqual(status["duplicates"], ["title"])

    def test_complete_translation_is_clean(self):
        status = ts.compare(self.english, self.english[:])
        self.assertEqual(status["missing"], [])
        self.assertEqual(status["unknown"], [])
        # Every entry equals the English, so all of them read as untranslated.
        self.assertEqual(len(status["untranslated"]), 4)

    def test_empty_translation_is_missing_not_untranslated(self):
        # Hugo renders the English for a blank entry, so it is not a translation.
        status = ts.compare(self.english, [("title", ""), ("topic01", "  ")])
        self.assertEqual(status["untranslated"], [])
        self.assertEqual(status["missing"], ["title", "topic01", "topic01p01", "topic02"])
        self.assertEqual(status["translated"], 0)

    def test_missing_keys_follow_english_order(self):
        english = ts.parse_entries(EN)
        status = ts.compare(english, [("topic01p01", "x")])
        self.assertEqual(status["missing"], ["title", "topic01", "topic02"])


class Collect(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for name, body in (("en", EN), ("fr", FR), ("de", DE)):
            path = os.path.join(self.dir.name, f"{name}.yml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)

    def test_english_is_not_compared_against_itself(self):
        _english, statuses = ts.collect(self.dir.name, CONFIG)
        self.assertEqual([code for code, _, _ in statuses], ["de", "fr"])

    def test_counts_english_keys(self):
        english, _statuses = ts.collect(self.dir.name, CONFIG)
        self.assertEqual(english["total"], 4)

    def test_uses_display_names_from_config(self):
        _english, statuses = ts.collect(self.dir.name, CONFIG)
        self.assertEqual(dict((c, n) for c, n, _ in statuses)["fr"], "francais")

    def test_without_config_the_code_is_the_name(self):
        _english, statuses = ts.collect(self.dir.name, None)
        self.assertEqual(dict((c, n) for c, n, _ in statuses)["fr"], "fr")


class Reports(unittest.TestCase):
    def setUp(self):
        english = ts.parse_entries(EN)
        self.english_status = {"total": 4, "duplicates": []}
        self.statuses = [
            ("de", "deutsch", ts.compare(english, ts.parse_entries(DE))),
            ("fr", "francais", ts.compare(english, ts.parse_entries(FR))),
        ]

    def test_text_names_the_missing_key(self):
        out = ts.report_text(self.english_status, self.statuses)
        self.assertIn("topic02", out)
        self.assertIn("fr", out)

    def test_text_flags_unknown_keys(self):
        out = ts.report_text(self.english_status, self.statuses)
        self.assertIn("UNKNOWN", out)
        self.assertIn("topic07p99", out)

    def test_markdown_has_a_table_row_per_language(self):
        out = ts.report_markdown(self.english_status, self.statuses)
        self.assertIn("| deutsch (`de`) |", out)
        self.assertIn("| francais (`fr`) |", out)

    def test_markdown_lists_keys_waiting_for_translation(self):
        out = ts.report_markdown(self.english_status, self.statuses)
        self.assertIn("Keys still waiting for a translation", out)
        self.assertIn("`topic02`", out)

    def test_markdown_reports_dead_keys(self):
        out = ts.report_markdown(self.english_status, self.statuses)
        self.assertIn("Keys that render nowhere", out)
        self.assertIn("`topic07p99`", out)

    def test_markdown_omits_empty_sections(self):
        clean = [("fr", "francais", ts.compare(ts.parse_entries(EN), ts.parse_entries(EN)))]
        out = ts.report_markdown(self.english_status, clean)
        self.assertNotIn("Keys still waiting", out)
        self.assertNotIn("Keys that render nowhere", out)

    def test_percentage_of_a_complete_translation_is_shown(self):
        english = ts.parse_entries(EN)
        translated = [(key, f"xx {key}") for key, _ in english]
        status = ts.compare(english, translated)
        self.assertEqual(ts._percent(status), 100)


class Defects(unittest.TestCase):
    def test_clean_repo_has_none(self):
        english = ts.parse_entries(EN)
        translated = [(key, f"xx {key}") for key, _ in english]
        found = ts.defects(
            {"total": 4, "duplicates": []}, [("fr", "francais", ts.compare(english, translated))]
        )
        self.assertEqual(found, [])

    def test_missing_keys_are_not_defects(self):
        english = ts.parse_entries(EN)
        found = ts.defects(
            {"total": 4, "duplicates": []},
            [("fr", "francais", ts.compare(english, ts.parse_entries(FR)))],
        )
        self.assertEqual(found, [])

    def test_unknown_and_duplicate_keys_are_defects(self):
        english = ts.parse_entries(EN)
        found = ts.defects(
            {"total": 4, "duplicates": []},
            [("de", "deutsch", ts.compare(english, ts.parse_entries(DE)))],
        )
        self.assertEqual(len(found), 2)
        self.assertTrue(any("topic07p99" in line for line in found))
        self.assertTrue(any("duplicate" in line for line in found))

    def test_duplicate_in_english_is_a_defect(self):
        found = ts.defects({"total": 4, "duplicates": ["title"]}, [])
        self.assertEqual(found, ["en.yml: duplicate id title"])


class Main(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _write(self, **files):
        for name, body in files.items():
            path = os.path.join(self.dir.name, f"{name.replace('_', '-')}.yml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ts.main(["--i18n-dir", self.dir.name, "--no-config", *args])
        return code, out.getvalue(), err.getvalue()

    def test_reporting_a_behind_translation_still_exits_zero(self):
        self._write(en=EN, fr=FR)
        code, out, _err = self._run()
        self.assertEqual(code, 0)
        self.assertIn("topic02", out)

    def test_check_passes_when_only_keys_are_missing(self):
        self._write(en=EN, fr=FR)
        code, _out, _err = self._run("--check")
        self.assertEqual(code, 0)

    def test_check_fails_on_an_unknown_key(self):
        self._write(en=EN, de=DE)
        code, _out, err = self._run("--check")
        self.assertEqual(code, 1)
        self.assertIn("topic07p99", err)

    def test_markdown_format_is_selectable(self):
        self._write(en=EN, fr=FR)
        _code, out, _err = self._run("--format", "markdown")
        self.assertIn("| Language |", out)


class RealRepository(unittest.TestCase):
    """The checked-in i18n files must satisfy --check."""

    def setUp(self):
        self.root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isdir(os.path.join(self.root, "i18n")):
            self.skipTest("not running inside the repository")

    def test_no_unknown_or_duplicate_keys(self):
        with open(os.path.join(self.root, "config.toml"), encoding="utf-8") as handle:
            config = handle.read()
        english_status, statuses = ts.collect(os.path.join(self.root, "i18n"), config)
        self.assertEqual(ts.defects(english_status, statuses), [])

    def test_every_configured_language_has_a_file(self):
        with open(os.path.join(self.root, "config.toml"), encoding="utf-8") as handle:
            config = handle.read()
        names = ts.language_names(config)
        _english, statuses = ts.collect(os.path.join(self.root, "i18n"), config)
        have = {code for code, _, _ in statuses} | {ts.SOURCE_LANGUAGE}
        self.assertEqual(set(names) - have, set())


if __name__ == "__main__":
    unittest.main()
