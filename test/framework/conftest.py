##
# Copyright 2026-2026 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
Configuration for running the EasyBuild framework test suite with pytest (optional, e.g. 'python -O -m pytest -n auto').

The official test runner remains 'python -O -m test.framework.suite';
this file makes pytest run exactly the same set of tests.
"""
import os
import re
import sys
import unittest

import pytest

# make sys.argv look like it does when running 'python -m test.framework.suite':
# - pytest's command line arguments are not meant for EasyBuild's option parser,
#   which is used when test modules are imported (see test/framework/utilities.py);
# - the option parser derives the prefix for environment variables from the program name when no prefix is specified,
#   so with 'pytest' as program name environment variables like $PYTEST_VERSION would be interpreted as options
sys.argv[:] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'suite.py')]

# same initialisation as the official test runner (disable logging, keyring to use, temporary directory, ...);
# the list of test modules in there also determines the order in which tests are run
from test.framework import output_check, suite  # noqa: E402

# files in test/framework that are not test modules, and directories with test data
# (the sandbox contains Python modules like easyblocks, which should not be collected as tests)
collect_ignore = ['output_check.py', 'suite.py', 'utilities.py']
collect_ignore_glob = ['easyconfigs/*', 'easystacks/*', 'modules/*', 'sandbox/*']

# lines written by pytest itself while a test is running, which end up in the captured output:
# the status of subtests, like "SUBPASSED(in_path='/') [100%]" (verbose mode) or "uuuuuuuu [  6%]" (pytest-xdist)
PYTEST_STATUS_LINE_REGEX = re.compile(r"\bSUB(PASSED|FAILED|SKIPPED)\b|^[.,sEFxXu]+ *\[ *[0-9]+%\]$")


def pytest_configure(config):
    """Check whether tests are run with optimization enabled."""
    # some tests rely on assert statements being disabled (like in unittest's assertRegex),
    # which is how the official test runner is used ('python -O -m test.framework.suite')
    if not sys.flags.optimize:
        raise pytest.UsageError("Run the tests with optimization enabled: 'python -O -m pytest' or $PYTHONOPTIMIZE=1")
    # make sure that worker processes for parallel runs (pytest-xdist) also run with optimization enabled
    os.environ['PYTHONOPTIMIZE'] = str(sys.flags.optimize)

    # check for unexpected output printed by tests based on what pytest captures, see pytest_runtest_makereport
    output_check.CHECK_VIA_PYTEST = True


def _suite_test_ids(module):
    """Return set of (class name, method name) for the tests included by the suite() function of a test module."""
    ids = set()
    todo = [module.suite(unittest.TestLoader())]
    while todo:
        tests = todo.pop()
        if isinstance(tests, unittest.TestSuite):
            todo.extend(tests)
        else:
            ids.add((type(tests).__name__, tests._testMethodName))
    return ids


def pytest_collection_modifyitems(config, items):
    """
    Only retain tests that are included by the suite() function of the corresponding test module,
    like 'python -m test.framework.suite' does:
    pytest collects *all* unittest.TestCase subclasses in a module, including (imported) base classes
    like ModuleGeneratorTest, which should not be run by themselves.
    """
    suite_ids = {}
    selected, deselected = [], []
    for item in items:
        module = item.module
        if module not in suite_ids:
            suite_ids[module] = _suite_test_ids(module) if hasattr(module, 'suite') else None
        ids = suite_ids[module]
        if item.cls is None or ids is None or (item.cls.__name__, item.name) in ids:
            selected.append(item)
        else:
            deselected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)

    # run tests in the same order as the official test runner does: the order of the test modules matters,
    # since some tests expect to run in a fresh Python process (like test_000_list_easyblocks in options.py);
    # this is also what makes parallel runs with 'pytest -n auto --dist loadfile' reliable,
    # since each test module is then run from start to end in a single worker process
    module_order = {module.__name__: idx for idx, module in enumerate(suite.tests)}
    selected.sort(key=lambda item: module_order.get(item.module.__name__, len(module_order)))
    items[:] = selected


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Make tests that print unexpected output to stdout/stderr fail, like test/framework/output_check.py does
    when using the official test runner (based on the output captured by pytest, so not with 'pytest -s').
    """
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call' and report.passed and os.getenv(output_check.ALLOW_OUTPUT_ENV_VAR) != '1':
        output = report.capstdout + report.capstderr
        output = '\n'.join(line for line in output.splitlines() if not PYTEST_STATUS_LINE_REGEX.search(line))
        if output_check.unexpected_output(output):
            report.outcome = 'failed'
            report.longrepr = ("Test %s printed unexpected output to stdout/stderr (capture it via "
                               "self.mocked_stdout_stderr(), or set $%s=1 to disable this check):\n%s"
                               % (item.nodeid, output_check.ALLOW_OUTPUT_ENV_VAR, output))
