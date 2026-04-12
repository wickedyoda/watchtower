#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/watchtower-export"
BUNDLE_NAME="uptime-watchtower-bundle-$(date +%Y%m%d-%H%M%S).tar.gz"

mkdir -p "${OUT_DIR}"

cp -f "${SCRIPT_DIR}/uptime-bot.py" "${OUT_DIR}/uptime-bot.py"
cp -f "${SCRIPT_DIR}/requirements.txt" "${OUT_DIR}/requirements.txt"
cp -f "${SCRIPT_DIR}/config.yml" "${OUT_DIR}/config.yml"
cp -f "${SCRIPT_DIR}/container-monitor-map.yaml" "${OUT_DIR}/container-monitor-map.yaml"

if [[ ! -f "${OUT_DIR}/Dockerfile" ]]; then
  echo "Missing ${OUT_DIR}/Dockerfile"
  exit 1
fi

if [[ ! -f "${OUT_DIR}/docker-compose.watchtower-uptime-sync.yml" ]]; then
  echo "Missing ${OUT_DIR}/docker-compose.watchtower-uptime-sync.yml"
  exit 1
fi

cd "${OUT_DIR}"
tar -czf "${BUNDLE_NAME}" \
  Dockerfile \
  docker-compose.watchtower-uptime-sync.yml \
  uptime-bot.py \
  requirements.txt \
  config.yml \
  container-monitor-map.yaml

echo "Bundle created: ${OUT_DIR}/${BUNDLE_NAME}"
