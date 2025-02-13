#!/bin/bash
DEV_USER="${1:-${DEV_USER}}"
if [ -z "$DEV_USER" ]; then
  echo "[entrypoint.sh] No DEV_USER provided. usage: entrypoint.sh <DEV_USER> or set DEV_USER env."
  exit 1
fi

echo "[entrypoint.sh] Running as DEV_USER: $DEV_USER"

BACK_DIR="/home/ubuntu/taxi-back"
FRONT_DIR="/home/ubuntu/taxi-front"

if [ ! -d "$BACK_DIR/.git" ]; then
  echo "[entrypoint.sh] $BACK_DIR is empty. Cloning taxi-back repo..."
  git clone https://github.com/sparcs-kaist/taxi-back.git "$BACK_DIR"
fi

if [ ! -d "$FRONT_DIR/.git" ]; then
  echo "[entrypoint.sh] $FRONT_DIR is empty. Cloning taxi-front repo..."
  git clone https://github.com/sparcs-kaist/taxi-front.git "$FRONT_DIR"
fi

echo "[entrypoint.sh] Done. Starting final command: $@"
exec "$@"