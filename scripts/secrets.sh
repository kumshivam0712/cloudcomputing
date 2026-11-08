#!/usr/bin/env bash
# Generate random S3 credentials (once, kept in .secrets/, which is git-ignored) and store them
# ONLY as Kubernetes Secrets:
#   data/seaweedfs-s3-config   the SeaweedFS S3 identities file (s3.json)
#   pipeline/s3-credentials    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for the workers
#   app/s3-credentials         the same keys for the inference service
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .secrets && chmod 700 .secrets
if [[ ! -f .secrets/s3.env ]]; then
  ak="AK$(python3 -c 'import secrets; print(secrets.token_hex(9).upper())')"
  sk="$(python3 -c 'import secrets; print(secrets.token_urlsafe(30))')"
  umask 177
  printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$ak" "$sk" > .secrets/s3.env
fi
# shellcheck disable=SC1091
source .secrets/s3.env

s3json=$(printf '{"identities":[{"name":"ccmini","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","List","Tagging","Write"]}]}' \
  "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY")

kubectl apply -f k8s/namespaces.yaml >/dev/null
kubectl -n data create secret generic seaweedfs-s3-config --from-literal=s3.json="$s3json" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
for ns in pipeline app; do
  kubectl -n "$ns" create secret generic s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
done
echo "secrets: data/seaweedfs-s3-config, pipeline/s3-credentials, app/s3-credentials are in place"
