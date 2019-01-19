#!/bin/bash
echo "testing with `which python3`: `python3 -V`"
for mod in `ls easybuild/base/*.py easybuild/tools/*py easybuild/main.py | egrep -v '__init__|ordereddict' | cut -f2-3 -d/ | tr '/' '.' | sed 's/.py$//g'`; do
    test="import easybuild.$mod"
    echo $test
    python3 -c "$test"
done
echo "set_up_configuration()"
python3 -c "from easybuild.tools.options import set_up_configuration; set_up_configuration()"
echo "test.framework.filetools"
python3 -O -m test.framework.filetools
