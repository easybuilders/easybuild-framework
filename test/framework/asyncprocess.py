##
# Copyright 2012-2025 Ghent University
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
Unit tests for asyncprocess.py.

@author: Toon Willems (Ghent University)
"""

import sys
import time
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

import easybuild.tools.asyncprocess as p
from easybuild.tools.asyncprocess import Popen
from easybuild.tools.run import subprocess_terminate


class AsyncProcessTest(EnhancedTestCase):
    """ Testcase for asyncprocess """

    def setUp(self):
        """ setup a basic shell """
        super().setUp()
        self.shell = Popen('sh', stdin=p.PIPE, stdout=p.PIPE, shell=True, executable='/bin/bash')

    def test_echo_between_process(self):
        """ try echoing some text and see if it comes back out """
        p.send_all(self.shell, "echo hello\n")
        time.sleep(0.1)
        self.assertEqual(p.recv_some(self.shell), b'hello\n')

        p.send_all(self.shell, "echo hello world\n")
        time.sleep(0.1)
        self.assertEqual(p.recv_some(self.shell), b'hello world\n')

        p.send_all(self.shell, "exit\n")
        time.sleep(0.1)
        self.assertEqual(b'', p.recv_some(self.shell, e=0))
        self.assertRaises(Exception, p.recv_some, self.shell)

    def tearDown(self):
        """cleanup"""
        subprocess_terminate(self.shell, timeout=1)
        super().tearDown()


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(AsyncProcessTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
