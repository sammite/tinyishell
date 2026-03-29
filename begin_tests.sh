#!/bin/bash
source tshvenv/bin/activate

SAVE_OUTPUT=false
if [[ "$1" == "--save-output" ]]; then
    SAVE_OUTPUT=true
fi

timestamp=$(date +%Y%m%d_%H%M%S)
logfile="tmp_musl_log_${timestamp}.log"

echo "--- Running musl Static Tests ---"
pytest -sv --musl 2>&1 | tee "$logfile"
ret=${PIPESTATUS[0]}

if [ "$SAVE_OUTPUT" = false ] && [ $ret -eq 0 ]; then
    echo "Tests passed, removing $logfile"
    rm "$logfile"
fi

deactivate
exit $ret
