#!/usr/bin/env bash
# fetch_models.sh v1 [v2 ...]
# Download each model version from its GitHub Release (tag model-<v>), check the files against
# the release's model.sha256 AND against the copy committed in models/<v>/model.sha256, then
# upload the model + tokenizer to object storage at s3://models/<v>/.
# Set LOCAL_MODELS=1 to upload build/models/<v>/ instead (e.g. right after `make train`).
set -euo pipefail
cd "$(dirname "$0")/.."
repo=${GITHUB_REPO:-kumshivam0712/cloudcomputing}
PY=${PY:-.venv/bin/python}

for v in "$@"; do
  if [[ "${LOCAL_MODELS:-0}" == 1 ]]; then
    dir=build/models/$v
  else
    dir=build/release/$v
    base="https://github.com/$repo/releases/download/model-$v"
    mkdir -p "$dir"
    curl -fsSL --retry 5 -o "$dir/model.sha256" "$base/model.sha256"
    while read -r sum name; do
      [[ -z "$name" ]] && continue
      if [[ -f "$dir/$name" ]] && echo "$sum  $dir/$name" | sha256sum -c --status; then continue; fi
      echo "downloading $base/$name"
      curl -fsSL --retry 5 -o "$dir/$name" "$base/$name"
    done < "$dir/model.sha256"
  fi
  (cd "$dir" && sha256sum -c model.sha256)
  if [[ -f models/$v/model.sha256 ]]; then
    diff -q models/$v/model.sha256 "$dir/model.sha256" \
      && echo "models/$v/model.sha256 (Git) matches the release checksums"
  fi
  $PY scripts/s3.py put-dir "$dir" "s3://models/$v/"
done
