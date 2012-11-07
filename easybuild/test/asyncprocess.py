##
# Copyright 2012 Ghent University
# Copyright 2012 Toon Willems
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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
import os
from unittest import TestCase, TestSuite

import easybuild.tools.asyncprocess as p
from easybuild.tools.asyncprocess import Popen


class AsyncProcessTest(TestCase):
    """ Testcase for asyncprocess """

    def setUp(self):
        """ setup a basic shell """
        self.shell = Popen('sh', stdin=p.PIPE, stdout=p.PIPE, shell=True, executable='/bin/bash')
        self.cwd = os.getcwd()

    def runTest(self):
        """ try echoing some text and see if it comes back out """
        p.send_all(self.shell, "echo hello\n")
        self.assertEqual(p.recv_some(self.shell), "hello\n")

        p.send_all(self.shell, "echo hello world\n")
        self.assertEqual(p.recv_some(self.shell), "hello world\n")

        p.send_all(self.shell, "exit\n")
        self.assertEqual("", p.recv_some(self.shell, e=0))
        self.assertRaises(Exception, p.recv_some, self.shell)

    def tearDown(self):
        """cleanup"""
        os.chdir(self.cwd)

def suite():
    """ returns all the testcases in this module """
    return TestSuite([AsyncProcessTest()])

