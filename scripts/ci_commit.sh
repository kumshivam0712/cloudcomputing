#!/usr/bin/env bash
# ci_commit.sh "message" PATH...   (used by the GitHub Actions workflows)
# Commit result files back to the branch the workflow ran on, authored by the repository owner
# (COMMIT_NAME / COMMIT_EMAIL), then push with retries.
set -euo pipefail
msg=$1; shift
branch=${GITHUB_REF_NAME:?}
git config user.name "${COMMIT_NAME:?}"
git config user.email "${COMMIT_EMAIL:?}"
git add -f -- "$@"
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "$msg"
for i in 1 2 3 4 5; do
  if git pull -q --rebase origin "$branch" && git push -q origin "HEAD:$branch"; then
    echo "pushed: $msg"; exit 0
  fi
  sleep $((2 ** i))
done
echo "push failed" >&2; exit 1
