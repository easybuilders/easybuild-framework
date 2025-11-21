# #
# Copyright 2014-2025 Ghent University
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
# #
"""
Unit tests for ModulesTool class.

@author: Stijn De Weirdt (Ghent University)
"""
import os
import re
import stat
import sys

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.base import fancylogger
from easybuild.tools import modules, LooseVersion
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file, which, write_file
from easybuild.tools.modules import EnvironmentModules, Lmod
from test.framework.utilities import init_config


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


class ModulesToolTest(EnhancedTestCase):
    """ Testcase for ModulesTool """

    def setUp(self):
        """Testcase setup."""
        super().setUp()

        # keep track of original 'module' function definition so we can restore it
        self.orig_module = os.environ.get('module', None)

    def test_mock(self):
        """Test the mock module"""
        os.environ['module'] = "() {  eval `/bin/echo $*`\n}"

        # ue empty mod_path list, otherwise the install_path is called
        mmt = MockModulesTool(mod_paths=[], testing=True)

        # the version of the MMT is the commandline option
        self.assertEqual(mmt.version, LooseVersion(MockModulesTool.VERSION_OPTION))

        cmd_abspath = which(MockModulesTool.COMMAND)

        # make sure absolute path of module command is being used
        self.assertEqual(mmt.cmd, cmd_abspath)

    def test_environment_command(self):
        """Test setting cmd via enviroment"""
        os.environ['module'] = "() { %s $*\n}" % BrokenMockModulesTool.COMMAND

        try:
            bmmt = BrokenMockModulesTool(mod_paths=[], testing=True)
            # should never get here
            self.fail('BrokenMockModulesTool should fail')
        except EasyBuildError as err:
            err_msg = "command is not available"
            self.assertIn(err_msg, str(err))

        os.environ[BrokenMockModulesTool.COMMAND_ENVIRONMENT] = MockModulesTool.COMMAND
        os.environ['module'] = "() { /bin/echo $*\n}"
        bmmt = BrokenMockModulesTool(mod_paths=[], testing=True)
        cmd_abspath = which(MockModulesTool.COMMAND)

        self.assertEqual(bmmt.version, LooseVersion(MockModulesTool.VERSION_OPTION))
        self.assertEqual(bmmt.cmd, cmd_abspath)

        # clean it up
        del os.environ[BrokenMockModulesTool.COMMAND_ENVIRONMENT]

    def test_module_mismatch(self):
        """Test whether mismatch detection between modules tool and 'module' function works."""
        # redefine 'module' function (deliberate mismatch with used module command in MockModulesTool)
        os.environ['module'] = "() {  eval `/tmp/Modules/$MODULE_VERSION/bin/modulecmd bash $*`\n}"
        error_regex = ".*pattern .* not found in defined 'module' function"
        self.assertErrorRegex(EasyBuildError, error_regex, MockModulesTool, testing=True)

        # check whether escaping error by allowing mismatch via build options works
        build_options = {
            'allow_modules_tool_mismatch': True,
        }
        init_config(build_options=build_options)

        fancylogger.logToFile(self.logfile)

        mt = MockModulesTool(testing=True)
        logtxt = read_file(self.logfile)
        warn_regex = re.compile("WARNING .*pattern .* not found in defined 'module' function")
        self.assertTrue(warn_regex.search(logtxt), "Found pattern '%s' in: %s" % (warn_regex.pattern, logtxt))

        # redefine 'module' function with correct module command
        os.environ['module'] = "() {  eval `/bin/echo $*`\n}"
        mt = MockModulesTool(testing=True)
        self.assertIsInstance(mt.loaded_modules(), list)  # dummy usage

        # a warning should be logged if the 'module' function is undefined
        del os.environ['module']
        mt = MockModulesTool(testing=True)
        logtxt = read_file(self.logfile)
        warn_regex = re.compile("WARNING No 'module' function defined, can't check if it matches .*")
        self.assertTrue(warn_regex.search(logtxt), "Pattern %s found in %s" % (warn_regex.pattern, logtxt))

        fancylogger.logToFile(self.logfile, enable=False)

    def test_lmod_specific(self):
        """Lmod-specific test (skipped unless Lmod is used as modules tool)."""
        lmod_abspath = which(Lmod.COMMAND)
        # only run this test if 'lmod' is available in $PATH
        if lmod_abspath is not None:
            build_options = {
                'allow_modules_tool_mismatch': True,
                'update_modules_tool_cache': True,
            }
            init_config(build_options=build_options)

            lmod = Lmod(testing=True)
            self.assertTrue(os.path.samefile(lmod.cmd, lmod_abspath))

            # drop any location where 'lmod' or 'spider' can be found from $PATH
            paths = os.environ.get('PATH', '').split(os.pathsep)
            new_paths = []
            for path in paths:
                lmod_cand_path = os.path.join(path, Lmod.COMMAND)
                spider_cand_path = os.path.join(path, 'spider')
                if not os.path.isfile(lmod_cand_path) and not os.path.isfile(spider_cand_path):
                    new_paths.append(path)
            os.environ['PATH'] = os.pathsep.join(new_paths)

            # make sure $MODULEPATH contains path that provides some modules
            os.environ['MODULEPATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))

            # initialize Lmod modules tool, pass (fake) full path to 'lmod' via $LMOD_CMD
            fake_path = os.path.join(self.test_installpath, 'lmod')
            fake_lmod_txt = '\n'.join([
                '#!/bin/bash',
                'echo "Modules based on Lua: Version %s " >&2' % Lmod.DEPR_VERSION,
                'echo "os.environ[\'FOO\'] = \'foo\'"',
            ])
            write_file(fake_path, fake_lmod_txt)
            os.chmod(fake_path, stat.S_IRUSR | stat.S_IXUSR)
            os.environ['LMOD_CMD'] = fake_path
            init_config(build_options=build_options)
            lmod = Lmod(testing=True)
            self.assertTrue(os.path.samefile(lmod.cmd, fake_path))

            # use correct full path for 'lmod' via $LMOD_CMD
            os.environ['LMOD_CMD'] = lmod_abspath
            init_config(build_options=build_options)
            lmod = Lmod(testing=True)

            # obtain list of availabe modules, should be non-empty
            self.assertTrue(lmod.available(), "List of available modules obtained using Lmod is non-empty")

            # test updating local spider cache (but don't actually update the local cache file!)
            self.assertTrue(lmod.update(), "Updated local Lmod spider cache is non-empty")

    def test_environment_modules_specific(self):
        """Environment Modules-specific test (skipped unless installed)."""
        modulecmd_abspath = which(EnvironmentModules.COMMAND)
        # only run this test if 'modulecmd.tcl' is installed
        if modulecmd_abspath is not None:
            # redefine 'module' and '_module_raw' function (deliberate mismatch with used module
            # command in EnvironmentModules)
            os.environ['_module_raw'] = "() {  eval `/usr/share/Modules/libexec/foo.tcl' bash $*`;\n}"
            os.environ['module'] = "() {  _module_raw \"$@\" 2>&1;\n}"
            error_regex = ".*pattern .* not found in defined 'module' function"
            self.assertErrorRegex(EasyBuildError, error_regex, EnvironmentModules, testing=True)

            # redefine '_module_raw' function with correct module command
            os.environ['_module_raw'] = "() {  eval `/usr/share/Modules/libexec/modulecmd.tcl' bash $*`;\n}"
            mt = EnvironmentModules(testing=True)
            self.assertIsInstance(mt.loaded_modules(), list)  # dummy usage

            # test updating module cache
            test_modulepath = os.path.join(self.test_installpath, 'modules', 'all')
            os.environ['MODULEPATH'] = test_modulepath
            test_module_dir = os.path.join(test_modulepath, 'test')
            test_module_file = os.path.join(test_module_dir, '1.2.3')
            write_file(test_module_file, '#%Module')
            build_options = {
                'update_modules_tool_cache': True,
            }
            init_config(build_options=build_options)
            mt = EnvironmentModules(testing=True)
            out = mt.update()
            os.remove(test_module_file)
            os.rmdir(test_module_dir)

            # test cache file has been created if module tool supports it
            if LooseVersion(mt.version) >= LooseVersion('5.3.0'):
                cache_fp = os.path.join(test_modulepath, '.modulecache')
                expected = "Creating %s\n" % cache_fp
                self.assertEqual(expected, out, "Module cache created")
                self.assertTrue(os.path.exists(cache_fp))
                os.remove(cache_fp)

            # initialize Environment Modules tool with non-official version number
            # pass (fake) full path to 'modulecmd.tcl' via $MODULES_CMD
            fake_path = os.path.join(self.test_installpath, 'libexec', 'modulecmd.tcl')
            fake_modulecmd_txt = '\n'.join([
                '#!/bin/bash',
                'echo "Modules Release 5.3.1+unload-188-g14b6b59b (2023-10-21)" >&2',
                'echo "os.environ[\'FOO\'] = \'foo\'"',
            ])
            write_file(fake_path, fake_modulecmd_txt)
            os.chmod(fake_path, stat.S_IRUSR | stat.S_IXUSR)
            os.environ['_module_raw'] = "() {  eval `%s' bash $*`;\n}" % fake_path
            os.environ['MODULES_CMD'] = fake_path
            EnvironmentModules.COMMAND = fake_path
            mt = EnvironmentModules(testing=True)
            self.assertTrue(os.path.samefile(mt.cmd, fake_path), "%s - %s" % (mt.cmd, fake_path))

    def tearDown(self):
        """Testcase cleanup."""
        super().tearDown()

        # restore 'module' function
        if self.orig_module is not None:
            os.environ['module'] = self.orig_module
        else:
            os.environ.pop('module', None)


def suite(loader=None):
    """ returns all the testcases in this module """
    if loader:
        return loader.loadTestsFromTestCase(ModulesToolTest)
    else:
        return TestLoaderFiltered().loadTestsFromTestCase(ModulesToolTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
