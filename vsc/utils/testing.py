#!/usr/bin/env python
##
#
# Copyright 2014-2014 Ghent University
#
# This file is part of vsc-base,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/vsc-base
#
# vsc-base is free software: you can redistribute it and/or modify
# it under the terms of the GNU Library General Public License as
# published by the Free Software Foundation, either version 2 of
# the License, or (at your option) any later version.
#
# vsc-base is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public License
# along with vsc-base. If not, see <http://www.gnu.org/licenses/>.
##
"""
Test utilities.

@author: Kenneth Hoste (Ghent University)
"""

import re
import sys
from cStringIO import StringIO
from unittest import TestCase


class EnhancedTestCase(TestCase):
    """Enhanced test case, provides extra functionality (e.g. an assertErrorRegex method)."""

    def setUp(self):
        """Prepare test case."""
        super(EnhancedTestCase, self).setUp()
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
            str_args = ', '.join(map(str, args) + str_kwargs)
            self.assertTrue(False, "Expected errors with %s(%s) call should occur" % (call.__name__, str_args))
        except error, err:
            msg = self.convert_exception_to_str(err)
            if isinstance(regex, basestring):
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

    def tearDown(self):
        """Cleanup after running a test."""
        self.mock_stdout(False)
        self.mock_stderr(False)
        super(EnhancedTestCase, self).tearDown()
