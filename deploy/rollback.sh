#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT=${1:-}
REVISION=${2:-}

if [[ -z "$ENVIRONMENT" ]]; then
  echo "Usage: deploy/rollback.sh <staging|production> [revision]" >&2
  exit 1
fi

echo "Rolling back ${ENVIRONMENT} to ${REVISION:-previous revision}"
# TODO: Replace with your rollback logic.
# Examples:
#   helm rollback berkeley-bot ${REVISION}
#   kubectl -n ${ENVIRONMENT} rollout undo deployment/berkeley-engine
