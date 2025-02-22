#!/bin/bash

echo -n "taxi-front: "
if screen -ls | grep -q "\.taxi-front"; then
        echo "already running"
else
        screen -dmS taxi-front bash -c "cd ~/taxi-front && pnpm web start" && echo "ok" || echo "failed"
fi

echo -n "taxi-back: "
if screen -ls | grep -q "\.taxi-back"; then
        echo "already running"
else
        screen -dmS taxi-back bash -c "cd ~/taxi-back && pnpm start" && echo "ok" || echo "failed"
fi