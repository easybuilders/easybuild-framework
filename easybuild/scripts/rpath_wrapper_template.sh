#!/bin/bash

set -e

# logging function
function log {
    echo "($$) [$(date "+%%Y-%%m-%%d %%H:%%M:%%S")] $1" >> %(rpath_wrapper_log)s
}

# command name
CMD=`basename $0`

log "found CMD: $CMD | original command: %(orig_cmd)s | orig args: '$(echo \"$@\")'"

# rpath_args.py script spits out statement that defines $CMD_ARGS
rpath_args_out=$(%(python)s -O %(rpath_args_py)s $CMD '%(rpath_filter)s' "$@")

log "rpath_args_out:
$rpath_args_out"

# define $CMD_ARGS by evaluating output of rpath_args.py script
eval $rpath_args_out

# call original command with modified list of command line arguments
log "running '%(orig_cmd)s $(echo ${CMD_ARGS[@]})'"
%(orig_cmd)s "${CMD_ARGS[@]}"
