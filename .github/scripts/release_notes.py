#!/usr/bin/env python3
"""Build the changelog for a fact sheet release.

Compares two git refs and describes what a reader of the site would notice:
which translated passages changed (with a word-level diff), which further
reading entries came and went, and who signed or left the signatory list.

The notes are the changelog (#879). They are published as the GitHub release
body only -- never on the website itself.

A change is "substantive" when anything other than the signatory list changed.
Signature-only pushes don't cut a release, so watching releases doesn't turn
into a notification per signature; those signatures are rolled into the next
release's notes instead, because every release is diffed against the previous
release tag rather than against the previous push.

Usage:
    release_notes.py --base <ref> --head <ref> [--repo owner/name] [--tag vX]
                     [--output notes.md]

Prints "substantive=true|false" and writes the markdown notes to --output
(stdout when omitted). Needs PyYAML.
"""

import argparse
import difflib
import html
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict

import yaml

TEMPLATE = "layouts/index.html"
I18N_DIR = "i18n/"
# Everything that ends up on the published page. Anything else in the repo
# (README, workflows, tooling) is not a content change.
CONTENT_PATHS = ["i18n", "layouts", "static", "config.toml"]
# GitHub rejects release bodies over 125,000 characters.
MAX_NOTES = 120_000


# --------------------------------------------------------------------------
# Parsing


def plain_text(fragment):
    """Reduce an HTML fragment to the words a reader sees."""
    text = re.sub(r"<[^>]+>", " ", fragment or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Tags were replaced with spaces; don't leave one before punctuation.
    return re.sub(r" ([.,;:!?)])", r"\1", text)


def parse_translations(source):
    """Map translation id -> string for one i18n/*.yml file."""
    if source is None:
        return {}
    entries = yaml.safe_load(source) or []
    return {str(e["id"]): str(e.get("translation", "")) for e in entries}


def _list_after(source, anchor, tag):
    """Return (start, end) of the inner HTML of the first <tag> after anchor."""
    at = source.find(anchor)
    if at == -1:
        return None
    open_match = re.compile(rf"<{tag}\b[^>]*>").search(source, at)
    if not open_match:
        return None
    close = source.find(f"</{tag}>", open_match.end())
    if close == -1:
        return None
    return open_match.end(), close


def _item_text(item):
    """'Title — Source' for a further reading entry, plain text otherwise."""
    link = re.search(r"<a\b[^>]*>(.*?)</a>", item, flags=re.S)
    source = re.search(r'class="further-reading-source"[^>]*>(.*?)</span>', item, flags=re.S)
    if link and source:
        return f"{plain_text(link.group(1))} — {plain_text(source.group(1))}"
    return plain_text(item)


def _items(inner):
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", inner, flags=re.S)
    return [t for t in map(_item_text, items) if t]


def parse_template(source):
    """Split the page template into signatories, further reading, and the rest.

    'rest' is the template with both lists blanked out, so comparing it tells
    us whether anything besides those two lists changed.
    """
    if source is None:
        return {"signatories": [], "reading": [], "rest": ""}

    spans = {}
    sig = _list_after(source, 'id="signed-by"', "ol")
    if sig:
        spans["signatories"] = sig
    reading = _list_after(source, 'id="additional-reading"', "ul")
    if reading:
        spans["reading"] = reading

    result = {"signatories": [], "reading": []}
    rest = source
    # Blank from the end backwards so earlier offsets stay valid.
    for name, (start, end) in sorted(spans.items(), key=lambda s: -s[1][0]):
        result[name] = _items(source[start:end])
        rest = rest[:start] + "\n" + rest[end:]
    result["rest"] = rest
    return result


def language_names(config_source):
    """Map language code -> display label, from config.toml."""
    if not config_source:
        return {}
    try:
        config = tomllib.loads(config_source)
    except tomllib.TOMLDecodeError:
        return {}
    names = {}
    for code, lang in config.get("languages", {}).items():
        name = lang.get("params", {}).get("languageName", "")
        names[code] = f"{name} ({code})" if name and name != code else code
    return names


# --------------------------------------------------------------------------
# Diffing


def _missing_from(items, reference):
    """Entries of items not matched in reference, counting duplicates."""
    remaining = Counter(reference)
    missing = []
    for item in items:
        if remaining[item]:
            remaining[item] -= 1
        else:
            missing.append(item)
    return missing


def list_changes(before, after):
    """Entries added to / removed from a list, preserving order.

    Compared as multisets, so a second copy of an existing entry (someone
    signing twice) shows up as added rather than disappearing.
    """
    return _missing_from(after, before), _missing_from(before, after)


_SECTION_KEY = re.compile(r"(topic\d+)(.*)")


def _split_key(key):
    """'topic05p02' -> ('topic05', 'p02'); keys outside a section -> (None, key)."""
    match = _SECTION_KEY.fullmatch(key)
    return (match.group(1), match.group(2)) if match else (None, key)


def section_renames(moved):
    """Infer renumbered sections from passages that moved key unchanged.

    Returns {new section: old section}, e.g. {"topic06": "topic05"} when a new
    section was inserted before the privacy section.
    """
    votes = defaultdict(Counter)
    for old_key, new_key in moved:
        (old_section, old_rest), (new_section, new_rest) = _split_key(old_key), _split_key(new_key)
        if old_section and new_section and old_section != new_section and old_rest == new_rest:
            votes[new_section][old_section] += 1
    return {new: counts.most_common(1)[0][0] for new, counts in votes.items()}


def translation_changes(before, after):
    """Compare two translation maps.

    Returns (added, removed, changed, moved). changed and moved are lists of
    (old key, new key) pairs: changed passages have new wording, moved ones
    have identical wording under a new key. Without this, renumbering the
    sections would report every later passage as rewritten.
    """
    old = {k: v for k, v in before.items() if after.get(k) != v}
    new = {k: v for k, v in after.items() if before.get(k) != v}

    by_text = defaultdict(list)
    for key, text in old.items():
        by_text[text].append(key)
    moved = []
    for key, text in list(new.items()):
        if by_text[text]:
            old_key = by_text[text].pop(0)
            moved.append((old_key, key))
            del new[key], old[old_key]

    # A passage renumbered *and* reworded: pair it with its old key through
    # the section renumbering, falling back to the same key.
    renames = section_renames(moved)
    changed = []
    for key in list(new):
        section, rest = _split_key(key)
        candidates = ([renames[section] + rest] if section in renames else []) + [key]
        old_key = next((c for c in candidates if c in old), None)
        if old_key:
            changed.append((old_key, key))
            del new[key], old[old_key]
    return list(new), list(old), changed, moved


# "#" is left alone so "#1234" still autolinks to the pull request; every
# escaped string sits mid-line, where "#" can't start a heading.
_MD_SPECIAL = re.compile(r"([\\`*_~\[\]<>|])")


def md_escape(text):
    return _MD_SPECIAL.sub(r"\\\1", text)


# Scripts written without spaces between words (Japanese, Chinese). Each of
# these characters is its own diff token; otherwise a one-word edit in a
# Japanese passage would strike out and re-add the entire passage.
_CJK = "\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef"
_TOKEN = re.compile(rf"\s+|[{_CJK}]|[^\s{_CJK}]+")


def word_diff(old, new):
    """Render old -> new as markdown: ~~removed~~ and **added** words."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(md_escape("".join(a[i1:i2])))
            continue
        # Spaces around each marker keep the emphasis delimiters valid even
        # next to CJK punctuation; the collapse below removes any doubles.
        if op in ("delete", "replace") and "".join(a[i1:i2]).strip():
            out.append(f" ~~{md_escape(''.join(a[i1:i2]).strip())}~~ ")
        if op in ("insert", "replace") and "".join(b[j1:j2]).strip():
            out.append(f" **{md_escape(''.join(b[j1:j2]).strip())}** ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


# --------------------------------------------------------------------------
# Report


def section_of(key, english):
    """'topic03p02' -> the English heading of topic03, for orientation."""
    match = re.match(r"(topic\d+)", key)
    if match and match.group(1) in english and match.group(1) != key:
        return plain_text(english[match.group(1)])
    return None


def describe_key(key, english):
    section = section_of(key, english)
    return f"`{key}` — {md_escape(section)}" if section else f"`{key}`"


def _renumbered_lines(moved):
    """'topic05 → topic06 (4 passages)' lines for passages that only moved."""
    groups = Counter()
    lines = []
    for old_key, new_key in moved:
        (old_section, old_rest), (new_section, new_rest) = _split_key(old_key), _split_key(new_key)
        if old_section and new_section and old_rest == new_rest:
            groups[(old_section, new_section)] += 1
        else:
            lines.append(f"- `{new_key}` (was `{old_key}`; wording unchanged)")
    grouped = [
        f"`{old}` → `{new}` ({n} passage{'s' if n != 1 else ''})"
        for (old, new), n in sorted(groups.items())
    ]
    if grouped:
        lines.insert(0, "- Renumbered, wording unchanged: " + ", ".join(grouped))
    return lines


def key_renames(base_files, head_files):
    """Old section -> new section, as inferred from the English translation."""
    before = parse_translations(base_files.get(f"{I18N_DIR}en.yml"))
    after = parse_translations(head_files.get(f"{I18N_DIR}en.yml"))
    moved = translation_changes(before, after)[3]
    return {old: new for new, old in section_renames(moved).items()}


def text_section(base_files, head_files, names):
    """Markdown for translation changes, English first.

    Returns (blocks, reworded): reworded is False when the only differences
    are renumbered keys, which change nothing a reader sees.
    """
    english = parse_translations(head_files.get(f"{I18N_DIR}en.yml")) or parse_translations(
        base_files.get(f"{I18N_DIR}en.yml")
    )
    paths = sorted(
        {p for p in list(base_files) + list(head_files) if p.startswith(I18N_DIR) and p.endswith(".yml")},
        key=lambda p: (p != f"{I18N_DIR}en.yml", p),
    )
    blocks = []
    reworded = False
    for path in paths:
        code = path[len(I18N_DIR) : -len(".yml")]
        before = parse_translations(base_files.get(path))
        after = parse_translations(head_files.get(path))
        if before == after:
            continue
        added, removed, changed, moved = translation_changes(before, after)
        label = names.get(code, code)
        lines = []
        if path not in base_files:
            lines.append(f"New translation: **{md_escape(label)}**.")
        elif path not in head_files:
            lines.append(f"Translation removed: **{md_escape(label)}**.")
        else:
            for old_key, key in changed:
                was = f" (was `{old_key}`)" if old_key != key else ""
                old, new = plain_text(before[old_key]), plain_text(after[key])
                if old == new:
                    lines.append(f"- {describe_key(key, english)}{was} (links or formatting only; wording unchanged)")
                else:
                    lines.append(f"- {describe_key(key, english)}{was}  \n  {word_diff(old, new)}")
            for key in added:
                lines.append(f"- {describe_key(key, english)} (new)  \n  {md_escape(plain_text(after[key]))}")
            for key in removed:
                lines.append(f"- {describe_key(key, english)} (removed)")
            lines += _renumbered_lines(moved)
        if not lines:
            continue
        passages = len(added) + len(removed) + len(changed)
        reworded = reworded or passages > 0 or path not in base_files or path not in head_files
        body = "\n".join(lines)
        if code == "en":
            blocks.append(f"#### {md_escape(label)}\n\n{body}")
        else:
            if path not in base_files or path not in head_files:
                summary = md_escape(label)
            elif passages:
                summary = f"{md_escape(label)} — {passages} passage{'s' if passages != 1 else ''}"
            else:
                summary = f"{md_escape(label)} — renumbered only"
            blocks.append(f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>")
    return blocks, reworded


def build_notes(base_files, head_files, commits, *, compare_url=None):
    """Return (substantive, markdown) for the change from base to head.

    base_files / head_files map repo path -> file content (None or absent when
    the file doesn't exist at that ref). commits is a list of (sha, subject).
    """
    names = language_names(head_files.get("config.toml") or base_files.get("config.toml"))
    before_tpl = parse_template(base_files.get(TEMPLATE))
    after_tpl = parse_template(head_files.get(TEMPLATE))

    text_blocks, reworded = text_section(base_files, head_files, names)
    reading_added, reading_removed = list_changes(before_tpl["reading"], after_tpl["reading"])
    signed, unsigned = list_changes(before_tpl["signatories"], after_tpl["signatories"])
    # Renumbered sections rename the template's {{ T "topicNN…" }} references
    # too; apply the same renumbering to the old template before comparing.
    renames = key_renames(base_files, head_files)
    before_rest = re.sub(
        r'(T ")(topic\d+)', lambda m: m.group(1) + renames.get(m.group(2), m.group(2)), before_tpl["rest"]
    )
    template_changed = TEMPLATE in head_files and TEMPLATE in base_files and before_rest != after_tpl["rest"]

    other_files = sorted(
        p
        for p in set(base_files) | set(head_files)
        if p != TEMPLATE and not p.startswith(I18N_DIR) and base_files.get(p) != head_files.get(p)
    )

    substantive = bool(reworded or reading_added or reading_removed or template_changed or other_files)

    parts = []
    if text_blocks:
        parts.append("### Fact sheet text\n\n" + "\n\n".join(text_blocks))
    if reading_added or reading_removed:
        lines = [f"- Added: {md_escape(x)}" for x in reading_added]
        lines += [f"- Removed: {md_escape(x)}" for x in reading_removed]
        parts.append("### Further reading\n\n" + "\n".join(lines))
    if template_changed or other_files:
        lines = []
        if template_changed:
            lines.append("- Page template (`layouts/index.html`) outside the signatory and further reading lists")
        lines += [f"- `{p}`" for p in other_files]
        parts.append("### Page structure and assets\n\n" + "\n".join(lines))
    if signed or unsigned:
        counts = []
        if signed:
            counts.append(f"{len(signed)} added")
        if unsigned:
            counts.append(f"{len(unsigned)} removed")
        lines = [f"- Added: {md_escape(x)}" for x in signed]
        lines += [f"- Removed: {md_escape(x)}" for x in unsigned]
        parts.append(
            f"### Signatories\n\n{', '.join(counts)}.\n\n<details>\n<summary>Names</summary>\n\n"
            + "\n".join(lines)
            + "\n\n</details>"
        )
    if commits:
        lines = [f"- {md_escape(subject)} ({sha})" for sha, subject in commits]
        parts.append(
            f"### Commits\n\n<details>\n<summary>{len(commits)} commit{'s' if len(commits) != 1 else ''}</summary>\n\n"
            + "\n".join(lines)
            + "\n\n</details>"
        )
    if compare_url:
        parts.append(f"**Full diff:** {compare_url}")
    if not parts:
        parts.append("No content changes.")

    notes = "\n\n".join(parts) + "\n"
    if len(notes) > MAX_NOTES:
        cut = notes.rfind("\n", 0, MAX_NOTES)
        notes = notes[:cut]
        # Close any collapsed section the cut landed in, or the notice and
        # the diff link below would be hidden inside it.
        notes += "\n\n</details>" * (notes.count("<details>") - notes.count("</details>"))
        notes += "\n\n…notes truncated; see the full diff.\n"
        if compare_url:
            notes += f"\n**Full diff:** {compare_url}\n"
    return substantive, notes


# --------------------------------------------------------------------------
# Git


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def changed_paths(base, head):
    out = git("diff", "--name-only", "--no-renames", base, head, "--", *CONTENT_PATHS)
    return [p for p in out.splitlines() if p]


def file_at(ref, path):
    try:
        return git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


def load(ref, paths):
    return {p: c for p in paths if (c := file_at(ref, p)) is not None}


def content_commits(base, head):
    out = git("log", "--no-merges", "--reverse", "--format=%h%x09%s", f"{base}..{head}", "--", *CONTENT_PATHS)
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if "\t" in line]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="previous release (tag or sha)")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repo", help="owner/name, for the compare link")
    parser.add_argument("--tag", help="tag being released, for the compare link")
    parser.add_argument("--output", help="write notes here instead of stdout")
    args = parser.parse_args(argv)

    paths = changed_paths(args.base, args.head)
    # The template and config are needed for context (language names,
    # section headings) even when they didn't change.
    context = [TEMPLATE, "config.toml", f"{I18N_DIR}en.yml"]
    base_files = load(args.base, paths)
    head_files = load(args.head, paths)
    for path in context:
        if path not in paths:
            content = file_at(args.head, path)
            if content is not None:
                base_files[path] = head_files[path] = content

    compare_url = None
    if args.repo:
        compare_url = f"https://github.com/{args.repo}/compare/{args.base}...{args.tag or args.head}"

    substantive, notes = build_notes(
        base_files, head_files, content_commits(args.base, args.head), compare_url=compare_url
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(notes)
    else:
        sys.stdout.write(notes)

    flag = f"substantive={'true' if substantive else 'false'}"
    print(flag, file=sys.stderr if not args.output else sys.stdout)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(flag + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
