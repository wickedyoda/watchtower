#!/usr/bin/env bash

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-ghcr.io/your-org/watchtower}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH="${PUSH:-true}"
BUILDER_NAME="${BUILDER_NAME:-watchtower-multi}"

if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER_NAME" --use
else
  docker buildx use "$BUILDER_NAME"
fi

docker buildx inspect --bootstrap >/dev/null

BUILD_ARGS=(
  --platform "$PLATFORMS"
  --tag "${IMAGE_NAME}:${IMAGE_TAG}"
)

if [[ "${PUSH}" == "true" ]]; then
  BUILD_ARGS+=(--push)
else
  BUILD_ARGS+=(--load)
fi

docker buildx build "${BUILD_ARGS[@]}" .
