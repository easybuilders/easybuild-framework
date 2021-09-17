#
# Copyright 2014-2021 Ghent University
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
#
"""
Shared module for vsc software testing

TestCase: use instead of unittest TestCase
   from easybuild.base.testing import TestCase

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import difflib
import pprint
import re
import sys
from contextlib import contextmanager

try:
    from cStringIO import StringIO  # Python 2
except ImportError:
    from io import StringIO  # Python 3

from unittest import TestCase as OrigTestCase

from easybuild.tools.py2vs3 import string_type


def nicediff(txta, txtb, offset=5):
    """
    generate unified diff style output
        ndiff has nice indicators what is different, but prints the whole content
            each line that is interesting starts with non-space
        unified diff only prints changes and some offset around it

    return list with diff (one per line) (not a generator like ndiff or unified_diff)
    """
    diff = list(difflib.ndiff(txta.splitlines(1), txtb.splitlines(1)))
    different_idx = [idx for idx, line in enumerate(diff) if not line.startswith(' ')]
    res_idx = []
    # very bruteforce
    for didx in different_idx:
        for idx in range(max(didx - offset, 0), min(didx + offset, len(diff) - 1)):
            if idx not in res_idx:
                res_idx.append(idx)
    res_idx.sort()
    # insert linenumbers too? what are the linenumbers in ndiff?
    newdiff = [diff[idx] for idx in res_idx]

    return newdiff


class TestCase(OrigTestCase):
    """Enhanced test case, provides extra functionality (e.g. an assertErrorRegex method)."""

    longMessage = True  # print both standard messgae and custom message

    ASSERT_MAX_DIFF = 100
    DIFF_OFFSET = 5  # lines of text around changes

    def is_string(self, x):
        """test if the variable x is a string)"""
        try:
            return isinstance(x, string_type)
        except NameError:
            return isinstance(x, str)

    # pylint: disable=arguments-differ
    def assertEqual(self, a, b, msg=None):
        """Make assertEqual always print useful messages"""

        try:
            super(TestCase, self).assertEqual(a, b)
        except AssertionError as e:
            if msg is None:
                msg = str(e)
            else:
                msg = "%s: %s" % (msg, e)

            if self.is_string(a):
                txta = a
            else:
                txta = pprint.pformat(a)
            if self.is_string(b):
                txtb = b
            else:
                txtb = pprint.pformat(b)

            diff = nicediff(txta, txtb, offset=self.DIFF_OFFSET)
            if len(diff) > self.ASSERT_MAX_DIFF:
                limit = ' (first %s lines)' % self.ASSERT_MAX_DIFF
            else:
                limit = ''

            raise AssertionError("%s:\nDIFF%s:\n%s" % (msg, limit, ''.join(diff[:self.ASSERT_MAX_DIFF])))

    def setUp(self):
        """Prepare test case."""
        super(TestCase, self).setUp()

        self.maxDiff = None
        self.longMessage = True

        self.orig_sys_stdout = sys.stdout
        self.orig_sys_stderr = sys.stderr

    def convert_exception_to_str(self, err):
        """Convert an Exception instance to a string."""
        msg = err
        if hasattr(err, 'msg'):
            msg = err.msg
        elif hasattr(err, 'message'):
            msg = err.message
            if not msg:
                # rely on str(msg) in case err.message is empty
                msg = err
        elif hasattr(err, 'args'):  # KeyError in Python 2.4 only provides message via 'args' attribute
            msg = err.args[0]
        else:
            msg = err
        try:
            res = str(msg)
        except UnicodeEncodeError:
            res = msg.encode('utf8', 'replace')

        return res

    def assertErrorRegex(self, error, regex, call, *args, **kwargs):
        """
        Convenience method to match regex with the expected error message.
        Example: self.assertErrorRegex(OSError, "No such file or directory", os.remove, '/no/such/file')
        """
        try:
            call(*args, **kwargs)
            str_kwargs = ['='.join([k, str(v)]) for (k, v) in kwargs.items()]
            str_args = ', '.join(list(map(str, args)) + str_kwargs)
            self.assertTrue(False, "Expected errors with %s(%s) call should occur" % (call.__name__, str_args))
        except error as err:
            msg = self.convert_exception_to_str(err)
            if self.is_string(regex):
                regex = re.compile(regex)
            self.assertTrue(regex.search(msg), "Pattern '%s' is found in '%s'" % (regex.pattern, msg))

    def mock_stdout(self, enable):
        """Enable/disable mocking stdout."""
        sys.stdout.flush()
        if enable:
            sys.stdout = StringIO()
        else:
            sys.stdout = self.orig_sys_stdout

    def mock_stderr(self, enable):
        """Enable/disable mocking stdout."""
        sys.stderr.flush()
        if enable:
            sys.stderr = StringIO()
        else:
            sys.stderr = self.orig_sys_stderr

    def get_stdout(self):
        """Return output captured from stdout until now."""
        return sys.stdout.getvalue()

    def get_stderr(self):
        """Return output captured from stderr until now."""
        return sys.stderr.getvalue()

    @contextmanager
    def mocked_stdout_stderr(self, mock_stdout=True, mock_stderr=True):
        """Context manager to mock stdout and stderr"""
        if mock_stdout:
            self.mock_stdout(True)
        if mock_stderr:
            self.mock_stderr(True)
        try:
            if mock_stdout and mock_stderr:
                yield sys.stdout, sys.stderr
            elif mock_stdout:
                yield sys.stdout
            else:
                yield sys.stderr
        finally:
            if mock_stdout:
                self.mock_stdout(False)
            if mock_stderr:
                self.mock_stderr(False)

    def tearDown(self):
        """Cleanup after running a test."""
        self.mock_stdout(False)
        self.mock_stderr(False)
        super(TestCase, self).tearDown()
