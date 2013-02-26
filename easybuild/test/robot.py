##
# Copyright 2012-2013 Ghent University
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
"""
Unit tests for robot (dependency resolution).

@author: Toon Willems (Ghent University)
"""

import os
from copy import deepcopy
from unittest import TestCase, TestSuite
from unittest import main as unittestmain

import easybuild.tools.modules as modules
import easybuild.main as main
from easybuild.test.utilities import find_full_path
from easybuild.tools.build_log import EasyBuildError, get_log

orig_modules = modules.Modules
orig_main_modules = main.Modules


class MockModule(modules.Modules):
    """ MockModule class, allows for controlling what Modules() will return """

    def available(self, *args):
        """ no module should be available """
        return []


class RobotTest(TestCase):
    """ Testcase for the robot dependency resolution """

    def setUp(self):
        """ dynamically replace Modules class with MockModule """
        # replace Modules class with something we have control over
        modules.Modules = MockModule
        main.Modules = MockModule

        self.log = get_log("RobotTest")
        main.log = get_log("main")  # redefine the main log when calling the main functions directly

        self.cwd = os.getcwd()

        self.base_easyconfig_dir = find_full_path(os.path.join("easybuild", "test", "easyconfigs"))
        self.assertTrue(self.base_easyconfig_dir)

    def runTest(self):
        """ Test with some basic testcases (also check if he can find dependencies inside the given directory """
        easyconfig = {
            'spec': '_',
            'module': ("name", "version"),
            'dependencies': []
        }
        res = main.resolve_dependencies([deepcopy(easyconfig)], None)
        self.assertEqual([easyconfig], res)

        easyconfig_dep = {
            'spec': '_',
            'module': ("name", "version"),
            'dependencies': [('gzip', '1.4')]
        }
        res = main.resolve_dependencies([deepcopy(easyconfig_dep)], self.base_easyconfig_dir)
        # Dependency should be found
        self.assertEqual(len(res), 2)

        # here we have include a Dependency in the easyconfig list
        easyconfig['module'] = ("gzip", "1.4")

        res = main.resolve_dependencies([deepcopy(easyconfig_dep), deepcopy(easyconfig)], None)
        # all dependencies should be resolved
        self.assertEqual(0, sum(len(ec['dependencies']) for ec in res))

        # this should not resolve (cannot find gzip-1.4.eb)
        self.assertRaises(EasyBuildError, main.resolve_dependencies, [deepcopy(easyconfig_dep)], None)

        # test if dependencies of an automatically found file are also loaded
        easyconfig_dep['dependencies'] = [('gzip', "1.4-GCC-4.6.3")]
        res = main.resolve_dependencies([deepcopy(easyconfig_dep)], self.base_easyconfig_dir)

        # GCC should be first (required by gzip dependency)
        self.assertEqual(('GCC', '4.6.3'), res[0]['module'])
        self.assertEqual(('name', 'version'), res[-1]['module'])


    def tearDown(self):
        """ reset the Modules back to its original """
        modules.Modules = orig_modules
        main.Modules = orig_main_modules
        os.chdir(self.cwd)


def suite():
    """ returns all the testcases in this module """
    return TestSuite([RobotTest()])

if __name__ == '__main__':
    unittestmain()
