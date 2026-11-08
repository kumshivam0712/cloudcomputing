#!/usr/bin/env bash
# Build the single submission file <roll_number>.zip:
#   scripts/package_submission.sh ROLL_NUMBER path/to/scanned-reflection.pdf [GIT_REF]
# Contents (zip root): the source tree of GIT_REF (default: the tag "final", i.e. README.md with the
# GitHub link, report/report.pdf, all code/tests/manifests/workflows/results) + ROLL_NUMBER.pdf
# (the scanned handwritten reflection). Model weights are not in Git, so they are not in the zip.
set -euo pipefail
cd "$(dirname "$0")/.."
roll=${1:?usage: $0 ROLL_NUMBER SCANNED_REFLECTION.pdf [GIT_REF]}
scan=${2:?usage: $0 ROLL_NUMBER SCANNED_REFLECTION.pdf [GIT_REF]}
ref=${3:-final}
[[ "$roll" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "roll number must not contain spaces or special characters" >&2; exit 1; }
[[ -f "$scan" ]] || { echo "scanned reflection $scan not found" >&2; exit 1; }
git rev-parse --verify -q "$ref^{commit}" >/dev/null || { echo "git ref $ref not found" >&2; exit 1; }

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
git archive --format=tar "$ref" | tar -x -C "$stage"
rm -f "$stage/${scan#./}"                     # the scan goes in once, as <roll>.pdf at the root
rmdir "$stage/$(dirname "${scan#./}")" 2>/dev/null || true
cp "$scan" "$stage/$roll.pdf"
for f in README.md report/report.pdf "$roll.pdf"; do
  [[ -f "$stage/$f" ]] || { echo "missing $f in the package" >&2; exit 1; }
done
mkdir -p dist
rm -f "dist/$roll.zip"
python3 - "$stage" "dist/$roll.zip" <<'PY'
import os, sys, zipfile
root, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for d, _, files in sorted(os.walk(root)):
        for f in sorted(files):
            p = os.path.join(d, f)
            z.write(p, os.path.relpath(p, root))
PY
echo "wrote dist/$roll.zip ($(du -h "dist/$roll.zip" | cut -f1)) from $ref ($(git rev-parse --short "$ref"))"
