#!/usr/bin/env bash
set -euo pipefail

# This script merges a fetched upstream ref. Fetching and pushing are separate
# workflow steps so an unsuccessful merge can never publish a partial result.
upstream_ref="${1:-refs/remotes/upstream/main}"
protected_paths=(
  'Clash/kclash.ini'
  '.github/workflows'
  '.github/scripts'
)

cd "$(git rev-parse --show-toplevel)"
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'Refusing to sync: the working tree must be clean.' >&2
  exit 1
fi

personal_head="$(git rev-parse HEAD)"
upstream_head="$(git rev-parse --verify "${upstream_ref}^{commit}")"
if git merge-base --is-ancestor "$upstream_head" "$personal_head"; then
  echo 'Already synced with upstream.'
  exit 0
fi

merge_status=0
git -c merge.autoStash=false merge --no-commit --no-ff "$upstream_head" || merge_status=$?
if ! git rev-parse --verify -q MERGE_HEAD >/dev/null; then
  echo "Merge failed before a merge result was created (exit $merge_status)." >&2
  exit 1
fi

# Restore entire paths even when Git merged them without conflicts. Choosing
# "ours" only for conflicting lines would still accept other upstream edits.
if ! git restore --source="$personal_head" --staged --worktree -- "${protected_paths[@]}"; then
  git merge --abort
  echo 'Could not restore the protected files; sync aborted.' >&2
  exit 1
fi

conflicts="$(git diff --name-only --diff-filter=U)"
if [[ -n "$conflicts" ]]; then
  echo 'Sync aborted: conflicts outside the protected paths:' >&2
  printf '%s\n' "$conflicts" >&2
  git merge --abort
  exit 1
fi

# Reject errors unrelated to content conflicts, even if no unmerged paths remain.
if [[ "$merge_status" -gt 1 ]]; then
  git merge --abort
  echo "Sync aborted: git merge exited with $merge_status." >&2
  exit 1
fi

if ! git diff --cached --quiet "$personal_head" -- "${protected_paths[@]}"; then
  git merge --abort
  echo 'Sync aborted: a protected file changed.' >&2
  exit 1
fi

git -c core.hooksPath=/dev/null commit -m "chore: sync upstream ${upstream_head:0:12}"
echo 'Upstream merged; personal configuration and automation preserved.'
