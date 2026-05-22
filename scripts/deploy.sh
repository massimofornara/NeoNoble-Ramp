#!/usr/bin/env sh
set -eu

ENVIRONMENT="${1:-staging}"
NAMESPACE="${KUBE_NAMESPACE:-neonoble-ramp}"
IMAGE="${IMAGE:-neonoble-ramp:$(git rev-parse --short HEAD 2>/dev/null || echo local)}"

echo "Building ${IMAGE}"
docker build -t "${IMAGE}" .

echo "Ensuring namespace ${NAMESPACE}"
kubectl apply -f deploy/k8s/namespace.yaml

echo "Applying database and app secrets from existing cluster Secret neonoble-ramp-secrets"
kubectl -n "${NAMESPACE}" get secret neonoble-ramp-secrets >/dev/null

echo "Deploying ${ENVIRONMENT}"
helm upgrade --install neonoble-ramp ./deploy/helm/neonoble-ramp \
  --namespace "${NAMESPACE}" \
  --set image.repository="$(echo "${IMAGE}" | cut -d: -f1)" \
  --set image.tag="$(echo "${IMAGE}" | awk -F: '{print $2}')" \
  --set environment="${ENVIRONMENT}"

kubectl -n "${NAMESPACE}" rollout status deployment/neonoble-ramp --timeout=180s
kubectl -n "${NAMESPACE}" get ingress neonoble-ramp
