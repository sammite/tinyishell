#!/bin/bash
source tshvenv/bin/activate

LATENCY=false
SAVE_OUTPUT=false
PYTEST_ARGS=()

for arg in "$@"; do
    if [[ "$arg" == "--latency" ]]; then
        LATENCY=true
    elif [[ "$arg" == "--save-output" ]]; then
        SAVE_OUTPUT=true
    else
        PYTEST_ARGS+=("$arg")
    fi
done

# 1. Add latency to loopback interface if requested
if [ "$LATENCY" = true ]; then
    echo "--- Adding 3s latency to lo (requires sudo) ---"
    sudo tc qdisc add dev lo root netem delay 3000ms

    # Setup trap to ensure latency is removed even if script exits unexpectedly
    function cleanup {
        echo "--- Removing latency ---"
        sudo tc qdisc del dev lo root
    }
    trap cleanup EXIT
fi

timestamp=$(date +%Y%m%d_%H%M%S)
logfile="tmp_musl_log_${timestamp}.log"

if [ "$LATENCY" = true ]; then
    echo "--- Running musl Static Tests with 3s Latency ---"
else
    echo "--- Running musl Static Tests ---"
fi

pytest -sv --musl "${PYTEST_ARGS[@]}" 2>&1 | tee "$logfile"
ret=${PIPESTATUS[0]}

if [ "$SAVE_OUTPUT" = false ] && [ $ret -eq 0 ]; then
    echo "Tests passed, removing $logfile"
    rm "$logfile"
fi

deactivate
exit $ret
