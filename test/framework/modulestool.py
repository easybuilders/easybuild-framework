# #
# Copyright 2014-2014 Ghent University
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
# #
"""
Unit tests for ModulesTool class.

@author: Stijn De Weirdt (Ghent University)
"""
import os
import re
import tempfile
from vsc import fancylogger

from unittest import main as unittestmain
from unittest import TestCase, TestLoader
from distutils.version import StrictVersion

import easybuild.tools.options as eboptions
from easybuild.tools import config, modules
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import which


class MockModulesTool(modules.ModulesTool):
    """ MockModule class"""
    COMMAND = 'echo'
    VERSION_OPTION = '1.0'
    VERSION_REGEXP = r'(?P<version>\d\S*)'
    # redirect to stderr, ignore 'echo python' ($0 and $1)
    COMMAND_SHELL = ["bash", "-c", "echo $2 $3 $4 1>&2"]


class BrokenMockModulesTool(MockModulesTool):
    """MockModulesTool class that is broken unless environment command is set"""
    COMMAND = '/does/not/exist'
    COMMAND_ENVIRONMENT = 'BMMT_CMD'


class ModulesToolTest(TestCase):
    """ Testcase for ModulesTool """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def setUp(self):
        """Testcase setup."""
        # initialize configuration so config.get_modules_tool function works
        eb_go = eboptions.parse_options()
        config.init(eb_go.options, eb_go.get_options_by_section('config'))

        fd, self.log_fn = tempfile.mkstemp(prefix='easybuild-tests-modules-tool-', suffix='.log')
        os.close(fd)
        os.remove(self.log_fn)
        fancylogger.logToFile(self.log_fn)

        # keep track of original 'module' function definition so we can restore it
        self.orig_module = os.environ['module']

    def tearDown(self):
        """Testcase cleanup."""
        fancylogger.logToFile(self.log_fn, enable=False)
        os.remove(self.log_fn)

        # restore
        os.environ['module'] = self.orig_module

    def test_mock(self):
        """Test the mock module"""
        os.environ['module'] = "() {  eval `/bin/echo $*`\n}"

        # ue empty mod_path list, otherwise the install_path is called
        mmt = MockModulesTool(mod_paths=[])

        # the version of the MMT is the commandline option
        self.assertEqual(mmt.version, StrictVersion(MockModulesTool.VERSION_OPTION))

        cmd_abspath = which(MockModulesTool.COMMAND)

        # make sure absolute path of module command is being used
        self.assertEqual(mmt.cmd, cmd_abspath)

    def test_environment_command(self):
        """Test setting cmd via enviroment"""
        os.environ['module'] = "() { %s $*\n}" % BrokenMockModulesTool.COMMAND

        try:
            bmmt = BrokenMockModulesTool(mod_paths=[])
            # should never get here
            self.assertTrue(False, 'BrokenMockModulesTool should fail')
        except EasyBuildError, err:
            self.assertTrue('command is not available' in str(err))

        os.environ[BrokenMockModulesTool.COMMAND_ENVIRONMENT] = MockModulesTool.COMMAND
        os.environ['module'] = "() { /bin/echo $*\n}"
        bmmt = BrokenMockModulesTool(mod_paths=[])
        cmd_abspath = which(MockModulesTool.COMMAND)

        self.assertEqual(bmmt.version, StrictVersion(MockModulesTool.VERSION_OPTION))
        self.assertEqual(bmmt.cmd, cmd_abspath)

        # clean it up
        del os.environ[BrokenMockModulesTool.COMMAND_ENVIRONMENT]

    def test_module_mismatch(self):
        """Test whether mismatch detection between modules tool and 'module' function works."""
        # redefine 'module' function (deliberate mismatch with used module command in MockModulesTool)
        os.environ['module'] = "() {  eval `/Users/kehoste/Modules/$MODULE_VERSION/bin/modulecmd bash $*`\n}"
        self.assertErrorRegex(EasyBuildError, ".*command .* not found in defined 'module' function", MockModulesTool)

        # redefine 'module' function with correct module command
        os.environ['module'] = "() {  eval `/bin/echo $*`\n}"
        mt = MockModulesTool()
        self.assertTrue(isinstance(mt.loaded_modules(), list))  # dummy usage

        # a warning should be logged if the 'module' function is undefined
        del os.environ['module']
        mt = MockModulesTool()
        f = open(self.log_fn, 'r')
        logtxt = f.read()
        f.close()
        warning_regex = re.compile("WARNING 'module' function not defined, can't verify whether modules tool matches it.")
        self.assertTrue(warning_regex.search(logtxt))

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ModulesToolTest)


if __name__ == '__main__':
    unittestmain()

