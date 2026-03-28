#!/bin/bash
source tshvenv/bin/activate

echo "--- Running Standard Linux Tests ---"
pytest -sv 2>&1 | tee tmp_log_$(date +%Y%m%d_%H%M%S).log

echo -e "\n--- Running musl Static Tests ---"
pytest -sv --musl 2>&1 | tee tmp_musl_log_$(date +%Y%m%d_%H%M%S).log

deactivate
