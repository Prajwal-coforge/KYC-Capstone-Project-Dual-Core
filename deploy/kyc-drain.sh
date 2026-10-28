#!/bin/bash
# Every boot: start the mock on loopback, drain the queue as kyc, then stop.
# A failed review leaves the message on the queue. This never opens SQLite.
set -uo pipefail
exec >> /var/log/kyc-drain.log 2>&1
REGION=us-east-1
IMAGE=104005345381.dkr.ecr.us-east-1.amazonaws.com/kyc-copilot:d6d3a04
systemctl start docker
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin 104005345381.dkr.ecr.us-east-1.amazonaws.com
docker pull "$IMAGE"
if ! docker ps --format '{{.Names}}' | grep -qx kyc-mock; then
  docker rm -f kyc-mock >/dev/null 2>&1 || true
  docker run -d --name kyc-mock --network host --user kyc "$IMAGE"
fi
python3 - <<'PY'
import time
import urllib.request

for _ in range(30):
    try:
        urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=2)
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("mock did not become healthy")
PY
SECRET_JSON=$(aws secretsmanager get-secret-value \
  --secret-id kyc/staging/database --query SecretString --output text --region "$REGION")
KYC_DATABASE_URL=$(printf '%s' "$SECRET_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["url"], end="")')
unset SECRET_JSON
export KYC_DATABASE_URL
export KYC_API_URL=http://127.0.0.1:8766
export KYC_DOCKER_NETWORK=host
export KYC_RUN_USER=kyc
export KYC_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/104005345381/kyc-staging-cases
export KYC_IMAGE="$IMAGE"
export KYC_OUT_DIR=/var/lib/kyc/out
export KYC_PACKET_BUCKET=kyc-staging-packets-104005345381
export KYC_TRACE_BUCKET=kyc-staging-traces-104005345381
export AWS_REGION="$REGION"
export AWS_DEFAULT_REGION="$REGION"
export PYTHONPATH=/opt/kyc/src
install -d -m 750 /var/lib/kyc/out
chown 1000:1000 /var/lib/kyc/out
rm -rf /opt/kyc/src
docker create --name kyc-src "$IMAGE" >/dev/null
docker cp kyc-src:/app/src /opt/kyc/src
docker rm kyc-src >/dev/null
while true; do
  python3 -m kyc_copilot.runner.batch_queue
  code=$?
  if [ "$code" -eq 3 ]; then
    break
  fi
  if [ "$code" -ne 0 ]; then
    exit "$code"
  fi
done
docker rm -f kyc-mock >/dev/null 2>&1 || true
shutdown -h now
