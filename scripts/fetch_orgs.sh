#!/bin/bash
# Shallow-clone EVERY repo (including forks and archived) of the given GitHub orgs into reference/<org>/<repo>.
# Skips repos already listed in reference/MANIFEST.tsv. Strips .git, appends to the manifest.
# Usage: scripts/fetch_orgs.sh OpenIPC OpenHD hd-zero svpcom RubyFPV open-sdr
set -u
DEST="${DEST:-$HOME/notadji/reference}"
MANIFEST="$DEST/MANIFEST.tsv"
MIN_FREE_GB=${MIN_FREE_GB:-25}
MAX_MB=${MAX_MB:-2000}   # skip repos whose full-history size exceeds this (override: MAX_MB=100000)
export GIT_TERMINAL_PROMPT=0 GIT_LFS_SKIP_SMUDGE=1 DEST MANIFEST MIN_FREE_GB MAX_MB
SKIPPED="$DEST/SKIPPED_LARGE.tsv"; export SKIPPED
[ -s "$MANIFEST" ] || printf 'repo\tpath\tcommit\tlicense_file\n' > "$MANIFEST"

clone_one() {
  repo="${1%% *}"; mb="${1##* }"; org="${repo%%/*}"; name="${repo#*/}"
  grep -q -P "^\Q$repo\E\t" "$SKIPPED" 2>/dev/null && { echo "skip-large $repo"; return; }
  if [ "$mb" -gt "$MAX_MB" ]; then printf '%s\t%s\tover MAX_MB=%s\n' "$repo" "$mb" "$MAX_MB" >> "$SKIPPED"; echo "skip-large $repo ${mb}MB"; return; fi
  grep -q -P "^\Q$repo\E\t" "$MANIFEST" && { echo "skip  $repo"; return; }
  free=$(df --output=avail -BG "$DEST" | tail -1 | tr -dc 0-9)
  [ "$free" -lt "$MIN_FREE_GB" ] && { echo "STOP  $repo (free ${free}G < ${MIN_FREE_GB}G)"; return; }
  group=$(echo "$org" | tr 'A-Z' 'a-z'); target="$DEST/$group/$name"
  [ -d "$target" ] && { echo "exists $repo"; return; }
  mkdir -p "$DEST/$group"
  if timeout 900 git clone --depth 1 --quiet "https://github.com/$repo.git" "$target" 2>"$target.err"; then
    sha=$(git -C "$target" rev-parse HEAD 2>/dev/null)
    lic=$(ls "$target" | grep -iE '^(license|copying)' | head -1)
    printf '%s\t%s\t%s\t%s\n' "$repo" "$group/$name" "$sha" "${lic:-NO_LICENSE_FILE}" >> "$MANIFEST"
    rm -rf "$target/.git" "$target.err"; echo "ok    $repo"
  else
    echo "FAIL  $repo: $(tail -1 "$target.err")"; rm -rf "$target" "$target.err"
  fi
}
export -f clone_one
for org in "$@"; do gh repo list "$org" --limit 1000 --json nameWithOwner,diskUsage --jq '.[]|"\(.nameWithOwner) \(.diskUsage/1024|floor)"'; done \
  | xargs -P 6 -I{} bash -c 'clone_one "{}"'
echo DONE; df -h "$DEST" | tail -1; du -sh "$DEST"
