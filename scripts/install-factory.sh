#!/usr/bin/env bash
# Install the factory's skills, workflows and repository templates into a
# consuming repository. Run it from the root of that repository:
#
#   ~/code/factory/scripts/install-factory.sh [options]
#
# Options:
#   --create-labels      create the factory's labels on the GitHub repository (gh)
#   --with-novelty DIR   also copy the novelty-audit skills from DIR (e.g. ~/code/novelty-audit/skills)
#   --force              overwrite installed files that were changed locally
#   --dry-run            print what would change without writing
#
# Files the factory owns (skills, workflows) are tracked in .claude/factory.lock
# with their checksums. On reinstall, a file changed locally since the last
# install (for example by the improve-review-pr loop) is kept unless --force is
# given. Repository documents (FACTORY.md, vision.md, bets.md) are created only
# if missing and are never overwritten.

set -euo pipefail

FACTORY_DIR="${FACTORY_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SKILLS=(triage spec write-product-spec write-tech-spec novelty-gate implementation validate-against-specs verify-behavior review-pr improve-review-pr bet dependency-bump)
NOVELTY_SKILLS=(novelty-audit novelty-decompose prior-art-search similarity-scan novelty-classify novelty-tests)

create_labels=false force=false dry_run=false novelty_dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --create-labels) create_labels=true ;;
    --force) force=true ;;
    --dry-run) dry_run=true ;;
    --with-novelty) novelty_dir="${2:?--with-novelty needs a directory}"; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Run this from inside the consuming Git repository." >&2; exit 1; }
[ "$root" = "$(pwd -P)" ] || { echo "Run this from the repository root: $root" >&2; exit 1; }
[ "$root" != "$(cd "$FACTORY_DIR" && pwd -P)" ] || { echo "Run this from a consuming repository, not the factory itself." >&2; exit 1; }

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
lock=".claude/factory.lock"
new_lock="$(mktemp)"
trap 'rm -f "$new_lock"' EXIT
installed=0 kept=0 unchanged=0

locked_sha() { [ -f "$lock" ] && awk -v p="$1" '$2 == p { print $1 }' "$lock" || true; }

# install_file SRC DEST: copy a factory-owned file, respecting local changes.
install_file() {
  local src="$1" dest="$2" want have was
  want="$(sha "$src")"
  if [ -f "$dest" ]; then
    have="$(sha "$dest")"
    was="$(locked_sha "$dest")"
    if [ "$have" = "$want" ]; then
      unchanged=$((unchanged + 1)); echo "$want $dest" >> "$new_lock"; return
    fi
    if [ "$force" = false ] && { [ -z "$was" ] || [ "$have" != "$was" ]; }; then
      echo "keep    $dest (changed locally; --force to overwrite)"
      kept=$((kept + 1)); echo "${was:-$have} $dest" >> "$new_lock"; return
    fi
  fi
  echo "install $dest"
  installed=$((installed + 1)); echo "$want $dest" >> "$new_lock"
  [ "$dry_run" = true ] && return
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
}

# install_tree SRC_DIR DEST_DIR: every file except caches.
install_tree() {
  local src="$1" dest="$2" f
  while IFS= read -r f; do
    install_file "$src/$f" "$dest/$f"
  done < <(cd "$src" && find . -type f ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '.DS_Store' | sed 's|^\./||' | sort)
}

# create_once SRC DEST: repository documents, never overwritten.
create_once() {
  if [ -e "$2" ]; then echo "exists  $2"; return; fi
  echo "create  $2"
  [ "$dry_run" = true ] || cp "$1" "$2"
}

for s in "${SKILLS[@]}"; do
  install_tree "$FACTORY_DIR/skills/$s" ".claude/skills/$s"
done

if [ -n "$novelty_dir" ]; then
  for s in "${NOVELTY_SKILLS[@]}"; do
    [ -d "$novelty_dir/$s" ] || { echo "missing $novelty_dir/$s" >&2; exit 1; }
    install_tree "$novelty_dir/$s" ".claude/skills/$s"
  done
fi

install_tree "$FACTORY_DIR/templates/github/workflows" ".github/workflows"

create_once "$FACTORY_DIR/templates/repo/FACTORY.md" FACTORY.md
create_once "$FACTORY_DIR/templates/repo/vision.md" vision.md
create_once "$FACTORY_DIR/templates/repo/bets.md" bets.md

factory_rev="$(git -C "$FACTORY_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [ "$dry_run" = false ]; then
  # Keep entries for files this run didn't touch (e.g. novelty skills installed earlier).
  if [ -f "$lock" ]; then
    carried="$(awk 'NR == FNR { seen[$2] = 1; next } /^#/ { next } !($2 in seen)' "$new_lock" "$lock")"
    [ -z "$carried" ] || printf '%s\n' "$carried" >> "$new_lock"
  fi
  mkdir -p .claude
  { echo "# Installed by factory@$factory_rev. Checksums of factory-owned files; do not edit."; sort -k2 "$new_lock"; } > "$lock"
fi

if [ "$create_labels" = true ]; then
  while IFS='|' read -r name color desc; do
    echo "label   $name"
    [ "$dry_run" = true ] || gh label create "$name" --color "$color" --description "$desc" --force >/dev/null
  done <<'LABELS'
ready-to-implement|0E8A16|Factory: an agent may implement this now
ready-to-spec|1D76DB|Factory: needs PRODUCT.md and TECH.md first
needs-info|FBCA04|Factory: blocked on questions in the triage comment
wait-to-implement|C5DEF5|Factory: doesn't fit the vision or an open bet yet
spec-ready-for-review|5319E7|Factory: specs PR is ready for a human
invariant-risk|B60205|Factory: touches protected paths; Opus and human review
factory:agent|0E8A16|Factory: small and low risk; agents advance it
factory:awaiting-approval|FBCA04|Factory: a human must approve the next stage
factory:approved|0E8A16|Factory: human approval to start the next stage
factory:proposed|EDEDED|Factory: drafted by the bet skill
maintenance|EDEDED|Bugs, CI, dependencies, security: needs no bet
LABELS
fi

cat <<EOF

Factory@$factory_rev: $installed installed, $unchanged unchanged, $kept kept (changed locally).$( [ "$dry_run" = true ] && echo " Dry run: nothing written.")

Next:
  1. Fill in FACTORY.md (validation commands, protected paths, consumers, app).
  2. Add a secret: ANTHROPIC_API_KEY, or CLAUDE_CODE_OAUTH_TOKEN from \`claude setup-token\`.
  3. Optional: FACTORY_GITHUB_TOKEN (fine-grained; contents, issues and pull requests
     read/write on this repository) so agent PRs trigger CI and review.
  4. Optional variables: FACTORY_AUTOCHAIN, FACTORY_VERIFY, FACTORY_TRIAGE_ALL, FACTORY_MODEL_*.
  5. If the implementation agent needs toolchains, add .github/factory/setup.sh.
EOF
