#!/bin/bash

set -e

# logging function
function log {
    echo "($$) [$(date "+%%Y-%%m-%%d %%H:%%M:%%S")] $1" >> %(rpath_wrapper_log)s
}

# command name
CMD=`basename $0`

log "found CMD: $CMD | original command: %(orig_cmd)s | orig args: '$(echo \"$@\")'"

# rpath_args.py script spits out statements that define $RPATH and $CMD_ARGS
rpath_args_out=$(%(python)s -O %(rpath_args_py)s $CMD "$@")

log "rpath_args_out:
$rpath_args_out"

eval $rpath_args_out
log "RPATH: '$RPATH', CMD_ARGS: '$CMD_ARGS'"

log "running '%(orig_cmd)s $RPATH $@'"
%(orig_cmd)s "${RPATH_ARGS[@]}" "${CMD_ARGS[@]}"
