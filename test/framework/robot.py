# #
# Copyright 2012-2014 Ghent University
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
Unit tests for robot (dependency resolution).

@author: Toon Willems (Ghent University)
"""

import os
from copy import deepcopy
from unittest import TestCase, TestLoader
from unittest import main as unittestmain
from vsc import fancylogger

import easybuild.tools.options as eboptions
import easybuild.framework.easyconfig.tools as ectools
from easybuild.framework.easyconfig.tools import resolve_dependencies, skip_available
from easybuild.tools import config, modules
from easybuild.tools.build_log import EasyBuildError
from test.framework.utilities import find_full_path

orig_modules_tool = modules.modules_tool
orig_main_modules_tool = ectools.modules_tool


class MockModule(modules.ModulesTool):
    """ MockModule class, allows for controlling what modules_tool() will return """
    COMMAND = 'echo'
    VERSION_OPTION = '1.0'
    VERSION_REGEXP = r'(?P<version>\d\S*)'
    # redirect to stderr, ignore 'echo python' ($0 and $1)
    COMMAND_SHELL = ["bash", "-c", "echo $2 $3 $4 1>&2"]

    avail_modules = []

    def available(self, *args):
        """ no module should be available """
        return self.avail_modules

def mock_module(mod_paths=None):
    """Get mock module instance."""
    return MockModule(mod_paths=mod_paths)


class RobotTest(TestCase):
    """ Testcase for the robot dependency resolution """

    def setUp(self):
        """Set up everything for a unit test."""
        # initialize configuration so config.get_modules_tool function works
        eb_go = eboptions.parse_options()
        config.init(eb_go.options, eb_go.get_options_by_section('config'))

        # replace Modules class with something we have control over
        config.modules_tool = mock_module
        ectools.modules_tool = mock_module

        self.log = fancylogger.getLogger("RobotTest", fname=False)

        self.cwd = os.getcwd()

        self.base_easyconfig_dir = find_full_path(os.path.join("test", "framework", "easyconfigs"))
        self.assertTrue(self.base_easyconfig_dir)

    def test_resolve_dependencies(self):
        """ Test with some basic testcases (also check if he can find dependencies inside the given directory """
        easyconfig = {
            'spec': '_',
            'module': 'name/version',
            'dependencies': []
        }
        build_options = {
            'ignore_osdeps': True,
            'robot_path': None,
            'validate': False,
        }
        res = resolve_dependencies([deepcopy(easyconfig)], build_options=build_options)
        self.assertEqual([easyconfig], res)

        easyconfig_dep = {
            'ec': {
                'name': 'foo',
                'version': '1.2.3',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
            },
            'spec': '_',
            'module': 'foo/1.2.3',
            'dependencies': [{
                'name': 'gzip',
                'version': '1.4',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
                'dummy': True,
            }],
            'parsed': True,
        }
        build_options.update({'robot_path': self.base_easyconfig_dir})
        res = resolve_dependencies([deepcopy(easyconfig_dep)], build_options=build_options)
        # dependency should be found, order should be correct
        self.assertEqual(len(res), 2)
        self.assertEqual('gzip/1.4', res[0]['module'])
        self.assertEqual('foo/1.2.3', res[-1]['module'])

        # here we have include a Dependency in the easyconfig list
        easyconfig['module'] = 'gzip/1.4'

        ecs = [deepcopy(easyconfig_dep), deepcopy(easyconfig)]
        build_options.update({'robot_path': None})
        res = resolve_dependencies(ecs, build_options=build_options)
        # all dependencies should be resolved
        self.assertEqual(0, sum(len(ec['dependencies']) for ec in res))

        # this should not resolve (cannot find gzip-1.4.eb)
        ecs = [deepcopy(easyconfig_dep)]
        self.assertRaises(EasyBuildError, resolve_dependencies, ecs, build_options=build_options)

        # test if dependencies of an automatically found file are also loaded
        easyconfig_dep['dependencies'] = [{
            'name': 'gzip',
            'version': '1.4',
            'versionsuffix': '',
            'toolchain': {'name': 'GCC', 'version': '4.6.3'},
            'dummy': True,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        build_options.update({'robot_path': self.base_easyconfig_dir})
        res = resolve_dependencies([deepcopy(easyconfig_dep)], build_options=build_options)

        # GCC should be first (required by gzip dependency)
        self.assertEqual('GCC/4.6.3', res[0]['module'])
        self.assertEqual('foo/1.2.3', res[-1]['module'])

        # make sure that only missing stuff is built, and that available modules are not rebuilt
        # monkey patch MockModule to pretend that all ingredients required for goolf-1.4.10 toolchain are present
        MockModule.avail_modules = [
            'GCC/4.7.2',
            'OpenMPI/1.6.4-GCC-4.7.2',
            'OpenBLAS/0.2.6-gompi-1.4.10-LAPACK-3.4.2',
            'FFTW/3.3.3-gompi-1.4.10',
            'ScaLAPACK/2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2',
        ]

        easyconfig_dep['dependencies'] = [{
            'name': 'goolf',
            'version': '1.4.10',
            'versionsuffix': '',
            'toolchain': {'name': 'dummy', 'version': 'dummy'},
            'dummy': True,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        res = resolve_dependencies(ecs, build_options=build_options)

        # there should only be two retained builds, i.e. the software itself and the goolf toolchain as dep
        self.assertEqual(len(res), 2)
        # goolf should be first, the software itself second
        self.assertEqual('goolf/1.4.10', res[0]['module'])
        self.assertEqual('foo/1.2.3', res[1]['module'])

        # force doesn't trigger rebuild of all deps, but listed easyconfigs for which a module is available are rebuilt
        build_options.update({'force': True})
        easyconfig['module'] = 'this/is/already/there'
        MockModule.avail_modules.append('this/is/already/there')
        ecs = [deepcopy(easyconfig_dep), deepcopy(easyconfig)]
        res = resolve_dependencies(ecs, build_options=build_options)

        # there should only be three retained builds, foo + goolf dep and the additional build (even though a module is available)
        self.assertEqual(len(res), 3)
        # goolf should be first, the software itself second
        self.assertEqual('this/is/already/there', res[0]['module'])
        self.assertEqual('goolf/1.4.10', res[1]['module'])
        self.assertEqual('foo/1.2.3', res[2]['module'])

        # build that are listed but already have a module available are not retained without force
        build_options.update({'force': False})
        newecs = skip_available(ecs, testing=True)  # skip available builds since force is not enabled
        res = resolve_dependencies(newecs, build_options=build_options)
        self.assertEqual(len(res), 2)
        self.assertEqual('goolf/1.4.10', res[0]['module'])
        self.assertEqual('foo/1.2.3', res[1]['module'])

        # with retain_all_deps enabled, all dependencies ae retained
        build_options.update({'retain_all_deps': True})
        ecs = [deepcopy(easyconfig_dep)]
        newecs = skip_available(ecs, testing=True)  # skip available builds since force is not enabled
        res = resolve_dependencies(newecs, build_options=build_options)
        self.assertEqual(len(res), 9)
        self.assertEqual('GCC/4.7.2', res[0]['module'])
        self.assertEqual('goolf/1.4.10', res[-2]['module'])
        self.assertEqual('foo/1.2.3', res[-1]['module'])

        build_options.update({'retain_all_deps': False})

        # provide even less goolf ingredients (no OpenBLAS/ScaLAPACK), make sure the numbers add up
        MockModule.avail_modules = [
            'GCC/4.7.2',
            'OpenMPI/1.6.4-GCC-4.7.2',
            'gompi/1.4.10',
            'FFTW/3.3.3-gompi-1.4.10',
        ]

        easyconfig_dep['dependencies'] = [{
            'name': 'goolf',
            'version': '1.4.10',
            'versionsuffix': '',
            'toolchain': {'name': 'dummy', 'version': 'dummy'},
            'dummy': True,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        res = resolve_dependencies([deepcopy(easyconfig_dep)], build_options=build_options)

        # there should only be two retained builds, i.e. the software itself and the goolf toolchain as dep
        self.assertEqual(len(res), 4)
        # goolf should be first, the software itself second
        self.assertEqual('OpenBLAS/0.2.6-gompi-1.4.10-LAPACK-3.4.2', res[0]['module'])
        self.assertEqual('ScaLAPACK/2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2', res[1]['module'])
        self.assertEqual('goolf/1.4.10', res[2]['module'])
        self.assertEqual('foo/1.2.3', res[3]['module'])

    def tearDown(self):
        """ reset the Modules back to its original """
        config.modules_tool = orig_modules_tool
        ectools.modules_tool = orig_main_modules_tool
        os.chdir(self.cwd)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(RobotTest)

if __name__ == '__main__':
    unittestmain()
