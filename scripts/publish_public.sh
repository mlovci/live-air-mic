#!/usr/bin/env bash
# =============================================================================
# LiveAirMic — Zero-Leak Public Release Promoter (`scripts/publish_public.sh`)
# =============================================================================
# Synthesizes a single, pristine Conventional Commit onto `public-main` from a
# target private ref (default: `master`) using `git read-tree` + `git commit-tree`
# in an isolated temporary index.
#
# Architectural Guarantee:
#   - The resulting commit on `public-main` has ONLY `public-main` as its parent.
#   - ZERO private commit SHAs or intermediate WIP history are ever reachable
#     from `public-main` or pushed to the `public` remote (`mlovci/live-air-mic`).
#   - Automatically strips private/release-asset-only binaries (`*.apk`) from
#     the public git tree while preserving `.amxd` and `.adg` Ableton devices.
#
# Usage:
#   ./scripts/publish_public.sh "feat(dsp): add 3-band parametric vocal EQ" [source_ref] [--push]
# =============================================================================
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 \"<conventional-commit-message>\" [source_ref=master] [--push]" >&2
    exit 1
fi

COMMIT_MSG="$1"
SOURCE_REF="${2:-master}"
PUSH_FLAG="${3:-}"

PUBLIC_BRANCH="public-main"
PUBLIC_REMOTE="public"

# Ensure public-main exists locally
if ! git rev-parse --verify "$PUBLIC_BRANCH" >/dev/null 2>&1; then
    echo "Error: Local branch '$PUBLIC_BRANCH' does not exist." >&2
    exit 1
fi

TMP_INDEX="$(mktemp -t git_public_index.XXXXXX)"
rm -f "$TMP_INDEX"
trap 'rm -f "$TMP_INDEX"' EXIT

export GIT_INDEX_FILE="$TMP_INDEX"

# 1. Read the target source tree into the isolated index
git read-tree "$SOURCE_REF"

# 2. Strip release-only APK binaries from the public git tree
git rm --cached --ignore-unmatch "android-native/*.apk" >/dev/null 2>&1 || true

# 3. Ensure .gitignore in public-main excludes android-native/*.apk
GITIGNORE_CONTENT="$(git show "${SOURCE_REF}:.gitignore")"
if ! grep -q "android-native/\*.apk" <<<"$GITIGNORE_CONTENT"; then
    GITIGNORE_CONTENT="${GITIGNORE_CONTENT}"$'\n'"android-native/*.apk"$'\n'
fi
GITIGNORE_BLOB="$(printf "%s" "$GITIGNORE_CONTENT" | git hash-object -w --stdin)"
git update-index --add --cacheinfo "100644,${GITIGNORE_BLOB},.gitignore"

NEW_TREE="$(git write-tree)"
CURRENT_PUBLIC_TREE="$(git rev-parse "${PUBLIC_BRANCH}^{tree}")"

if [[ "$NEW_TREE" == "$CURRENT_PUBLIC_TREE" ]]; then
    echo "No tree changes between '$SOURCE_REF' (filtered) and '$PUBLIC_BRANCH'. Nothing to commit."
    exit 0
fi

# 4. Create a single-parent commit on top of public-main
NEW_COMMIT="$(printf "%s\n" "$COMMIT_MSG" | git commit-tree "$NEW_TREE" -p "$PUBLIC_BRANCH")"
git update-ref "refs/heads/${PUBLIC_BRANCH}" "$NEW_COMMIT"

# 5. Invariant check: verify zero shared commit history between public-main and private source
if git merge-base "$PUBLIC_BRANCH" "$SOURCE_REF" >/dev/null 2>&1; then
    echo "FATAL: History leak detected between '$PUBLIC_BRANCH' and '$SOURCE_REF'!" >&2
    exit 1
fi

echo "✓ Created clean public commit on ${PUBLIC_BRANCH}: ${NEW_COMMIT:0:7}"
git --no-pager show --stat "$NEW_COMMIT"

if [[ "$PUSH_FLAG" == "--push" || "$SOURCE_REF" == "--push" ]]; then
    echo "Pushing ${PUBLIC_BRANCH} -> ${PUBLIC_REMOTE}/main..."
    git push "$PUBLIC_REMOTE" "${PUBLIC_BRANCH}:main"
    echo "✓ Public repository updated with zero private history leakage."
else
    echo ""
    echo "To push to the public repository, run:"
    echo "  git push ${PUBLIC_REMOTE} ${PUBLIC_BRANCH}:main"
fi
