#!/usr/bin/env bash
# sync-skills.sh: copy pinned agent skills into this repository's skills directory.
#
# Vendored into a consuming repository as .agents/sync-skills.sh, and into tools that install it (it names no
# repository, so a copy can live anywhere; keep it that way).
# Reads .agents/skills.lock, fetches each source at its pinned commit, and copies the selected
# skills into .claude/skills/ (or the lock's `target` directories). Run it from a SessionStart
# hook (terminal and cloud sessions) and as an explicit CI step (GitHub Actions).
#
#   sync-skills.sh                      apply the lock (fast no-op when nothing changed)
#   sync-skills.sh --dev                use sibling checkouts' working trees, not pinned commits
#   sync-skills.sh --strict             exit non-zero on any failure (CI); default never blocks
#   sync-skills.sh update <owner/repo> [ref] [select]
#                                       pin a source to a ref's current commit (adds the source
#                                       if new; select defaults to *), then apply the lock
#
# Lock format, one directive per line ('#' starts a comment):
#   <owner/repo>  <ref>  <40-hex sha>  <select>
#   target <dir> [<dir>...]            default: .claude/skills
# Earlier sources win a skill-name clash. <select> is * or a comma-separated list: plugin names
# or plugin/skill for a marketplace source (plugins/<p>/skills/<s>/), skill names for a plain
# source (skills/<s>/).
#
# Fetch order per source: cache, sibling checkout (a clone next to this repository, e.g. a cloud
# environment's attached repository), git fetch with ambient credentials, then a GitHub tarball
# (GH_TOKEN/GITHUB_TOKEN if set, else anonymous). A skill the repository commits itself is never
# overwritten. Synced skill folders carry a .gitignore marker, so they stay out of git and are
# pruned when they leave the lock.
#
# Environment (for tests and unusual setups):
#   AGENT_SKILLS_CACHE        cache dir (default ${XDG_CACHE_HOME:-~/.cache}/agent-skills)
#   AGENT_SKILLS_SOURCES_DIR  where sibling checkouts live (default: this repository's parent)
#   AGENT_SKILLS_GIT_BASE     git URL prefix (default https://github.com/)
#   AGENT_SKILLS_NO_TARBALL   set to 1 to skip the tarball fallback
#
# Portable to bash 3.2 (macOS): no associative arrays, mapfile or ${var,,}.

set -u

VERSION=1
MARKER="# agent-skills: synced by .agents/sync-skills.sh"
GIT_BASE="${AGENT_SKILLS_GIT_BASE:-https://github.com/}"
CACHE="${AGENT_SKILLS_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/agent-skills}"
DEV=0
STRICT=0
FAILED=0

say() { echo "agent-skills: $*" >&2; }
fail() { say "$*"; FAILED=1; }
finish() {
  if [ "$FAILED" -ne 0 ] && [ "$STRICT" -eq 1 ]; then exit 1; fi
  exit 0
}

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1; else shasum -a 256 | cut -d' ' -f1; fi
}

ROOT="${CLAUDE_PROJECT_DIR:-}"
[ -n "$ROOT" ] || ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || ROOT="$PWD"
cd "$ROOT" || { say "can't enter $ROOT"; exit 0; }
LOCK="$ROOT/.agents/skills.lock"
SOURCES_DIR="${AGENT_SKILLS_SOURCES_DIR:-$(dirname "$ROOT")}"
GIT_DIR="$(git rev-parse --absolute-git-dir 2>/dev/null || true)"
STAMP="${GIT_DIR:+$GIT_DIR/agent-skills.stamp}"

# ------------------------------------------------------------------ lock

SRC_REPO=(); SRC_REF=(); SRC_SHA=(); SRC_SEL=(); TARGETS=()

read_lock() {
  local line repo ref sha sel extra n=0
  SRC_REPO=(); SRC_REF=(); SRC_SHA=(); SRC_SEL=(); TARGETS=()
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    line="${line%%#*}"
    # Split on whitespace without expanding '*' (a select) against the filesystem.
    set -f
    # shellcheck disable=SC2086
    set -- $line
    set +f
    [ $# -eq 0 ] && continue
    if [ "$1" = target ]; then
      shift
      [ $# -gt 0 ] || { fail "skills.lock:$n: target needs at least one directory"; continue; }
      TARGETS+=("$@")
      continue
    fi
    repo="$1"; ref="${2:-}"; sha="${3:-}"; sel="${4:-}"; extra="${5:-}"
    if [ -n "$extra" ] || [ -z "$sel" ]; then fail "skills.lock:$n: expected <owner/repo> <ref> <sha> <select>"; continue; fi
    case "$repo" in */*) ;; *) fail "skills.lock:$n: '$repo' is not owner/repo"; continue ;; esac
    if ! printf '%s' "$sha" | grep -Eq '^[0-9a-f]{40}$'; then fail "skills.lock:$n: '$sha' is not a 40-character commit sha"; continue; fi
    SRC_REPO+=("$repo"); SRC_REF+=("$ref"); SRC_SHA+=("$sha"); SRC_SEL+=("$sel")
  done < "$LOCK"
  [ ${#TARGETS[@]} -gt 0 ] || TARGETS=(.claude/skills)
}

# ------------------------------------------------------------------ fetch

# fetch_source <repo> <sha>: prints a directory holding the source tree at <sha>, or fails.
fetch_source() {
  local repo="$1" sha="$2" dest tmp sib tok url top
  sib="$SOURCES_DIR/${repo##*/}"

  if [ "$DEV" -eq 1 ] && git -C "$sib" rev-parse --git-dir >/dev/null 2>&1 && [ "$(cd "$sib" && pwd -P)" != "$(pwd -P)" ]; then
    tmp="$(mktemp -d)" || return 1
    if tar -C "$sib" --exclude=.git -cf - . | tar -C "$tmp" -xf -; then
      say "$repo: using the working tree of $sib (--dev)"
      echo "$tmp"; return 0
    fi
    rm -rf "$tmp"
  fi

  dest="$CACHE/$repo/$sha"
  if [ -f "$dest/.agent-skills-complete" ]; then echo "$dest"; return 0; fi
  mkdir -p "$CACHE/$repo" || return 1
  tmp="$(mktemp -d "$CACHE/$repo/.tmp.XXXXXX")" || return 1
  mkdir "$tmp/x"

  local got=0
  # 1. sibling checkout at the pinned commit (fetching that commit into it if it's missing)
  if git -C "$sib" rev-parse --git-dir >/dev/null 2>&1; then
    if git -C "$sib" cat-file -e "$sha^{commit}" 2>/dev/null \
      || GIT_TERMINAL_PROMPT=0 git -C "$sib" fetch -q --depth 1 origin "$sha" 2>/dev/null; then
      git -C "$sib" archive "$sha" | tar -C "$tmp/x" -xf - && got=1
    fi
  fi
  # 2. git fetch by sha with whatever credentials git has (gh auth setup-git, a credential helper)
  if [ "$got" -eq 0 ]; then
    rm -rf "$tmp/x" "$tmp/g"; mkdir "$tmp/x"
    if git init -q "$tmp/g" 2>/dev/null \
      && GIT_TERMINAL_PROMPT=0 git -C "$tmp/g" fetch -q --depth 1 "$GIT_BASE$repo" "$sha" 2>/dev/null; then
      git -C "$tmp/g" archive FETCH_HEAD | tar -C "$tmp/x" -xf - && got=1
    fi
  fi
  # 3. GitHub tarball, authenticated when a token is in the environment (CI)
  if [ "$got" -eq 0 ] && [ "${AGENT_SKILLS_NO_TARBALL:-0}" != 1 ] && command -v curl >/dev/null 2>&1; then
    rm -rf "$tmp/x"; mkdir "$tmp/x"
    tok="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
    if [ -n "$tok" ]; then
      url="https://api.github.com/repos/$repo/tarball/$sha"
      curl -fsSL --max-time 60 -H "Authorization: Bearer $tok" "$url" -o "$tmp/src.tgz" 2>/dev/null || rm -f "$tmp/src.tgz"
    else
      curl -fsSL --max-time 60 "https://codeload.github.com/$repo/tar.gz/$sha" -o "$tmp/src.tgz" 2>/dev/null || rm -f "$tmp/src.tgz"
    fi
    if [ -f "$tmp/src.tgz" ]; then
      top="$(tar -tzf "$tmp/src.tgz" 2>/dev/null | head -1)"
      case "$top" in
        *"${sha:0:7}"*) tar -C "$tmp/x" -xzf "$tmp/src.tgz" --strip-components=1 && got=1 ;;
        *) say "$repo: tarball isn't for ${sha:0:7} (top folder '$top'); ignoring it" ;;
      esac
    fi
  fi

  if [ "$got" -eq 0 ]; then rm -rf "$tmp"; return 1; fi
  touch "$tmp/x/.agent-skills-complete"
  rm -rf "$dest"
  mv "$tmp/x" "$dest" && rm -rf "$tmp" && echo "$dest"
}

# ------------------------------------------------------------------ select

CHOSEN_NAME=(); CHOSEN_PATH=(); CHOSEN_FROM=()

chosen_index() {
  local i
  for ((i = 0; i < ${#CHOSEN_NAME[@]}; i++)); do [ "${CHOSEN_NAME[$i]}" = "$1" ] && { echo "$i"; return 0; }; done
  return 1
}

choose() { # choose <name> <path> <from>
  local prev
  if prev="$(chosen_index "$1")"; then
    say "skill '$1' from $3 skipped: ${CHOSEN_FROM[$prev]} (earlier in the lock) already provides it"
    return
  fi
  CHOSEN_NAME+=("$1"); CHOSEN_PATH+=("$2"); CHOSEN_FROM+=("$3")
}

select_skills() { # select_skills <tree> <select> <from>
  local tree="$1" sel="$2" from="$3" tok d p s
  if [ -d "$tree/plugins" ]; then
    if [ "$sel" = "*" ]; then
      for d in "$tree"/plugins/*/skills/*/; do [ -f "$d/SKILL.md" ] && choose "$(basename "$d")" "${d%/}" "$from"; done
      return 0
    fi
    local toks=(); IFS=, read -r -a toks <<< "$sel"
    for tok in "${toks[@]}"; do
      case "$tok" in
        */*) p="${tok%%/*}"; s="${tok#*/}"
             if [ -f "$tree/plugins/$p/skills/$s/SKILL.md" ]; then choose "$s" "$tree/plugins/$p/skills/$s" "$from"
             else fail "$from: no skill $s in plugin $p"; fi ;;
        *)   [ -d "$tree/plugins/$tok/skills" ] || { fail "$from: no plugin '$tok'"; continue; }
             for d in "$tree/plugins/$tok"/skills/*/; do [ -f "$d/SKILL.md" ] && choose "$(basename "$d")" "${d%/}" "$from"; done ;;
      esac
    done
  elif [ -d "$tree/skills" ]; then
    if [ "$sel" = "*" ]; then
      for d in "$tree"/skills/*/; do [ -f "$d/SKILL.md" ] && choose "$(basename "$d")" "${d%/}" "$from"; done
      return 0
    fi
    local toks=(); IFS=, read -r -a toks <<< "$sel"
    for tok in "${toks[@]}"; do
      if [ -f "$tree/skills/$tok/SKILL.md" ]; then choose "$tok" "$tree/skills/$tok" "$from"; else fail "$from: no skill '$tok'"; fi
    done
  else
    fail "$from: no plugins/ or skills/ folder; nothing to sync"
  fi
}

# ------------------------------------------------------------------ apply

is_tracked() { [ -n "$(git ls-files -- "$1" 2>/dev/null | head -1)" ]; }
is_marked() { # the first line of a synced folder's .gitignore starts with MARKER
  [ -f "$1/.gitignore" ] || return 1
  case "$(head -1 "$1/.gitignore")" in "$MARKER"*) return 0 ;; *) return 1 ;; esac
}

install_skill() { # install_skill <target> <name> <path> <from>
  local dest="$1/$2"
  if is_tracked "$dest"; then say "$dest is committed in this repository; keeping it (it overrides $4)"; return 0; fi
  if [ -e "$dest" ] && ! is_marked "$dest"; then fail "$dest exists and wasn't synced; move it or commit it, then sync again"; return 0; fi
  mkdir -p "$1" || { fail "can't create $1"; return 0; }
  rm -rf "$dest.agent-skills-new"
  if cp -R "$3" "$dest.agent-skills-new"; then
    printf '%s from %s; regenerate, do not edit\n*\n' "$MARKER" "$4" > "$dest.agent-skills-new/.gitignore"
    rm -rf "$dest" && mv "$dest.agent-skills-new" "$dest"
  else
    rm -rf "$dest.agent-skills-new"; fail "couldn't copy $2 into $1"
  fi
}

prune() { # prune <target>: remove synced skills no longer chosen
  local d name
  [ -d "$1" ] || return 0
  for d in "$1"/*/; do
    [ -d "$d" ] || continue
    d="${d%/}"; name="$(basename "$d")"
    is_marked "$d" || continue
    chosen_index "$name" >/dev/null || { rm -rf "$d"; say "removed $d (no longer in the lock)"; }
  done
}

lock_hash() { { echo "v$VERSION"; cat "$LOCK"; echo "dev=$DEV"; } | sha256; }

up_to_date() {
  local want line
  [ -n "$STAMP" ] && [ -f "$STAMP" ] || return 1
  want="$(lock_hash)"
  [ "$(head -1 "$STAMP")" = "$want" ] || return 1
  while IFS= read -r line; do [ -d "$line" ] || return 1; done < <(tail -n +2 "$STAMP")
  return 0
}

apply_lock() {
  local i t tree failed_sources=0
  read_lock
  if [ "$DEV" -eq 0 ] && up_to_date; then return 0; fi
  CHOSEN_NAME=(); CHOSEN_PATH=(); CHOSEN_FROM=()
  for ((i = 0; i < ${#SRC_REPO[@]}; i++)); do
    if ! tree="$(fetch_source "${SRC_REPO[$i]}" "${SRC_SHA[$i]}")"; then
      fail "${SRC_REPO[$i]}@${SRC_SHA[$i]:0:7}: couldn't fetch (no sibling checkout with it, git fetch and the tarball failed); keeping the skills already here"
      failed_sources=1
      continue
    fi
    select_skills "$tree" "${SRC_SEL[$i]}" "${SRC_REPO[$i]}@${SRC_SHA[$i]:0:7}"
  done
  for t in "${TARGETS[@]}"; do
    for ((i = 0; i < ${#CHOSEN_NAME[@]}; i++)); do install_skill "$t" "${CHOSEN_NAME[$i]}" "${CHOSEN_PATH[$i]}" "${CHOSEN_FROM[$i]}"; done
    # A source that failed to fetch keeps its old copies: prune only after a complete run.
    [ "$failed_sources" -eq 0 ] && prune "$t"
  done
  if [ "$FAILED" -eq 0 ] && [ "$DEV" -eq 0 ] && [ -n "$STAMP" ]; then
    { lock_hash; for t in "${TARGETS[@]}"; do for ((i = 0; i < ${#CHOSEN_NAME[@]}; i++)); do echo "$t/${CHOSEN_NAME[$i]}"; done; done; } > "$STAMP"
  fi
  [ "$FAILED" -eq 0 ] && say "${#CHOSEN_NAME[@]} skill(s) in sync from ${#SRC_REPO[@]} source(s)"
}

# ------------------------------------------------------------------ update

resolve_ref() { # resolve_ref <repo> <ref>: prints the commit sha
  local repo="$1" ref="$2" out sha
  if printf '%s' "$ref" | grep -Eq '^[0-9a-f]{40}$'; then echo "$ref"; return 0; fi
  out="$(GIT_TERMINAL_PROMPT=0 git ls-remote "$GIT_BASE$repo" "refs/tags/$ref^{}" "refs/tags/$ref" "refs/heads/$ref" 2>/dev/null)"
  sha="$(printf '%s\n' "$out" | awk -v r="refs/tags/$ref^{}" '$2 == r { print $1; exit }')"
  [ -n "$sha" ] || sha="$(printf '%s\n' "$out" | awk 'NF { print $1; exit }')"
  if [ -z "$sha" ] && command -v gh >/dev/null 2>&1; then sha="$(gh api "repos/$repo/commits/$ref" --jq .sha 2>/dev/null)"; fi
  [ -n "$sha" ] && echo "$sha"
}

update_source() { # update_source <repo> [ref] [select]
  local repo="${1:-}" ref="${2:-}" sel="${3:-}" sha i found=-1 tmp line
  [ -n "$repo" ] || { say "usage: sync-skills.sh update <owner/repo> [ref] [select]"; exit 2; }
  mkdir -p "$ROOT/.agents"
  if [ ! -f "$LOCK" ]; then
    printf '%s\n' "# agent-skills lock: <owner/repo> <ref> <sha> <select>; earlier lines win a name clash." \
      "# Change it with: .agents/sync-skills.sh update <owner/repo> [ref] [select]" > "$LOCK"
  fi
  read_lock
  for ((i = 0; i < ${#SRC_REPO[@]}; i++)); do [ "${SRC_REPO[$i]}" = "$repo" ] && found=$i; done
  if [ "$found" -ge 0 ]; then ref="${ref:-${SRC_REF[$found]}}"; sel="${sel:-${SRC_SEL[$found]}}"; fi
  [ -n "$ref" ] || { say "update: give a ref for the new source $repo"; exit 2; }
  sel="${sel:-*}"
  sha="$(resolve_ref "$repo" "$ref")" || true
  [ -n "$sha" ] || { say "update: can't resolve $repo $ref (no such tag or branch, or no access)"; exit 1; }
  line="$(printf '%-20s %-8s %s  %s' "$repo" "$ref" "$sha" "$sel")"
  tmp="$(mktemp)"
  if [ "$found" -ge 0 ]; then
    awk -v repo="$repo" -v line="$line" '{ split($0, f, /[ \t]+/); if (f[1] == repo && !done) { print line; done = 1 } else print }' "$LOCK" > "$tmp"
  else
    cat "$LOCK" > "$tmp"; echo "$line" >> "$tmp"
  fi
  mv "$tmp" "$LOCK"
  say "pinned $repo $ref at ${sha:0:12}"
}

# ------------------------------------------------------------------ main

main() {
  local cmd=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dev) DEV=1 ;;
      --strict) STRICT=1 ;;
      -h|--help) sed -n '2,/^$/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
      update) cmd=update; shift; update_source "$@"; break ;;
      *) say "unknown argument '$1' (try --help)"; exit 2 ;;
    esac
    shift
  done
  [ -f "$LOCK" ] || { [ -n "$cmd" ] || exit 0; }
  apply_lock
  finish
}

main "$@"
