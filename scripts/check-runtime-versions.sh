#!/usr/bin/env bash
# Fails when the Dockerfile drifts from the runtime versions CI tests with:
# svc/.python-version, .nvmrc, and the uv pin in .github/workflows/ci.yml.
# A Dependabot base-image bump stays red until those files are updated too.
set -euo pipefail
cd "$(dirname "$0")/.."

python_file=$(tr -d '[:space:]' < svc/.python-version)
node_file=$(tr -d '[:space:]' < .nvmrc)
# The uv pin is the first `version:` input after the setup-uv step.
uv_ci=$(awk '/astral-sh\/setup-uv/ { in_uv = 1 }
    in_uv && /^ *version: / { gsub(/[^0-9.]/, "", $2); print $2; exit }' .github/workflows/ci.yml)

python_image=$(sed -n 's/^FROM python:\([0-9.]*\)-.*/\1/p' Dockerfile)
node_image=$(sed -n 's/^FROM node:\([0-9.]*\)-.*/\1/p' Dockerfile)
uv_image=$(sed -n 's|^COPY --from=ghcr.io/astral-sh/uv:\([0-9.]*\) .*|\1|p' Dockerfile)

status=0
check() {
    if [[ "$2" != "$3" ]]; then
        echo "::error::Dockerfile $1 is '$2' but $4 says '$3'"
        status=1
    fi
}
check "python" "$python_image" "$python_file" "svc/.python-version"
check "node" "$node_image" "$node_file" ".nvmrc"
check "uv" "$uv_image" "$uv_ci" ".github/workflows/ci.yml"

if [[ $status -eq 0 ]]; then
    echo "Dockerfile matches: python $python_file, node $node_file, uv $uv_ci"
fi
exit $status
