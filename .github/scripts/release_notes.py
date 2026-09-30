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


def list_changes(before, after):
    """Entries added to / removed from a list, preserving order."""
    before_set, after_set = set(before), set(after)
    added = [x for x in after if x not in before_set]
    removed = [x for x in before if x not in after_set]
    return added, removed


def translation_changes(before, after):
    added = [k for k in after if k not in before]
    removed = [k for k in before if k not in after]
    changed = [k for k in after if k in before and before[k] != after[k]]
    return added, removed, changed


# "#" is left alone so "#1234" still autolinks to the pull request; every
# escaped string sits mid-line, where "#" can't start a heading.
_MD_SPECIAL = re.compile(r"([\\`*_~\[\]<>|])")


def md_escape(text):
    return _MD_SPECIAL.sub(r"\\\1", text)


def word_diff(old, new):
    """Render old -> new as markdown: ~~removed~~ and **added** words."""
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(md_escape(" ".join(a[i1:i2])))
            continue
        if op in ("delete", "replace"):
            out.append(f"~~{md_escape(' '.join(a[i1:i2]))}~~")
        if op in ("insert", "replace"):
            out.append(f"**{md_escape(' '.join(b[j1:j2]))}**")
    return " ".join(out)


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


def text_section(base_files, head_files, names):
    """Markdown for translation changes, English first."""
    english = parse_translations(head_files.get(f"{I18N_DIR}en.yml")) or parse_translations(
        base_files.get(f"{I18N_DIR}en.yml")
    )
    paths = sorted(
        {p for p in list(base_files) + list(head_files) if p.startswith(I18N_DIR) and p.endswith(".yml")},
        key=lambda p: (p != f"{I18N_DIR}en.yml", p),
    )
    blocks = []
    for path in paths:
        code = path[len(I18N_DIR) : -len(".yml")]
        before = parse_translations(base_files.get(path))
        after = parse_translations(head_files.get(path))
        if before == after:
            continue
        added, removed, changed = translation_changes(before, after)
        label = names.get(code, code)
        lines = []
        if path not in base_files:
            lines.append(f"New translation: **{md_escape(label)}**.")
        elif path not in head_files:
            lines.append(f"Translation removed: **{md_escape(label)}**.")
        else:
            for key in changed:
                old, new = plain_text(before[key]), plain_text(after[key])
                if old == new:
                    lines.append(f"- {describe_key(key, english)} (links or formatting only; wording unchanged)")
                else:
                    lines.append(f"- {describe_key(key, english)}  \n  {word_diff(old, new)}")
            for key in added:
                lines.append(f"- {describe_key(key, english)} (new)  \n  {md_escape(plain_text(after[key]))}")
            for key in removed:
                lines.append(f"- {describe_key(key, english)} (removed)")
        if not lines:
            continue
        body = "\n".join(lines)
        if code == "en":
            blocks.append(f"#### {md_escape(label)}\n\n{body}")
        else:
            count = len(added) + len(removed) + len(changed)
            summary = f"{md_escape(label)} — {count} passage{'s' if count != 1 else ''}"
            if path not in base_files or path not in head_files:
                summary = md_escape(label)
            blocks.append(f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>")
    return blocks


def build_notes(base_files, head_files, commits, *, compare_url=None):
    """Return (substantive, markdown) for the change from base to head.

    base_files / head_files map repo path -> file content (None or absent when
    the file doesn't exist at that ref). commits is a list of (sha, subject).
    """
    names = language_names(head_files.get("config.toml") or base_files.get("config.toml"))
    before_tpl = parse_template(base_files.get(TEMPLATE))
    after_tpl = parse_template(head_files.get(TEMPLATE))

    text_blocks = text_section(base_files, head_files, names)
    reading_added, reading_removed = list_changes(before_tpl["reading"], after_tpl["reading"])
    signed, unsigned = list_changes(before_tpl["signatories"], after_tpl["signatories"])
    template_changed = TEMPLATE in head_files and TEMPLATE in base_files and before_tpl["rest"] != after_tpl["rest"]

    other_files = sorted(
        p
        for p in set(base_files) | set(head_files)
        if p != TEMPLATE and not p.startswith(I18N_DIR) and base_files.get(p) != head_files.get(p)
    )

    substantive = bool(text_blocks or reading_added or reading_removed or template_changed or other_files)

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
        notes = notes[:cut] + "\n\n…notes truncated; see the full diff.\n"
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
