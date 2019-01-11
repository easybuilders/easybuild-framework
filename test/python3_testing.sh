#!/bin/bash
echo "testing with `which python`: `python3 -V`"
for mod in `ls easybuild/base/*.py | grep -v __init__ | cut -f3 -d/ | sed 's/.py$//g'`; do
    test="import easybuild.base.$mod"
    echo $test
    python3 -c $test
done
