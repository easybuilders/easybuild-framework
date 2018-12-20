# #
# Copyright 2012-2018 Ghent University
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
Unit tests for robot (dependency resolution).

@author: Toon Willems (Ghent University)
"""

import os
import re
import shutil
import sys
import tempfile
from copy import deepcopy
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.framework.easyconfig.easyconfig as ecec
import easybuild.framework.easyconfig.tools as ectools
import easybuild.tools.build_log
import easybuild.tools.robot as robot
from easybuild.framework.easyconfig.easyconfig import process_easyconfig, EasyConfig
from easybuild.framework.easyconfig.tools import alt_easyconfig_paths, find_resolved_modules, parse_easyconfigs
from easybuild.framework.easyconfig.tweak import tweak
from easybuild.framework.easyconfig.easyconfig import get_toolchain_hierarchy
from easybuild.framework.easyconfig.easyconfig import robot_find_subtoolchain_for_dep
from easybuild.framework.easyconfig.tools import skip_available
from easybuild.tools import config, modules
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.filetools import copy_file, mkdir, read_file, write_file
from easybuild.tools.github import fetch_github_token
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import invalidate_module_caches_for, reset_module_caches
from easybuild.tools.robot import check_conflicts, det_robot_path, resolve_dependencies
from test.framework.utilities import find_full_path


# test account, for which a token is available
GITHUB_TEST_ACCOUNT = 'easybuild_test'

ORIG_MODULES_TOOL = modules.modules_tool
ORIG_ECEC_MODULES_TOOL = ecec.modules_tool
ORIG_ECTOOLS_MODULES_TOOL = ectools.modules_tool
ORIG_MODULE_FUNCTION = os.environ.get('module', None)


class MockModule(modules.ModulesTool):
    """ MockModule class, allows for controlling what modules_tool() will return """
    COMMAND = 'echo'
    VERSION_OPTION = '1.0'
    VERSION_REGEXP = r'(?P<version>\d\S*)'
    # redirect to stderr, ignore 'echo python' ($0 and $1)
    COMMAND_SHELL = ["bash", "-c", "echo $2 $3 $4 1>&2"]

    avail_modules = []

    def available(self, *args, **kwargs):
        """Dummy implementation of available."""
        return self.avail_modules

    def show(self, modname):
        """Dummy implementation of show, which includes full path to (available or hidden) module files."""
        if modname in self.avail_modules or os.path.basename(modname).startswith('.'):
            txt = '  %s:' % os.path.join('/tmp', modname)
        else:
            txt = 'Module %s not found' % modname
        return txt


def mock_module(mod_paths=None):
    """Get mock module instance."""
    return MockModule(mod_paths=mod_paths, testing=True)


class RobotTest(EnhancedTestCase):
    """ Testcase for the robot dependency resolution """

    def install_mock_module(self):
        """Install MockModule as modules tool."""
        # replace Modules class with something we have control over
        config.modules_tool = mock_module
        ectools.modules_tool = mock_module
        ecec.modules_tool = mock_module
        robot.modules_tool = mock_module
        os.environ['module'] = "() {  eval `/bin/echo $*`\n}"
        self.modtool = mock_module()

    def setUp(self):
        """Set up test."""
        super(RobotTest, self).setUp()
        self.github_token = fetch_github_token(GITHUB_TEST_ACCOUNT)
        self.orig_experimental = easybuild.framework.easyconfig.tools._log.experimental
        self.orig_modtool = self.modtool

    def tearDown(self):
        """Test cleanup."""
        super(RobotTest, self).tearDown()

        # restore log.experimental
        easybuild.framework.easyconfig.tools._log.experimental = self.orig_experimental

        # restore original modules tool, it may have been tampered with
        config.modules_tool = ORIG_MODULES_TOOL
        ectools.modules_tool = ORIG_ECTOOLS_MODULES_TOOL
        ecec.modules_tool = ORIG_ECEC_MODULES_TOOL
        if ORIG_MODULE_FUNCTION is None:
            if 'module' in os.environ:
                del os.environ['module']
        else:
            os.environ['module'] = ORIG_MODULE_FUNCTION
        self.modtool = self.orig_modtool

    def test_resolve_dependencies(self):
        """ Test with some basic testcases (also check if he can find dependencies inside the given directory """
        self.install_mock_module()

        base_easyconfig_dir = find_full_path(os.path.join('test', 'framework', 'easyconfigs', 'test_ecs'))
        self.assertTrue(base_easyconfig_dir)

        easyconfig = {
            'spec': '_',
            'full_mod_name': 'name/version',
            'short_mod_name': 'name/version',
            'dependencies': []
        }
        build_options = {
            'allow_modules_tool_mismatch': True,
            'external_modules_metadata': ConfigObj(),
            'robot_path': None,
            'validate': False,
        }
        init_config(build_options=build_options)
        res = resolve_dependencies([deepcopy(easyconfig)], self.modtool)
        self.assertEqual([easyconfig], res)

        easyconfig_dep = {
            'ec': {
                'name': 'foo',
                'version': '1.2.3',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
            },
            'spec': '_',
            'short_mod_name': 'foo/1.2.3',
            'full_mod_name': 'foo/1.2.3',
            'dependencies': [{
                'name': 'gzip',
                'version': '1.4',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
                'dummy': True,
                'hidden': False,
            }],
            'parsed': True,
        }
        build_options.update({'robot': True, 'robot_path': base_easyconfig_dir})
        init_config(build_options=build_options)
        res = resolve_dependencies([deepcopy(easyconfig_dep)], self.modtool)
        # dependency should be found, order should be correct
        self.assertEqual(len(res), 2)
        self.assertEqual('gzip/1.4', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[-1]['full_mod_name'])

        # hidden dependencies are found too, but only retained if they're not available (or forced to be retained
        hidden_dep = {
            'name': 'toy',
            'version': '0.0',
            'versionsuffix': '-deps',
            'toolchain': {'name': 'dummy', 'version': 'dummy'},
            'dummy': True,
            'hidden': True,
        }
        easyconfig_moredeps = deepcopy(easyconfig_dep)
        easyconfig_moredeps['dependencies'].append(hidden_dep)
        easyconfig_moredeps['hiddendependencies'] = [hidden_dep]

        # toy/.0.0-deps is available and thus should be omitted
        res = resolve_dependencies([deepcopy(easyconfig_moredeps)], self.modtool)
        self.assertEqual(len(res), 2)
        full_mod_names = [ec['full_mod_name'] for ec in res]
        self.assertFalse('toy/.0.0-deps' in full_mod_names)

        res = resolve_dependencies([deepcopy(easyconfig_moredeps)], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 4)  # hidden dep toy/.0.0-deps (+1) depends on (fake) intel/2018a (+1)
        self.assertEqual('gzip/1.4', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[-1]['full_mod_name'])
        full_mod_names = [ec['full_mod_name'] for ec in res]
        self.assertTrue('toy/.0.0-deps' in full_mod_names)
        self.assertTrue('intel/2018a' in full_mod_names)

        # here we have included a dependency in the easyconfig list
        easyconfig['full_mod_name'] = 'gzip/1.4'

        ecs = [deepcopy(easyconfig_dep), deepcopy(easyconfig)]
        build_options.update({'robot_path': None})
        init_config(build_options=build_options)
        res = resolve_dependencies(ecs, self.modtool)
        # all dependencies should be resolved
        self.assertEqual(0, sum(len(ec['dependencies']) for ec in res))

        # this should not resolve (cannot find gzip-1.4.eb), both with and without robot enabled
        ecs = [deepcopy(easyconfig_dep)]
        msg = "Missing dependencies"
        self.assertErrorRegex(EasyBuildError, msg, resolve_dependencies, ecs, self.modtool)

        # test if dependencies of an automatically found file are also loaded
        easyconfig_dep['dependencies'] = [{
            'name': 'gzip',
            'version': '1.4',
            'versionsuffix': '',
            'toolchain': {'name': 'GCC', 'version': '4.6.3'},
            'dummy': True,
            'hidden': False,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        build_options.update({'robot_path': base_easyconfig_dir})
        init_config(build_options=build_options)
        res = resolve_dependencies([deepcopy(easyconfig_dep)], self.modtool)

        # GCC should be first (required by gzip dependency)
        self.assertEqual('GCC/4.6.3', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[-1]['full_mod_name'])

        # make sure that only missing stuff is built, and that available modules are not rebuilt
        # monkey patch MockModule to pretend that all ingredients required for foss-2018a toolchain are present
        MockModule.avail_modules = [
            'GCC/6.4.0-2.28',
            'OpenMPI/2.1.2-GCC-6.4.0-2.28',
            'OpenBLAS/0.2.20-GCC-6.4.0-2.28',
            'FFTW/3.3.7-gompi-2018a',
            'ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20',
        ]

        easyconfig_dep['dependencies'] = [{
            'name': 'foss',
            'version': '2018a',
            'versionsuffix': '',
            'toolchain': {'name': 'dummy', 'version': 'dummy'},
            'dummy': True,
            'hidden': False,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        res = resolve_dependencies(ecs, self.modtool)

        # there should only be two retained builds, i.e. the software itself and the foss toolchain as dep
        self.assertEqual(len(res), 2)
        # foss should be first, the software itself second
        self.assertEqual('foss/2018a', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[1]['full_mod_name'])

        # force doesn't trigger rebuild of all deps, but listed easyconfigs for which a module is available are rebuilt
        build_options.update({'force': True})
        init_config(build_options=build_options)
        easyconfig['full_mod_name'] = 'this/is/already/there'
        MockModule.avail_modules.append('this/is/already/there')
        ecs = [deepcopy(easyconfig_dep), deepcopy(easyconfig)]
        res = resolve_dependencies(ecs, self.modtool)

        # there should only be three retained builds:
        # foo + foss dep and the additional build (even though a module is available)
        self.assertEqual(len(res), 3)
        # foss should be first, the software itself second
        self.assertEqual('this/is/already/there', res[0]['full_mod_name'])
        self.assertEqual('foss/2018a', res[1]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[2]['full_mod_name'])

        # build that are listed but already have a module available are not retained without force
        build_options.update({'force': False})
        init_config(build_options=build_options)
        newecs = skip_available(ecs, self.modtool)  # skip available builds since force is not enabled
        res = resolve_dependencies(newecs, self.modtool)
        self.assertEqual(len(res), 2)
        self.assertEqual('foss/2018a', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[1]['full_mod_name'])

        # with retain_all_deps enabled, all dependencies ae retained
        build_options.update({'retain_all_deps': True})
        init_config(build_options=build_options)
        ecs = [deepcopy(easyconfig_dep)]
        newecs = skip_available(ecs, self.modtool)  # skip available builds since force is not enabled
        res = resolve_dependencies(newecs, self.modtool)
        self.assertEqual(len(res), 9)
        self.assertEqual('GCC/6.4.0-2.28', res[0]['full_mod_name'])
        self.assertEqual('foss/2018a', res[-2]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[-1]['full_mod_name'])

        build_options.update({'retain_all_deps': False})
        init_config(build_options=build_options)

        # provide even less foss ingredients (no OpenBLAS/ScaLAPACK), make sure the numbers add up
        MockModule.avail_modules = [
            'GCC/6.4.0-2.28',
            'OpenMPI/2.1.2-GCC-6.4.0-2.28',
            'gompi/2018a',
            'FFTW/3.3.7-gompi-2018a',
        ]

        easyconfig_dep['dependencies'] = [{
            'name': 'foss',
            'version': '2018a',
            'versionsuffix': '',
            'toolchain': {'name': 'dummy', 'version': 'dummy'},
            'dummy': True,
            'hidden': False,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        res = resolve_dependencies([deepcopy(easyconfig_dep)], self.modtool)

        # there should only be two retained builds, i.e. the software itself and the foss toolchain as dep
        self.assertEqual(len(res), 4)
        # foss should be first, the software itself second
        self.assertEqual('OpenBLAS/0.2.20-GCC-6.4.0-2.28', res[0]['full_mod_name'])
        self.assertEqual('ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20', res[1]['full_mod_name'])
        self.assertEqual('foss/2018a', res[2]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[3]['full_mod_name'])

    def test_resolve_dependencies_existing_modules(self):
        """Test order in case modules already being available."""
        def mkdepspec(name, version):
            """Create a dep spec with given name/version."""
            dep = {
                'name': name,
                'version': version,
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
                'dummy': True,
                'hidden': False,
                'short_mod_name': '%s/%s' % (name, version),
                'full_mod_name': '%s/%s' % (name, version),
            }
            return dep

        def mkspec(name, version, deps):
            """Create a spec with given name/version/deps."""
            spec = {
                'ec': {
                    'name': name,
                    'version': version,
                    'versionsuffix': '',
                    'toolchain': {'name': 'dummy', 'version': 'dummy'},
                },
                'spec': '_',
                'short_mod_name': '%s/%s' % (name, version),
                'full_mod_name': '%s/%s' % (name, version),
                'dependencies': [],
                'parsed': True,
            }
            for depname, depver in deps:
                spec['dependencies'].append(mkdepspec(depname, depver))

            return spec

        ecs = [
            mkspec('three', '3.0', [('twoone', '2.1'), ('one', '1.0')]),
            mkspec('four', '4.0', [('three', '3.0'), ('twoone', '2.1')]),
            mkspec('twoone', '2.1', [('one', '1.0'), ('two', '2.0')]),
            mkspec('two', '2.0', [('one', '1.0')]),
            mkspec('one', '1.0', []),
        ]
        expected = ['one/1.0', 'two/2.0', 'twoone/2.1', 'three/3.0', 'four/4.0']

        # order is correct if modules are not available yet
        res = resolve_dependencies(ecs, self.modtool)
        self.assertEqual([x['full_mod_name'] for x in res], expected)

        # precreate matching modules
        modpath = os.path.join(self.test_prefix, 'modules')
        mods = ['four/4.0', 'one/1.0', 'three/3.0', 'two/2.0', 'twooone/2.1']
        for mod in mods:
            write_file(os.path.join(modpath, mod), '#%Module\n')
        self.reset_modulepath([modpath])

        # order is correct even if modules are already available
        res = resolve_dependencies(ecs, self.modtool)
        self.assertEqual([x['full_mod_name'] for x in res], expected)

    def test_resolve_dependencies_minimal(self):
        """Test resolved dependencies with minimal toolchain."""

        # replace log.experimental with log.warning to allow experimental code
        easybuild.framework.easyconfig.tools._log.experimental = easybuild.framework.easyconfig.tools._log.warning

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        self.install_mock_module()

        init_config(build_options={
            'allow_modules_tool_mismatch': True,
            'minimal_toolchains': True,
            'use_existing_modules': True,
            'external_modules_metadata': ConfigObj(),
            'robot_path': test_easyconfigs,
            'valid_module_classes': module_classes(),
            'validate': False,
        })

        barec = os.path.join(self.test_prefix, 'bar-1.2.3-foss-2018a.eb')
        barec_lines = [
            "easyblock = 'ConfigureMake'",
            "name = 'bar'",
            "version = '1.2.3'",
            "homepage = 'http://example.com'",
            "description = 'foo'",
            # deliberately listing components of toolchain as dependencies without specifying subtoolchains,
            # to test resolving of dependencies with minimal toolchain
            # for each of these, we know test easyconfigs are available (which are required here)
            "dependencies = [",
            "   ('OpenMPI', '2.1.2'),",  # available with GCC/6.4.0-2.28
            "   ('OpenBLAS', '0.2.20'),",  # available with GCC/6.4.0-2.28
            "   ('ScaLAPACK', '2.0.2', '-OpenBLAS-0.2.20'),",  # available with gompi/2018a
            "   ('SQLite', '3.8.10.2'),",
            "]",
            # toolchain as list line, for easy modification later;
            # the use of %(version_minor)s here is mainly to check if templates are being handled correctly
            # (it doesn't make much sense, but it serves the purpose)
            "toolchain = {'name': 'foss', 'version': '%(version_minor)s018a'}",
        ]
        write_file(barec, '\n'.join(barec_lines))
        bar = process_easyconfig(barec)[0]

        # all modules in the dep graph, in order
        all_mods_ordered = [
            'GCC/6.4.0-2.28',
            'OpenBLAS/0.2.20-GCC-6.4.0-2.28',
            'hwloc/1.11.8-GCC-6.4.0-2.28',
            'OpenMPI/2.1.2-GCC-6.4.0-2.28',
            'SQLite/3.8.10.2-GCC-6.4.0-2.28',
            'gompi/2018a',
            'ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20',
            'FFTW/3.3.7-gompi-2018a',
            'foss/2018a',
            'bar/1.2.3-foss-2018a',
        ]

        # no modules available, so all dependencies are retained
        MockModule.avail_modules = []
        res = resolve_dependencies([bar], self.modtool)
        self.assertEqual(len(res), 10)
        self.assertEqual([x['full_mod_name'] for x in res], all_mods_ordered)

        MockModule.avail_modules = [
            'GCC/6.4.0-2.28',
            'gompi/2018a',
            'foss/2018a',
            'OpenMPI/2.1.2-GCC-6.4.0-2.28',
            'OpenBLAS/0.2.20-GCC-6.4.0-2.28',
            'ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20',
            'SQLite/3.8.10.2-GCC-6.4.0-2.28',
        ]

        # test resolving dependencies with minimal toolchain (rather than using foss/2018a for all of them)
        # existing modules are *not* taken into account when determining minimal subtoolchain, by default
        res = resolve_dependencies([bar], self.modtool)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['full_mod_name'], bar['ec'].full_mod_name)

        # test retaining all dependencies, regardless of whether modules are available or not
        res = resolve_dependencies([bar], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 10)
        mods = [x['full_mod_name'] for x in res]
        self.assertEqual(mods, all_mods_ordered)
        self.assertTrue('SQLite/3.8.10.2-GCC-6.4.0-2.28' in mods)

        # test taking into account existing modules
        # with an SQLite module with foss/2018a in place, this toolchain should be used rather than GCC/6.4.0-2.28
        MockModule.avail_modules = [
            'SQLite/3.8.10.2-foss-2018a',
        ]

        # parsed easyconfigs are cached, so clear the cache before reprocessing easyconfigs
        ecec._easyconfigs_cache.clear()

        bar = process_easyconfig(barec)[0]
        res = resolve_dependencies([bar], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 10)
        mods = [x['full_mod_name'] for x in res]
        self.assertTrue('SQLite/3.8.10.2-foss-2018a' in mods)
        self.assertFalse('SQLite/3.8.10.2-GCC-6.4.0-2.28' in mods)

        # Check whether having 2 version of dummy toolchain is ok
        # Clear easyconfig and toolchain caches
        ecec._easyconfigs_cache.clear()
        get_toolchain_hierarchy.clear()

        init_config(build_options={
            'allow_modules_tool_mismatch': True,
            'minimal_toolchains': True,
            'add_dummy_to_minimal_toolchains': True,
            'external_modules_metadata': ConfigObj(),
            'robot_path': test_easyconfigs,
            'valid_module_classes': module_classes(),
            'validate': False,
        })

        impi_txt = read_file(os.path.join(test_easyconfigs, 'i', 'impi', 'impi-5.1.2.150.eb'))
        self.assertTrue(re.search("^toolchain = {'name': 'dummy', 'version': ''}", impi_txt, re.M))
        gzip_txt = read_file(os.path.join(test_easyconfigs, 'g', 'gzip', 'gzip-1.4.eb'))
        self.assertTrue(re.search("^toolchain = {'name': 'dummy', 'version': 'dummy'}", gzip_txt, re.M))

        barec = os.path.join(self.test_prefix, 'bar-1.2.3-foss-2018a.eb')
        barec_lines = [
            "easyblock = 'ConfigureMake'",
            "name = 'bar'",
            "version = '1.2.3'",
            "homepage = 'http://example.com'",
            "description = 'foo'",
            # deliberately listing components of toolchain as dependencies without specifying subtoolchains,
            # to test resolving of dependencies with minimal toolchain
            # for each of these, we know test easyconfigs are available (which are required here)
            "dependencies = [",
            "   ('impi', '5.1.2.150'),",  # has toolchain ('dummy', '')
            "   ('gzip', '1.4'),",  # has toolchain ('dummy', 'dummy')
            "]",
            # toolchain as list line, for easy modification later
            "toolchain = {'name': 'foss', 'version': '2018a'}",
        ]
        write_file(barec, '\n'.join(barec_lines))
        bar = process_easyconfig(barec)[0]

        res = resolve_dependencies([bar], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 11)
        mods = [x['full_mod_name'] for x in res]
        self.assertTrue('impi/5.1.2.150' in mods)
        self.assertTrue('gzip/1.4' in mods)

    def test_resolve_dependencies_missing(self):
        """Test handling of missing dependencies in resolve_dependencies function."""

        self.install_mock_module()
        MockModule.avail_modules = []

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={'robot_path': [test_easyconfigs, self.test_prefix]})

        ec = {
            'ec': {
                'name': 'test',
                'version': '123',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
            },
            'spec': '_',
            'short_mod_name': 'test/123',
            'full_mod_name': 'test/123',
            'parsed': True,
            'dependencies': [{
                'name': 'somedep',
                'version': '4.5.6',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
                'dummy': True,
                'hidden': False,
                'short_mod_name': 'somedep/4.5.6',
                'full_mod_name': 'somedep/4.5.6',
            }],
        }

        error = "Missing dependencies: somedep/4.5.6 \(no easyconfig file or existing module found\)"
        self.assertErrorRegex(EasyBuildError, error, resolve_dependencies, [ec], self.modtool)

        # check behaviour if only module file is available
        MockModule.avail_modules = ['somedep/4.5.6']
        res = resolve_dependencies([ec], self.modtool)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['full_mod_name'], 'test/123')

        error = "Missing dependencies: somedep/4.5.6 \(no easyconfig file found in robot search path\)"
        self.assertErrorRegex(EasyBuildError, error, resolve_dependencies, [ec], self.modtool, retain_all_deps=True)

        res = resolve_dependencies([ec], self.modtool, retain_all_deps=True, raise_error_missing_ecs=False)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]['full_mod_name'], 'test/123')
        self.assertEqual(res[1]['full_mod_name'], 'somedep/4.5.6')

        # add easyconfig for dep to robot search path => resolve_dependencies should not complain anymore
        somedep_ectxt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'somedep'",
            "version = '4.5.6'",
            "homepage = 'https://example.com'",
            "description = 'some dep'",
            "toolchain = {'name': 'dummy', 'version': ''}",
        ])
        write_file(os.path.join(self.test_prefix, 'somedep-4.5.6.eb'), somedep_ectxt)

        res = resolve_dependencies([ec], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[1]['full_mod_name'], 'test/123')
        self.assertEqual(res[0]['full_mod_name'], 'somedep/4.5.6')

    def test_det_easyconfig_paths(self):
        """Test det_easyconfig_paths function (without --from-pr)."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        test_ec = 'toy-0.0-deps.eb'
        shutil.copy2(os.path.join(test_ecs_path, 't', 'toy', test_ec), self.test_prefix)
        shutil.copy2(os.path.join(test_ecs_path, 'i', 'intel', 'intel-2018a.eb'), self.test_prefix)
        self.assertFalse(os.path.exists(test_ec))

        args = [
            os.path.join(test_ecs_path, 't', 'toy', 'toy-0.0.eb'),
            test_ec,  # relative path, should be resolved via robot search path
            '--dry-run',
            '--debug',
            '--robot',
            '--robot-paths=%s' % self.test_prefix,  # override $EASYBUILD_ROBOT_PATHS
            '--unittest-file=%s' % self.logfile,
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,  # a GitHub token should be available for this user
            '--tmpdir=%s' % self.test_prefix,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn, raise_error=True)

        modules = [
            (test_ecs_path, 'toy/0.0'),  # specified easyconfigs, available at given location
            (self.test_prefix, 'intel/2018a'),  # dependency, found in robot search path
            (self.test_prefix, 'toy/0.0-deps'),  # specified easyconfig, found in robot search path
        ]
        for path_prefix, module in modules:
            ec_fn = "%s.eb" % '-'.join(module.split('/'))
            regex = re.compile(r"^ \* \[.\] %s.*%s \(module: %s\)$" % (path_prefix, ec_fn, module), re.M)
            self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

        # test using archived easyconfigs
        args = [
            'intel-2012a.eb',
            '--dry-run',
            '--debug',
            '--robot',
            '--unittest-file=%s' % self.logfile,
        ]
        self.assertErrorRegex(EasyBuildError, "Can't find", self.eb_main, args, logfile=dummylogfn, raise_error=True)

        args.append('--consider-archived-easyconfigs')
        outtxt = self.eb_main(args, logfile=dummylogfn, raise_error=True)
        regex = re.compile(r"^ \* \[.\] .*/__archive__/.*/intel-2012a.eb \(module: intel/2012a\)", re.M)
        self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

    def test_search_paths(self):
        """Test search_paths command line argument."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        test_ec = 'toy-0.0-deps.eb'
        shutil.copy2(os.path.join(test_ecs_path, 't', 'toy', test_ec), self.test_prefix)
        self.assertFalse(os.path.exists(test_ec))

        args = [
            '--search-paths=%s' % self.test_prefix,  # add to search path
            '--tmpdir=%s' % self.test_prefix,
            '--search',
            'toy',
        ]
        self.mock_stdout(True)
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        outtxt = self.get_stdout()
        self.mock_stdout(False)

        # Make sure we found the copied file
        regex = re.compile(r"^ \* %s$" % os.path.join(self.test_prefix, test_ec), re.M)
        self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

    def test_det_easyconfig_paths_from_pr(self):
        """Test det_easyconfig_paths function, with --from-pr enabled as well."""
        if self.github_token is None:
            print "Skipping test_from_pr, no GitHub token available?"
            return

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        test_ec = 'toy-0.0-deps.eb'
        shutil.copy2(os.path.join(test_ecs_path, 't', 'toy', test_ec), self.test_prefix)
        shutil.copy2(os.path.join(test_ecs_path, 'i', 'intel', 'intel-2018a.eb'), self.test_prefix)
        self.assertFalse(os.path.exists(test_ec))

        gompi_2015a_txt = '\n'.join([
            "easyblock = 'Toolchain'",
            "name = 'gompi'",
            "version = '2015a'",
            "versionsuffix = '-test'",
            "homepage = 'foo'",
            "description = 'bar'",
            "toolchain = {'name': 'dummy', 'version': 'dummy'}",
        ])
        write_file(os.path.join(self.test_prefix, 'gompi-2015a-test.eb'), gompi_2015a_txt)

        args = [
            os.path.join(test_ecs_path, 't', 'toy', 'toy-0.0.eb'),
            test_ec,  # relative path, should be resolved via robot search path
            # PR for foss/2015a, see https://github.com/easybuilders/easybuild-easyconfigs/pull/1239/files
            '--from-pr=1239',
            'FFTW-3.3.4-gompi-2015a.eb',
            'gompi-2015a-test.eb',  # relative path, available in robot search path
            '--dry-run',
            '--robot',
            '--robot=%s' % self.test_prefix,
            '--unittest-file=%s' % self.logfile,
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,  # a GitHub token should be available for this user
            '--tmpdir=%s' % self.test_prefix,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn, raise_error=True)

        modules = [
            (test_ecs_path, 'toy/0.0'),  # specified easyconfigs, available at given location
            (self.test_prefix, 'intel/2018a'),  # dependency, found in robot search path
            (self.test_prefix, 'toy/0.0-deps'),  # specified easyconfig, found in robot search path
            (self.test_prefix, 'gompi/2015a-test'),  # specified easyconfig, found in robot search path
            ('.*/files_pr1239', 'FFTW/3.3.4-gompi-2015a'),  # specified easyconfig
            ('.*/files_pr1239', 'gompi/2015a'),  # part of PR easyconfigs
            (test_ecs_path, 'GCC/4.9.2'),  # dependency for PR easyconfigs, found in robot search path
        ]
        for path_prefix, module in modules:
            ec_fn = "%s.eb" % '-'.join(module.split('/'))
            regex = re.compile(r"^ \* \[.\] %s.*%s \(module: %s\)$" % (path_prefix, ec_fn, module), re.M)
            self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

    def test_get_toolchain_hierarchy(self):
        """Test get_toolchain_hierarchy function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        fosscuda_hierarchy = get_toolchain_hierarchy({'name': 'fosscuda', 'version': '2018a'})
        self.assertEqual(fosscuda_hierarchy, [
            {'name': 'GCC', 'version': '6.4.0-2.28'},
            {'name': 'golf', 'version': '2018a'},
            {'name': 'gcccuda', 'version': '2018a'},
            {'name': 'golfc', 'version': '2018a'},
            {'name': 'gompic', 'version': '2018a'},
            {'name': 'fosscuda', 'version': '2018a'},
        ])

        foss_hierarchy = get_toolchain_hierarchy({'name': 'foss', 'version': '2018a'})
        self.assertEqual(foss_hierarchy, [
            {'name': 'GCC', 'version': '6.4.0-2.28'},
            {'name': 'golf', 'version': '2018a'},
            {'name': 'gompi', 'version': '2018a'},
            {'name': 'foss', 'version': '2018a'},
        ])

        iimpi_hierarchy = get_toolchain_hierarchy({'name': 'iimpi', 'version': '2016.01'})
        self.assertEqual(iimpi_hierarchy, [
            {'name': 'GCCcore', 'version': '4.9.3'},
            {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'},
            {'name': 'iimpi', 'version': '2016.01'},
        ])

        # test also --try-toolchain* case, where we want more detailed information
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        get_toolchain_hierarchy.clear()

        foss_hierarchy = get_toolchain_hierarchy({'name': 'foss', 'version': '2018a'}, incl_capabilities=True)
        expected = [
            {
                'name': 'GCC',
                'version': '6.4.0-2.28',
                'comp_family': 'GCC',
                'mpi_family': None,
                'lapack_family': None,
                'blas_family': None,
                'cuda': None
            },
            {
                'name': 'golf',
                'version': '2018a',
                'comp_family': 'GCC',
                'mpi_family': None,
                'lapack_family': 'OpenBLAS',
                'blas_family': 'OpenBLAS',
                'cuda': None
            },
            {
                'name': 'gompi',
                'version': '2018a',
                'comp_family': 'GCC',
                'mpi_family': 'OpenMPI',
                'lapack_family': None,
                'blas_family': None,
                'cuda': None
            },
            {
                'name': 'foss',
                'version': '2018a',
                'comp_family': 'GCC',
                'mpi_family': 'OpenMPI',
                'lapack_family': 'OpenBLAS',
                'blas_family': 'OpenBLAS',
                'cuda': None
            },
        ]
        self.assertEqual(foss_hierarchy, expected)

        iimpi_hierarchy = get_toolchain_hierarchy({'name': 'iimpi', 'version': '2016.01'},
                                                  incl_capabilities=True)
        expected = [
            {
                'name': 'GCCcore',
                'version': '4.9.3',
                'comp_family': 'GCC',
                'mpi_family': None,
                'blas_family': None,
                'lapack_family': None,
                'cuda': None,
            },
            {
                'name': 'iccifort',
                'version': '2016.1.150-GCC-4.9.3-2.25',
                'comp_family': 'Intel',
                'mpi_family': None,
                'lapack_family': None,
                'blas_family': None,
                'cuda': None
            },
            {
                'name': 'iimpi',
                'version': '2016.01',
                'comp_family': 'Intel',
                'mpi_family': 'IntelMPI',
                'lapack_family': None,
                'blas_family': None,
                'cuda': None
            },
        ]
        self.assertEqual(iimpi_hierarchy, expected)

        iccifortcuda_hierarchy = get_toolchain_hierarchy({'name': 'iccifortcuda', 'version': 'test'},
                                                         incl_capabilities=True)
        expected = [
            {
                'name': 'GCCcore',
                'version': '4.9.3',
                'comp_family': 'GCC',
                'mpi_family': None,
                'blas_family': None,
                'lapack_family': None,
                'cuda': None,
            },
            {
                'name': 'iccifort',
                'version': '2016.1.150-GCC-4.9.3-2.25',
                'comp_family': 'Intel',
                'mpi_family': None,
                'lapack_family': None,
                'blas_family': None,
                'cuda': None,
            },
            {
                'name': 'iccifortcuda',
                'version': 'test',
                'comp_family': 'Intel',
                'mpi_family': None,
                'lapack_family': None,
                'blas_family': None,
                'cuda': True,
            },
        ]
        self.assertEqual(iccifortcuda_hierarchy, expected)

        # test also including dummy
        init_config(build_options={
            'add_dummy_to_minimal_toolchains': True,
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        get_toolchain_hierarchy.clear()
        gompi_hierarchy = get_toolchain_hierarchy({'name': 'gompi', 'version': '2018a'})
        self.assertEqual(gompi_hierarchy, [
            {'name': 'dummy', 'version': ''},
            {'name': 'GCC', 'version': '6.4.0-2.28'},
            {'name': 'gompi', 'version': '2018a'},
        ])

        get_toolchain_hierarchy.clear()
        # check whether GCCcore is considered as subtoolchain, even if it's only listed as a dep
        gcc_hierarchy = get_toolchain_hierarchy({'name': 'GCC', 'version': '4.9.3-2.25'})
        self.assertEqual(gcc_hierarchy, [
            {'name': 'dummy', 'version': ''},
            {'name': 'GCCcore', 'version': '4.9.3'},
            {'name': 'GCC', 'version': '4.9.3-2.25'},
        ])

        get_toolchain_hierarchy.clear()
        iccifort_hierarchy = get_toolchain_hierarchy({'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'})
        self.assertEqual(iccifort_hierarchy, [
            {'name': 'dummy', 'version': ''},
            {'name': 'GCCcore', 'version': '4.9.3'},
            {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'},
        ])

        get_toolchain_hierarchy.clear()
        build_options = {
            'add_dummy_to_minimal_toolchains': True,
            'external_modules_metadata': ConfigObj(),
            'robot_path': test_easyconfigs,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        craycce_hierarchy = get_toolchain_hierarchy({'name': 'CrayCCE', 'version': '5.1.29'})
        self.assertEqual(craycce_hierarchy, [
            {'name': 'dummy', 'version': ''},
            {'name': 'CrayCCE', 'version': '5.1.29'},
        ])

        # special case of gmvapich2, where MVAPICH2 has a single dependency that is an external module
        # test case from https://github.com/eth-cscs/production/blob/master/easybuild/easyconfigs
        gmvapich2_hierarchy = get_toolchain_hierarchy({'name': 'gmvapich2', 'version': '15.11'})
        self.assertEqual(gmvapich2_hierarchy, [
            {'name': 'dummy', 'version': ''},
            {'name': 'GCCcore', 'version': '4.9.3'},
            {'name': 'GCC', 'version': '4.9.3-2.25'},
            {'name': 'gmvapich2', 'version': '15.11'},
        ])

        # put faulty foss easyconfig in place to test error reporting
        broken_gompi = os.path.join(self.test_prefix, 'gompi-2018a.eb')
        copy_file(os.path.join(test_easyconfigs, 'g', 'gompi', 'gompi-2018a.eb'), broken_gompi)
        ectxt = read_file(broken_gompi)
        ectxt += "\ndependencies += [('GCC', '4.6.4')]"
        write_file(broken_gompi, ectxt)
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': [self.test_prefix, test_easyconfigs],
        })
        tc = {'name': 'gompi', 'version': '2018a'}
        error_msg = "Multiple versions of GCC found in dependencies of toolchain gompi: 4.6.4, 6.4.0-2.28"
        self.assertErrorRegex(EasyBuildError, error_msg, get_toolchain_hierarchy, tc)

    def test_find_resolved_modules(self):
        """Test find_resolved_modules function."""
        nodeps = {
            'name': 'nodeps',
            'version': '1.2.3',
            'versionsuffix': '',
            'toolchain': {'name': 'dummy', 'version': 'dummy'},
            'dependencies': [],
            'full_mod_name': 'nodeps/1.2.3',
            'spec': 'nodeps-1.2.3.eb',
            'hidden': False,
        }
        dep1 = {
            'name': 'foo',
            'version': '2.3.4',
            'toolchain': {'name': 'GCC', 'version': '6.4.0-2.28'},
            'versionsuffix': '',
            'hidden': False,
        }
        dep2 = {
            'name': 'bar',
            'version': '3.4.5',
            'toolchain': {'name': 'gompi', 'version': '2018a'},
            'versionsuffix': '-test',
            'hidden': False,
        }
        onedep = {
            'name': 'onedep',
            'version': '3.14',
            'toolchain': {'name': 'foss', 'version': '2018a'},
            'dependencies': [dep1],
            'full_mod_name': 'onedep/3.14-foss-2018a',
            'spec': 'onedep-3.14-foss-2018a.eb',
        }
        threedeps = {
            'name': 'threedeps',
            'version': '9.8.7',
            'toolchain': {'name': 'foss', 'version': '2018a'},
            'dependencies': [dep1, dep2, nodeps],
            'full_mod_name': 'threedeps/9.8.7-foss-2018a',
            'spec': 'threedeps-9.8.7-foss-2018a.eb',
        }
        ecs = [
            nodeps,
            onedep,
            threedeps,
        ]
        mods = ['foo/2.3.4-GCC-6.4.0-2.28', 'bar/3.4.5-gompi-2018a', 'bar/3.4.5-GCC-6.4.0-2.28']

        ordered_ecs, new_easyconfigs, new_avail_modules = find_resolved_modules(ecs, mods, self.modtool)

        # all dependencies are resolved for easyconfigs included in ordered_ecs
        self.assertFalse(any([ec['dependencies'] for ec in ordered_ecs]))

        # nodeps/ondep easyconfigs have all dependencies resolved
        self.assertEqual(len(ordered_ecs), 2)
        self.assertEqual(nodeps, ordered_ecs[0])
        onedep['dependencies'] = []
        self.assertEqual(onedep, ordered_ecs[1])

        # threedeps has available dependencies (foo, nodeps) filtered out
        self.assertEqual(len(new_easyconfigs), 1)
        self.assertEqual(new_easyconfigs[0]['full_mod_name'], 'threedeps/9.8.7-foss-2018a')
        self.assertEqual(len(new_easyconfigs[0]['dependencies']), 1)
        self.assertEqual(new_easyconfigs[0]['dependencies'][0]['name'], 'bar')

        self.assertTrue(new_avail_modules, mods + ['nodeps/1.2.3', 'onedep/3.14-foss-2018a'])

        # also check results with retaining all dependencies enabled
        ordered_ecs, new_easyconfigs, new_avail_modules = find_resolved_modules(ecs, [], self.modtool,
                                                                                retain_all_deps=True)

        self.assertEqual(len(ordered_ecs), 2)
        self.assertEqual([ec['full_mod_name'] for ec in ordered_ecs], ['nodeps/1.2.3', 'onedep/3.14-foss-2018a'])

        self.assertEqual(len(new_easyconfigs), 1)
        self.assertEqual(len(new_easyconfigs[0]['dependencies']), 2)
        self.assertEqual([dep['name'] for dep in new_easyconfigs[0]['dependencies']], ['foo', 'bar'])

        self.assertTrue(new_avail_modules, ['nodeps/1.2.3', 'onedep/3.14-foss-2018a'])

    def test_tweak_robotpath(self):
        """Test that the robot correctly resolves the dependencies of tweaked easyconfigs. Tweaked
        easyconfigs take priority, but tweaked dependencies are only used on an as-needed basis"""

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        # Create directories to store the tweaked easyconfigs
        tweaked_ecs_paths, pr_path = alt_easyconfig_paths(self.test_prefix, tweaked_ecs=True)
        robot_path = det_robot_path([test_easyconfigs], tweaked_ecs_paths, pr_path, auto_robot=True)

        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': robot_path,
            'check_osdeps': False,
        })

        # Parse the easyconfig that we want to tweak
        untweaked_openmpi = os.path.join(test_easyconfigs, 'o', 'OpenMPI', 'OpenMPI-2.1.2-GCC-4.6.4.eb')
        easyconfigs, _ = parse_easyconfigs([(untweaked_openmpi, False)])

        # Tweak the toolchain version of the easyconfig
        tweak_specs = {'toolchain_version': '6.4.0-2.28'}
        easyconfigs = tweak(easyconfigs, tweak_specs, self.modtool, targetdirs=tweaked_ecs_paths)

        # Check that all expected tweaked easyconfigs exists
        tweaked_openmpi = os.path.join(tweaked_ecs_paths[0], 'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb')
        tweaked_hwloc = os.path.join(tweaked_ecs_paths[1], 'hwloc-1.11.8-GCC-6.4.0-2.28.eb')
        self.assertTrue(os.path.isfile(tweaked_openmpi))
        self.assertTrue(os.path.isfile(tweaked_hwloc))

        # Check that the robotpath is correctly configured to pick up the right versions of the easyconfigs
        res = resolve_dependencies(easyconfigs, self.modtool, retain_all_deps=True)
        specs = [ec['spec'] for ec in res]
        # Check it picks up the tweaked OpenMPI
        self.assertTrue(tweaked_openmpi in specs)
        # Check it picks up the untweaked dependency of the tweaked OpenMPI
        untweaked_hwloc = os.path.join(test_easyconfigs, 'h', 'hwloc', 'hwloc-1.11.8-GCC-6.4.0-2.28.eb')
        self.assertTrue(untweaked_hwloc in specs)

    def test_robot_find_subtoolchain_for_dep(self):
        """Test robot_find_subtoolchain_for_dep."""

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={'robot_path': test_easyconfigs})

        #
        # First test that it can do basic resolution
        #
        gzip15 = {
            'name': 'gzip',
            'version': '1.5',
            'versionsuffix': '',
            'toolchain': {'name': 'foss', 'version': '2018a'},
        }
        get_toolchain_hierarchy.clear()
        new_gzip15_toolchain = robot_find_subtoolchain_for_dep(gzip15, self.modtool)
        self.assertEqual(new_gzip15_toolchain, gzip15['toolchain'])

        # no easyconfig for gzip 1.4 with matching non-dummy (sub)toolchain
        gzip14 = {
            'name': 'gzip',
            'version': '1.4',
            'versionsuffix': '',
            'toolchain': {'name': 'foss', 'version': '2018a'},
        }
        get_toolchain_hierarchy.clear()
        self.assertEqual(robot_find_subtoolchain_for_dep(gzip14, self.modtool), None)

        gzip14['toolchain'] = {'name': 'gompi', 'version': '2018a'}

        #
        # Second test also including dummy toolchain
        #
        init_config(build_options={
            'add_dummy_to_minimal_toolchains': True,
            'robot_path': test_easyconfigs,
        })
        # specify alternative parent toolchain
        gompi_1410 = {'name': 'gompi', 'version': '2018a'}
        get_toolchain_hierarchy.clear()
        new_gzip14_toolchain = robot_find_subtoolchain_for_dep(gzip14, self.modtool, parent_tc=gompi_1410)
        self.assertTrue(new_gzip14_toolchain != gzip14['toolchain'])
        self.assertEqual(new_gzip14_toolchain, {'name': 'dummy', 'version': ''})

        # default: use toolchain from dependency
        gzip14['toolchain'] = gompi_1410
        get_toolchain_hierarchy.clear()
        new_gzip14_toolchain = robot_find_subtoolchain_for_dep(gzip14, self.modtool)
        self.assertTrue(new_gzip14_toolchain != gzip14['toolchain'])
        self.assertEqual(new_gzip14_toolchain, {'name': 'dummy', 'version': ''})

        # check reversed order (parent tc first) and skipping of parent tc itself
        dep = {
            'name': 'SQLite',
            'version': '3.8.10.2',
            'toolchain': {'name': 'foss', 'version': '2018a'},
            'hidden': False,
        }
        res = robot_find_subtoolchain_for_dep(dep, self.modtool)
        self.assertEqual(res, {'name': 'GCC', 'version': '6.4.0-2.28'})
        res = robot_find_subtoolchain_for_dep(dep, self.modtool, parent_first=True)
        self.assertEqual(res, {'name': 'foss', 'version': '2018a'})

        #
        # Finally test if it can recognise existing modules and use those
        #
        barec = os.path.join(self.test_prefix, 'bar-1.2.3-foss-2018a.eb')
        barec_txt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'bar'",
            "version = '1.2.3'",
            "homepage = 'http://example.com'",
            "description = 'foo'",
            "toolchain = {'name': 'foss', 'version': '2018a'}",
            # deliberately listing components of toolchain as dependencies without specifying subtoolchains,
            # to test resolving of dependencies with minimal toolchain
            # for each of these, we know test easyconfigs are available (which are required here)
            "dependencies = [",
            "   ('OpenMPI', '2.1.2'),",  # available with GCC/6.4.0-2.28
            "   ('OpenBLAS', '0.2.20'),",  # available with gompi/2018a
            "   ('ScaLAPACK', '2.0.2', '-OpenBLAS-0.2.20'),",  # available with gompi/2018a
            "   ('SQLite', '3.8.10.2'),",  # available with foss/2018a, gompi/2018a and GCC/6.4.0-2.28
            "]",
        ])
        write_file(barec, barec_txt)

        # check without --minimal-toolchains
        init_config(build_options={'robot_path': test_easyconfigs})
        bar = EasyConfig(barec)

        expected_dep_versions = {
            'OpenMPI': '2.1.2-GCC-6.4.0-2.28',
            'OpenBLAS': '0.2.20-GCC-6.4.0-2.28',
            'ScaLAPACK': '2.0.2-gompi-2018a-OpenBLAS-0.2.20',
            'SQLite': '3.8.10.2-foss-2018a',
        }
        for dep in bar.dependencies():
            expected_dep_version = expected_dep_versions[dep['name']]
            self.assertEqual(det_full_ec_version(dep), expected_dep_version)

        # check with --minimal-toolchains enabled
        init_config(build_options={
            'minimal_toolchains': True,
            'robot_path': test_easyconfigs,
        })
        bar = EasyConfig(barec)

        expected_dep_versions = {
            'OpenMPI': '2.1.2-GCC-6.4.0-2.28',
            'OpenBLAS': '0.2.20-GCC-6.4.0-2.28',
            'ScaLAPACK': '2.0.2-gompi-2018a-OpenBLAS-0.2.20',
            'SQLite': '3.8.10.2-GCC-6.4.0-2.28',
        }

        # check that all bar dependencies have been processed as expected
        for dep in bar.dependencies():
            expected_dep_version = expected_dep_versions[dep['name']]
            self.assertEqual(det_full_ec_version(dep), expected_dep_version)

        # Add the gompi/2018a version of SQLite as an available module
        module_parent = os.path.join(self.test_prefix, 'minimal_toolchain_modules')
        module_file = os.path.join(module_parent, 'SQLite', '3.8.10.2-gompi-2018a')
        module_txt = '\n'.join([
            "#%Module",
            "set root /tmp/SQLite/3.8.10.2",
            "setenv EBROOTSQLITE $root",
            "setenv EBVERSIONSQLITE 3.8.10.2",
            "setenv  EBDEVELSQLITE $root/easybuild/SQLite-3.8.10.2-easybuild-devel",
        ])
        write_file(module_file, module_txt)
        os.environ['MODULEPATH'] = module_parent  # Add the parent directory to the MODULEPATH
        invalidate_module_caches_for(module_parent)

        # Reinitialize the environment for the updated MODULEPATH and use_existing_modules
        init_config(build_options={
            'minimal_toolchains': True,
            'use_existing_modules': True,
            'robot_path': test_easyconfigs,
        })

        # Check gompi is now being picked up
        bar = EasyConfig(barec)  # Re-parse the parent easyconfig
        sqlite = bar.dependencies()[3]
        self.assertEqual(det_full_ec_version(sqlite), '3.8.10.2-gompi-2018a')

        # Add the foss version as an available version and check that gets precedence over the gompi version
        module_file = os.path.join(module_parent, 'SQLite', '3.8.10.2-foss-2018a')
        write_file(module_file, module_txt)
        invalidate_module_caches_for(module_parent)
        bar = EasyConfig(barec)  # Re-parse the parent easyconfig
        sqlite = bar.dependencies()[3]
        self.assertEqual(det_full_ec_version(sqlite), '3.8.10.2-foss-2018a')

    def test_robot_find_subtoolchain_for_dep_ecs_vs_mods(self):
        """
        Test behaviour of robot_find_subtoolchain_for_dep
        w.r.t. picking subtoolchains based on easyconfigs vs modules.
        """
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        # include both test easyconfig files and test directory in robot search path
        build_options = {'robot_path': [test_easyconfigs, self.test_prefix]}
        init_config(build_options=build_options)

        test_mods_dir = os.path.join(self.test_prefix, 'modules')
        mkdir(test_mods_dir)
        self.modtool.use(test_mods_dir)

        dep = {
            'name': 'dummydep',
            'version': '1.2.3',
            'versionsuffix': '',
            'toolchain': {'name': 'foss', 'version': '2018a'},
        }

        # no subtoolchain found if no easyconfigs or modules are found for this dep
        res = robot_find_subtoolchain_for_dep(dep, self.modtool, parent_first=True)
        self.assertEqual(res, None)

        # reset caches to make sure easyconfigs/modules are checked again
        ecec._easyconfig_files_cache.clear()
        reset_module_caches()

        # if a module file is found, that determines subtoolchain to use for dummy dep
        dummydep_modfile = os.path.join(test_mods_dir, 'dummydep', '1.2.3-gompi-2018a')
        write_file(dummydep_modfile, '#%Module')

        expected_gompi = {'name': 'gompi', 'version': '2018a'}

        # default config (no --minimal-toolchains)
        res = robot_find_subtoolchain_for_dep(dep, self.modtool, parent_first=True)
        self.assertEqual(res, expected_gompi)

        # same when --minimal-toolchains is used, but only if --use-existing-modules is also used
        res = robot_find_subtoolchain_for_dep(dep, self.modtool)
        self.assertEqual(res, None)

        build_options['use_existing_modules'] = True
        init_config(build_options=build_options)

        res = robot_find_subtoolchain_for_dep(dep, self.modtool)
        self.assertEqual(res, expected_gompi)

        # reset caches to make sure easyconfigs/modules are checked again
        ecec._easyconfig_files_cache.clear()
        reset_module_caches()

        build_options['use_existing_modules'] = False
        init_config(build_options=build_options)

        # if an easyconfig file is also available, this determines the subtoolchain instead
        # (unless --use-existing-modules is used)
        ec_txt = '\n'.join([
            "name = 'dummydep'",
            "version = '1.2.3'",
            "homepage = 'example.com'",
            "description = 'dummy dep'",
            "toolchain = {'name': 'foss', 'version': '2018a'}",
        ])
        write_file(os.path.join(self.test_prefix, 'dummydep-1.2.3-foss-2018a.eb'), ec_txt)

        expected_foss = {'name': 'foss', 'version': '2018a'}

        res = robot_find_subtoolchain_for_dep(dep, self.modtool, parent_first=True)
        self.assertEqual(res, expected_foss)

        res = robot_find_subtoolchain_for_dep(dep, self.modtool)
        self.assertEqual(res, expected_foss)

        # if --use-existing-modules is enabled,
        # subtoolchain picked by easyconfigs gets overruled by subtoolchain picked by modules
        build_options['use_existing_modules'] = True
        init_config(build_options=build_options)

        res = robot_find_subtoolchain_for_dep(dep, self.modtool, parent_first=True)
        self.assertEqual(res, expected_gompi)

        res = robot_find_subtoolchain_for_dep(dep, self.modtool)
        self.assertEqual(res, expected_gompi)

    def test_check_conflicts(self):
        """Test check_conflicts function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'force': True,
            'retain_all_deps': True,
            'robot_path': test_easyconfigs,
            'valid_module_classes': module_classes(),
            'validate': False,
        })

        gzip_ec = os.path.join(test_easyconfigs, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb')
        gompi_ec = os.path.join(test_easyconfigs, 'g', 'gompi', 'gompi-2018a.eb')
        ecs, _ = parse_easyconfigs([(gzip_ec, False), (gompi_ec, False)])

        # no conflicts found, no output to stderr
        self.mock_stderr(True)
        conflicts = check_conflicts(ecs, self.modtool)
        stderr = self.get_stderr()
        self.mock_stderr(False)
        self.assertFalse(conflicts)
        self.assertEqual(stderr, '')

        # change GCC version in gompi dependency, to inject a conflict
        gompi_ec_txt = read_file(gompi_ec)
        new_gompi_ec = os.path.join(self.test_prefix, 'gompi.eb')
        write_file(new_gompi_ec, gompi_ec_txt.replace('6.4.0-2.28', '4.6.4'))

        ecs, _ = parse_easyconfigs([(new_gompi_ec, False), (gzip_ec, False)])

        # conflicts are found and reported to stderr
        self.mock_stderr(True)
        conflicts = check_conflicts(ecs, self.modtool)
        stderr = self.get_stderr()
        self.mock_stderr(False)

        self.assertTrue(conflicts)
        self.assertTrue("Conflict found for dependencies of foss-2018a: GCC-4.6.4 vs GCC-6.4.0-2.28" in stderr)

        # conflicts between specified easyconfigs are also detected

        # direct conflict on software version
        ecs, _ = parse_easyconfigs([
            (os.path.join(test_easyconfigs, 'g', 'GCC', 'GCC-6.4.0-2.28.eb'), False),
            (os.path.join(test_easyconfigs, 'g', 'GCC', 'GCC-4.9.3-2.25.eb'), False),
        ])
        self.mock_stderr(True)
        conflicts = check_conflicts(ecs, self.modtool)
        stderr = self.get_stderr()
        self.mock_stderr(False)

        self.assertTrue(conflicts)
        self.assertTrue("Conflict between (dependencies of) easyconfigs: GCC-4.9.3-2.25 vs GCC-6.4.0-2.28" in stderr)

        # indirect conflict on dependencies
        ecs, _ = parse_easyconfigs([
            (os.path.join(test_easyconfigs, 'b', 'bzip2', 'bzip2-1.0.6-GCC-4.9.2.eb'), False),
            (os.path.join(test_easyconfigs, 'h', 'hwloc', 'hwloc-1.11.8-GCC-6.4.0-2.28.eb'), False),
        ])
        self.mock_stderr(True)
        conflicts = check_conflicts(ecs, self.modtool)
        stderr = self.get_stderr()
        self.mock_stderr(False)

        self.assertTrue(conflicts)
        self.assertTrue("Conflict between (dependencies of) easyconfigs: GCC-4.9.2 vs GCC-6.4.0-2.28" in stderr)

        # test use of check_inter_ec_conflicts
        self.assertFalse(check_conflicts(ecs, self.modtool, check_inter_ec_conflicts=False), "No conflicts found")

    def test_check_conflicts_wrapper_deps(self):
        """Test check_conflicts when dependency 'wrappers' are involved."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb')

        wrapper_ec_txt = '\n'.join([
            "easyblock = 'ModuleRC'",
            "name = 'toy'",
            "version = '0'",
            "homepage = 'https://example.com'",
            "description = 'Just A Wrapper'",
            "toolchain = {'name': 'dummy', 'version': ''}",
            "dependencies = [('toy', '0.0')]",
        ])
        wrapper_ec = os.path.join(self.test_prefix, 'toy-0.eb')
        write_file(wrapper_ec, wrapper_ec_txt)

        ecs, _ = parse_easyconfigs([(toy_ec, False), (wrapper_ec, False)])
        self.mock_stderr(True)
        res = check_conflicts(ecs, self.modtool)
        stderr = self.get_stderr()
        self.mock_stderr(False)
        self.assertEqual(stderr, '')
        self.assertFalse(res)

    def test_robot_archived_easyconfigs(self):
        """Test whether robot can pick up archived easyconfigs when asked."""

        # we must allow use of deprecated toolchain in this case
        self.allow_deprecated_behaviour()
        init_config()

        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        gzip_ec = os.path.join(test_ecs, 'g', 'gzip', 'gzip-1.5-intel-2018a.eb')
        gzip_ectxt = read_file(gzip_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        tc_spec = "toolchain = {'name': 'intel', 'version': '2012a'}"
        regex = re.compile("^toolchain = .*", re.M)
        test_ectxt = regex.sub(tc_spec, gzip_ectxt)
        write_file(test_ec, test_ectxt)
        ecs, _ = parse_easyconfigs([(test_ec, False)])
        self.assertErrorRegex(EasyBuildError, "Missing dependencies", resolve_dependencies,
                              ecs, self.modtool, retain_all_deps=True)

        # --consider-archived-easyconfigs must be used to let robot pick up archived easyconfigs
        init_config(build_options={
            'consider_archived_easyconfigs': True,
            'robot_path': [test_ecs],
        })
        res = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)
        self.assertEqual([ec['full_mod_name'] for ec in res], ['intel/2012a', 'gzip/1.5-intel-2012a'])
        expected = os.path.join(test_ecs, '__archive__', 'i', 'intel', 'intel-2012a.eb')
        self.assertTrue(os.path.samefile(res[0]['spec'], expected))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(RobotTest, sys.argv[1:])


if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
