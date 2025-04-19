#!/bin/bash

echo -n "taxi-front: "
if screen -ls | grep -q "\.taxi-front"; then
        screen -S taxi-front -X stuff "^C" && echo "ok" || echo "failed"
else
        echo "not running"
fi

echo -n "taxi-back: "
if screen -ls | grep -q "\.taxi-back"; then
        screen -S taxi-back -X stuff "^C" && echo "ok" || echo "failed"
else
        echo "not running"
fi
