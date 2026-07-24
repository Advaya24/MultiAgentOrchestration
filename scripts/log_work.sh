#!/usr/bin/env sh
# Append a timestamped action or decision to the local, untracked work log.
# Usage: scripts/log_work.sh "Decision: use durable handoff records"

set -eu

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 \"action or decision\"" >&2
    exit 1
fi

log_path=".local/work-log.md"
mkdir -p .local

if [ ! -f "$log_path" ]; then
    printf '# Local work log\n\n' > "$log_path"
fi

printf -- '- %s — %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$log_path"
