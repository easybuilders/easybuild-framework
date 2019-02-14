#!/bin/bash
set -e
echo "testing with `which python3`: `python3 -V`"
for mod in `ls easybuild/base/*.py easybuild/tools/*.py test/framework/*.py | egrep -v '__init__|ordereddict|/suite.py' | cut -f1-3 -d/ | tr '/' '.' | sed 's/.py$//g'`; do
    test="import $mod"
    echo $test
    python3 -c "$test"
done
echo "import easybuild.main"
python3 -c "import easybuild.main"
echo "set_up_configuration()"
python3 -c "from easybuild.tools.options import set_up_configuration; set_up_configuration()"
for subsuite in asyncprocess build_log config containers docs easyconfig filetools github module_generator modules run systemtools toolchain; do
    echo "test.framework.${subsuite}"
    python3 -O -m test.framework.${subsuite}
done
