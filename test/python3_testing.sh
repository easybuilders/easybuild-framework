#!/bin/bash
echo "testing with `which python3`: `python3 -V`"
for mod in `ls easybuild/base/*.py easybuild/tools/*py| grep -v __init__ | cut -f2-3 -d/ | tr '/' '.' | sed 's/.py$//g'`; do
    test="import easybuild.$mod"
    echo $test
    python3 -c "$test"
done
python3 -c "import easybuild.tools.asyncprocess"
python3 -c "import easybuild.tools.config"
