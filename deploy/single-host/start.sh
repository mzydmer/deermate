#!/bin/sh
set -eu
cd "$(dirname "$0")"
umask 077
. ./.env
docker info >/dev/null
docker compose version >/dev/null
docker volume create "$DEERMATE_STAGE_VOLUME" >/dev/null
helper=$(docker run --detach --rm --network=none --cap-drop=ALL --user=0:0 \
    --security-opt=no-new-privileges:true --memory=64m --pids-limit=16 \
    --mount "type=volume,source=$DEERMATE_STAGE_VOLUME,target=/stage" \
    --entrypoint /bin/sleep "$DEERMATE_GATEWAY_IMAGE" 300)
trap 'docker rm --force "$helper" >/dev/null 2>&1 || true' EXIT HUP INT TERM
docker cp runtime/. "$helper:/stage/"
docker compose --env-file .env --file compose.yaml up --detach --wait --wait-timeout 240
