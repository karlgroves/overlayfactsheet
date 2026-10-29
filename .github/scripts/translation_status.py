#!/usr/bin/env python3
"""Report how far each translation has fallen behind the English text.

`i18n/en.yml` is the source of truth. Every other `i18n/*.yml` is measured
against it and described three ways (#1434):

* **missing** -- a key in English with no entry, or a blank one, in that
  language. Hugo falls back to English for these, so the page still renders;
  the reader just sees English in the middle of their own language.
* **untranslated** -- an entry whose text is byte-for-byte the English. Usually
  a placeholder that was copied in and never translated. A handful are
  legitimate (proper nouns, a list of country abbreviations), so this is
  reported, never failed on.
* **unknown** -- a key that no longer exists in English. These are the ones
  worth failing a build over: the key renders nowhere, so a renumbering that
  missed a file (as in #1441) leaves the real passage silently falling back to
  English while a dead key sits in the file looking fine.

Only the set of keys is compared. When the English text under an existing
key is reworded, every translation of it still counts as translated, so those
edits have to be listed by hand.

Telling translators "topic05p03 changed" is the whole point -- nobody should
have to re-read the page to find the edit -- so `--format markdown` prints a
table that can be pasted straight into an issue comment.

Usage:
    translation_status.py [--i18n-dir i18n] [--config config.toml]
                          [--format text|markdown] [--check]

`--check` exits 1 when any file has unknown or duplicate keys. Without it the
command only reports, and exits 0. Needs PyYAML.
"""

import argparse
import glob
import os
import sys
import tomllib
from collections import Counter

import yaml

SOURCE_LANGUAGE = "en"


# --------------------------------------------------------------------------
# Parsing


def parse_entries(source):
    """Return [(id, translation)] for one i18n/*.yml, in file order.

    Order is kept so the report lists keys the way the page reads rather than
    alphabetically, which would scatter topic05p01..p05 across the list.
    """
    entries = yaml.safe_load(source) or []
    if not isinstance(entries, list):
        raise ValueError("expected a list of entries")
    pairs = []
    for entry in entries:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ValueError(f"entry without an id: {entry!r}")
        pairs.append((str(entry["id"]), str(entry.get("translation", ""))))
    return pairs


def duplicate_ids(pairs):
    """Ids appearing more than once. Later entries win in Hugo, silently."""
    counts = Counter(key for key, _ in pairs)
    return sorted(key for key, n in counts.items() if n > 1)


def language_names(config_source):
    """Map language code -> display name from config.toml's [languages.*]."""
    config = tomllib.loads(config_source)
    names = {}
    for code, block in (config.get("languages") or {}).items():
        params = block.get("params") or {}
        names[code] = str(params.get("languageName", code))
    return names


# --------------------------------------------------------------------------
# Comparing


def compare(english, other):
    """Describe one language against the English entries.

    Both arguments are [(id, translation)] as returned by parse_entries.
    """
    english_text = dict(english)
    order = [key for key, _ in english]
    # A blank entry renders the English too (Hugo falls back on it), so it
    # counts as missing rather than as a translation.
    other_text = {key: text for key, text in other if text.strip()}

    missing = [key for key in order if key not in other_text]
    untranslated = [
        key
        for key in order
        if key in other_text and other_text[key].strip() == english_text[key].strip()
    ]
    # Unknown keys are reported in the order they appear in the translation,
    # which is where someone editing the file will look for them.
    unknown = [key for key, _ in other if key not in english_text]

    translated = len(order) - len(missing) - len(untranslated)
    return {
        "total": len(order),
        "translated": translated,
        "missing": missing,
        "untranslated": untranslated,
        "unknown": unknown,
        "duplicates": duplicate_ids(other),
    }


def collect(i18n_dir, config_source=None):
    """Compare every i18n/*.yml against English. Returns [(code, name, status)]."""
    english_path = os.path.join(i18n_dir, f"{SOURCE_LANGUAGE}.yml")
    with open(english_path, encoding="utf-8") as handle:
        english = parse_entries(handle.read())

    names = language_names(config_source) if config_source else {}
    statuses = []
    for path in sorted(glob.glob(os.path.join(i18n_dir, "*.yml"))):
        code = os.path.basename(path)[: -len(".yml")]
        if code == SOURCE_LANGUAGE:
            continue
        with open(path, encoding="utf-8") as handle:
            entries = parse_entries(handle.read())
        statuses.append((code, names.get(code, code), compare(english, entries)))

    english_status = {
        "total": len(english),
        "duplicates": duplicate_ids(english),
    }
    return english_status, statuses


# --------------------------------------------------------------------------
# Reporting


def _percent(status):
    if not status["total"]:
        return 100
    return round(100 * status["translated"] / status["total"])


def _keys(keys, limit=None):
    if not keys:
        return "--"
    shown = keys if limit is None or len(keys) <= limit else keys[:limit]
    text = ", ".join(f"`{key}`" for key in shown)
    if len(shown) < len(keys):
        text += f", and {len(keys) - len(shown)} more"
    return text


def report_text(english_status, statuses):
    lines = [f"English keys: {english_status['total']}"]
    if english_status["duplicates"]:
        lines.append(f"  DUPLICATE ids in en.yml: {', '.join(english_status['duplicates'])}")
    for code, name, status in statuses:
        lines.append(
            f"{code:<6} {_percent(status):>3}%  "
            f"translated={status['translated']:<4} "
            f"missing={len(status['missing']):<4} "
            f"untranslated={len(status['untranslated']):<4} "
            f"unknown={len(status['unknown'])}  ({name})"
        )
        if status["missing"]:
            lines.append(f"       missing: {', '.join(status['missing'])}")
        if status["untranslated"]:
            lines.append(f"       same as English: {', '.join(status['untranslated'])}")
        if status["unknown"]:
            lines.append(f"       UNKNOWN keys: {', '.join(status['unknown'])}")
        if status["duplicates"]:
            lines.append(f"       DUPLICATE ids: {', '.join(status['duplicates'])}")
    return "\n".join(lines) + "\n"


def report_markdown(english_status, statuses):
    lines = [
        f"`i18n/en.yml` has **{english_status['total']}** keys.",
        "",
        "| Language | Translated | Missing | Same as English | Unknown |",
        "|---|---:|---:|---:|---:|",
    ]
    for code, name, status in statuses:
        lines.append(
            f"| {name} (`{code}`) | {status['translated']}/{status['total']} "
            f"({_percent(status)}%) | {len(status['missing'])} | "
            f"{len(status['untranslated'])} | {len(status['unknown'])} |"
        )

    behind = [(code, name, s) for code, name, s in statuses if s["missing"]]
    if behind:
        lines += ["", "### Keys still waiting for a translation", ""]
        for code, name, status in behind:
            lines.append(f"- **{name}** (`{code}`): {_keys(status['missing'])}")

    copied = [(code, name, s) for code, name, s in statuses if s["untranslated"]]
    if copied:
        lines += [
            "",
            "### Entries identical to the English text",
            "",
            "Some of these are correct -- proper nouns and the list of country "
            "abbreviations read the same in several languages.",
            "",
        ]
        for code, name, status in copied:
            lines.append(f"- **{name}** (`{code}`): {_keys(status['untranslated'])}")

    broken = [
        (code, name, s) for code, name, s in statuses if s["unknown"] or s["duplicates"]
    ]
    if broken or english_status["duplicates"]:
        lines += ["", "### Keys that render nowhere", ""]
        if english_status["duplicates"]:
            lines.append(f"- **English** (`en`): duplicate ids {_keys(english_status['duplicates'])}")
        for code, name, status in broken:
            if status["unknown"]:
                lines.append(f"- **{name}** (`{code}`): not in English -- {_keys(status['unknown'])}")
            if status["duplicates"]:
                lines.append(f"- **{name}** (`{code}`): duplicate ids {_keys(status['duplicates'])}")

    return "\n".join(lines) + "\n"


def defects(english_status, statuses):
    """The findings --check fails on: keys that render nowhere."""
    found = []
    for key in english_status["duplicates"]:
        found.append(f"en.yml: duplicate id {key}")
    for code, _name, status in statuses:
        for key in status["unknown"]:
            found.append(f"{code}.yml: {key} is not a key in en.yml")
        for key in status["duplicates"]:
            found.append(f"{code}.yml: duplicate id {key}")
    return found


# --------------------------------------------------------------------------
# Entry point


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--i18n-dir", default="i18n")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="read language display names from this file; omit with --no-config",
    )
    parser.add_argument("--no-config", action="store_true")
    parser.add_argument("--format", choices=("text", "markdown"), default="text")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when a file has unknown or duplicate keys",
    )
    args = parser.parse_args(argv)

    config_source = None
    if not args.no_config and os.path.exists(args.config):
        with open(args.config, encoding="utf-8") as handle:
            config_source = handle.read()

    english_status, statuses = collect(args.i18n_dir, config_source)

    render = report_markdown if args.format == "markdown" else report_text
    sys.stdout.write(render(english_status, statuses))

    if args.check:
        found = defects(english_status, statuses)
        if found:
            sys.stderr.write("\n")
            for line in found:
                sys.stderr.write(f"error: {line}\n")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
