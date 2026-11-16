#!/usr/bin/env bash
# Assert that a Hugo build produced a non-empty page for every configured
# language. Hugo can exit 0 while producing an empty or partial site, so this
# runs after `hugo --gc --minify`, locally and in CI (main.yml, "Verify build
# output").
#
# Usage: scripts/verify-build.sh [site-root]
#   site-root defaults to the repository root; it must hold config.toml and
#   the public/ directory Hugo wrote.
#
# Exit status: 0 when every page exists, 1 otherwise. The ::error:: prefixes
# become annotations on GitHub and are plain text locally.
set -uo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$root" || exit 1

fail=0

if [ ! -s public/index.html ]; then
  echo "::error::public/index.html is missing or empty"
  fail=1
fi

langs="$(grep -oE '^[[:space:]]*\[languages\.[A-Za-z-]+\]' config.toml \
  | sed -E 's/.*\[languages\.(.*)\]/\1/')"

if [ -z "$langs" ]; then
  echo "::error file=config.toml::No [languages.*] entries found in config.toml"
  exit 1
fi

while read -r lang; do
  page="public/$lang/index.html"
  if [ -s "$page" ]; then
    echo "ok  $page ($(wc -c < "$page" | tr -d ' ') bytes)"
  else
    echo "::error file=config.toml::$page is missing or empty"
    fail=1
  fi
done <<< "$langs"

exit $fail
