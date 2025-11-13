#!/usr/bin/env bash
set -euo pipefail

REGISTRY="${REGISTRY:-local}"
TAG="${TAG:-latest}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

services=(
  conversation-service
  telephony-service
  calendar-service
  mapping-service
  data-service
  notification-service
  dashboard-service
)

echo "[deploy] Building service images with tag ${REGISTRY}:${TAG}" >&2
for service in "${services[@]}"; do
  service_dir="${ROOT_DIR}/${service}"
  image="${REGISTRY}/cva-${service}:${TAG}"
  if [[ ! -f "${service_dir}/Dockerfile" ]]; then
    echo "Skipping ${service} (no Dockerfile found)" >&2
    continue
  fi
  echo "[deploy] docker build ${image}" >&2
  docker build -t "${image}" -f "${service_dir}/Dockerfile" "${service_dir}"
  if [[ "${PUSH:-false}" == "true" ]]; then
    echo "[deploy] docker push ${image}" >&2
    docker push "${image}"
  fi
done

echo "[deploy] Building docker-compose bundle" >&2
docker compose -f "${ROOT_DIR}/docker-compose.yml" build

echo "[deploy] Completed build sequence" >&2
