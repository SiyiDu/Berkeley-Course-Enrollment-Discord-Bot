#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT=${1:-}
IMAGE_TAG=${2:-}

if [[ -z "$ENVIRONMENT" || -z "$IMAGE_TAG" ]]; then
  echo "Usage: deploy/deploy.sh <staging|production> <image_tag>" >&2
  exit 1
fi

echo "Deploying ${ENVIRONMENT} with image tag ${IMAGE_TAG}"
# TODO: Replace this with your platform-specific deploy logic.
# Examples:
#   helm upgrade --install berkeley-bot ./deploy/chart --set image.tag=${IMAGE_TAG} --namespace ${ENVIRONMENT}
#   kubectl -n ${ENVIRONMENT} set image deployment/berkeley-engine engine=${IMAGE_TAG}
