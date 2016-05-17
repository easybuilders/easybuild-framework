# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
import re
import shutil
import tempfile
from copy import deepcopy
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader
from unittest import main as unittestmain

import easybuild.framework.easyconfig.easyconfig as ecec
import easybuild.framework.easyconfig.tools as ectools
import easybuild.tools.build_log
import easybuild.tools.robot as robot
from easybuild.framework.easyconfig.easyconfig import process_easyconfig, EasyConfig
from easybuild.framework.easyconfig.tools import find_resolved_modules
from easybuild.framework.easyconfig.easyconfig import get_toolchain_hierarchy
from easybuild.framework.easyconfig.easyconfig import robot_find_minimal_toolchain_of_dependency
from easybuild.framework.easyconfig.tools import skip_available
from easybuild.tools import config, modules
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.github import fetch_github_token
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import invalidate_module_caches_for
from easybuild.tools.robot import resolve_dependencies
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

        base_easyconfig_dir = find_full_path(os.path.join("test", "framework", "easyconfigs"))
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
        self.assertEqual(len(res), 4)  # hidden dep toy/.0.0-deps (+1) depends on (fake) ictce/4.1.13 (+1)
        self.assertEqual('gzip/1.4', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[-1]['full_mod_name'])
        full_mod_names = [ec['full_mod_name'] for ec in res]
        self.assertTrue('toy/.0.0-deps' in full_mod_names)
        self.assertTrue('ictce/4.1.13' in full_mod_names)

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
        msg = "Irresolvable dependencies encountered"
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
            'hidden': False,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        res = resolve_dependencies(ecs, self.modtool)

        # there should only be two retained builds, i.e. the software itself and the goolf toolchain as dep
        self.assertEqual(len(res), 2)
        # goolf should be first, the software itself second
        self.assertEqual('goolf/1.4.10', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[1]['full_mod_name'])

        # force doesn't trigger rebuild of all deps, but listed easyconfigs for which a module is available are rebuilt
        build_options.update({'force': True})
        init_config(build_options=build_options)
        easyconfig['full_mod_name'] = 'this/is/already/there'
        MockModule.avail_modules.append('this/is/already/there')
        ecs = [deepcopy(easyconfig_dep), deepcopy(easyconfig)]
        res = resolve_dependencies(ecs, self.modtool)

        # there should only be three retained builds, foo + goolf dep and the additional build (even though a module is available)
        self.assertEqual(len(res), 3)
        # goolf should be first, the software itself second
        self.assertEqual('this/is/already/there', res[0]['full_mod_name'])
        self.assertEqual('goolf/1.4.10', res[1]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[2]['full_mod_name'])

        # build that are listed but already have a module available are not retained without force
        build_options.update({'force': False})
        init_config(build_options=build_options)
        newecs = skip_available(ecs, self.modtool)  # skip available builds since force is not enabled
        res = resolve_dependencies(newecs, self.modtool)
        self.assertEqual(len(res), 2)
        self.assertEqual('goolf/1.4.10', res[0]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[1]['full_mod_name'])

        # with retain_all_deps enabled, all dependencies ae retained
        build_options.update({'retain_all_deps': True})
        init_config(build_options=build_options)
        ecs = [deepcopy(easyconfig_dep)]
        newecs = skip_available(ecs, self.modtool)  # skip available builds since force is not enabled
        res = resolve_dependencies(newecs, self.modtool)
        self.assertEqual(len(res), 9)
        self.assertEqual('GCC/4.7.2', res[0]['full_mod_name'])
        self.assertEqual('goolf/1.4.10', res[-2]['full_mod_name'])
        self.assertEqual('foo/1.2.3', res[-1]['full_mod_name'])

        build_options.update({'retain_all_deps': False})
        init_config(build_options=build_options)

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
            'hidden': False,
        }]
        ecs = [deepcopy(easyconfig_dep)]
        res = resolve_dependencies([deepcopy(easyconfig_dep)], self.modtool)

        # there should only be two retained builds, i.e. the software itself and the goolf toolchain as dep
        self.assertEqual(len(res), 4)
        # goolf should be first, the software itself second
        self.assertEqual('OpenBLAS/0.2.6-gompi-1.4.10-LAPACK-3.4.2', res[0]['full_mod_name'])
        self.assertEqual('ScaLAPACK/2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2', res[1]['full_mod_name'])
        self.assertEqual('goolf/1.4.10', res[2]['full_mod_name'])
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

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
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

        barec = os.path.join(self.test_prefix, 'bar-1.2.3-goolf-1.4.10.eb')
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
            "   ('OpenMPI', '1.6.4'),",  # available with GCC/4.7.2
            "   ('OpenBLAS', '0.2.6', '-LAPACK-3.4.2'),",  # available with gompi/1.4.10
            "   ('ScaLAPACK', '2.0.2', '-OpenBLAS-0.2.6-LAPACK-3.4.2'),",  # available with gompi/1.4.10
            "   ('SQLite', '3.8.10.2'),",
            "]",
            # toolchain as list line, for easy modification later
            "toolchain = {'name': 'goolf', 'version': '1.4.10'}",
        ]
        write_file(barec, '\n'.join(barec_lines))
        bar = process_easyconfig(barec)[0]

        # all modules in the dep graph, in order
        all_mods_ordered = [
            'GCC/4.7.2',
            'hwloc/1.6.2-GCC-4.7.2',
            'OpenMPI/1.6.4-GCC-4.7.2',
            'gompi/1.4.10',
            'OpenBLAS/0.2.6-gompi-1.4.10-LAPACK-3.4.2',
            'ScaLAPACK/2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2',
            'SQLite/3.8.10.2-GCC-4.7.2',
            'FFTW/3.3.3-gompi-1.4.10',
            'goolf/1.4.10',
            'bar/1.2.3-goolf-1.4.10',
        ]

        # no modules available, so all dependencies are retained
        MockModule.avail_modules = []
        res = resolve_dependencies([bar], self.modtool)
        self.assertEqual(len(res), 10)
        self.assertEqual([x['full_mod_name'] for x in res], all_mods_ordered)

        MockModule.avail_modules = [
            'GCC/4.7.2',
            'gompi/1.4.10',
            'goolf/1.4.10',
            'OpenMPI/1.6.4-GCC-4.7.2',
            'OpenBLAS/0.2.6-gompi-1.4.10-LAPACK-3.4.2',
            'ScaLAPACK/2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2',
            'SQLite/3.8.10.2-GCC-4.7.2',
        ]

        # test resolving dependencies with minimal toolchain (rather than using goolf/1.4.10 for all of them)
        # existing modules are *not* taken into account when determining minimal subtoolchain, by default
        res = resolve_dependencies([bar], self.modtool)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['full_mod_name'], bar['ec'].full_mod_name)

        # test retaining all dependencies, regardless of whether modules are available or not
        res = resolve_dependencies([bar], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 10)
        mods = [x['full_mod_name'] for x in res]
        self.assertEqual(mods, all_mods_ordered)
        self.assertTrue('SQLite/3.8.10.2-GCC-4.7.2' in mods)

        # test taking into account existing modules
        # with an SQLite module with goolf/1.4.10 in place, this toolchain should be used rather than GCC/4.7.2
        MockModule.avail_modules = [
            'SQLite/3.8.10.2-goolf-1.4.10',
        ]

        # parsed easyconfigs are cached, so clear the cache before reprocessing easyconfigs
        ecec._easyconfigs_cache.clear()

        bar = process_easyconfig(barec)[0]
        res = resolve_dependencies([bar], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 10)
        mods = [x['full_mod_name'] for x in res]
        self.assertTrue('SQLite/3.8.10.2-goolf-1.4.10' in mods)
        self.assertFalse('SQLite/3.8.10.2-GCC-4.7.2' in mods)

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

        impi_txt = read_file(os.path.join(test_easyconfigs, 'impi-4.1.3.049.eb'))
        self.assertTrue(re.search("^toolchain = {'name': 'dummy', 'version': ''}", impi_txt, re.M))
        gzip_txt = read_file(os.path.join(test_easyconfigs, 'gzip-1.4.eb'))
        self.assertTrue(re.search("^toolchain = {'name': 'dummy', 'version': 'dummy'}", gzip_txt, re.M))

        barec = os.path.join(self.test_prefix, 'bar-1.2.3-goolf-1.4.10.eb')
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
            "   ('impi', '4.1.3.049'),",  # has toolchain ('dummy', '')
            "   ('gzip', '1.4'),",  # has toolchain ('dummy', 'dummy')
            "]",
            # toolchain as list line, for easy modification later
            "toolchain = {'name': 'goolf', 'version': '1.4.10'}",
        ]
        write_file(barec, '\n'.join(barec_lines))
        bar = process_easyconfig(barec)[0]

        res = resolve_dependencies([bar], self.modtool, retain_all_deps=True)
        self.assertEqual(len(res), 11)
        mods = [x['full_mod_name'] for x in res]
        self.assertTrue('impi/4.1.3.049' in mods)
        self.assertTrue('gzip/1.4' in mods)


    def test_det_easyconfig_paths(self):
        """Test det_easyconfig_paths function (without --from-pr)."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')

        test_ec = 'toy-0.0-deps.eb'
        shutil.copy2(os.path.join(test_ecs_path, test_ec), self.test_prefix)
        shutil.copy2(os.path.join(test_ecs_path, 'ictce-4.1.13.eb'), self.test_prefix)
        self.assertFalse(os.path.exists(test_ec))

        args = [
            os.path.join(test_ecs_path, 'toy-0.0.eb'),
            test_ec,  # relative path, should be resolved via robot search path
            # PR for foss/2015a, see https://github.com/hpcugent/easybuild-easyconfigs/pull/1239/files
            #'--from-pr=1239',
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
            (self.test_prefix, 'ictce/4.1.13'),  # dependency, found in robot search path
            (self.test_prefix, 'toy/0.0-deps'),  # specified easyconfig, found in robot search path
        ]
        for path_prefix, module in modules:
            ec_fn = "%s.eb" % '-'.join(module.split('/'))
            regex = re.compile(r"^ \* \[.\] %s.*%s \(module: %s\)$" % (path_prefix, ec_fn, module), re.M)
            self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

    def test_det_easyconfig_paths_from_pr(self):
        """Test det_easyconfig_paths function, with --from-pr enabled as well."""
        if self.github_token is None:
            print "Skipping test_from_pr, no GitHub token available?"
            return

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')

        test_ec = 'toy-0.0-deps.eb'
        shutil.copy2(os.path.join(test_ecs_path, test_ec), self.test_prefix)
        shutil.copy2(os.path.join(test_ecs_path, 'ictce-4.1.13.eb'), self.test_prefix)
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
        # put gompi-2015a.eb easyconfig in place that shouldn't be considered (paths via --from-pr have precedence)
        write_file(os.path.join(self.test_prefix, 'gompi-2015a.eb'), gompi_2015a_txt)

        args = [
            os.path.join(test_ecs_path, 'toy-0.0.eb'),
            test_ec,  # relative path, should be resolved via robot search path
            # PR for foss/2015a, see https://github.com/hpcugent/easybuild-easyconfigs/pull/1239/files
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

        from_pr_prefix = os.path.join(self.test_prefix, '.*', 'files_pr1239')
        modules = [
            (test_ecs_path, 'toy/0.0'),  # specified easyconfigs, available at given location
            (self.test_prefix, 'ictce/4.1.13'),  # dependency, found in robot search path
            (self.test_prefix, 'toy/0.0-deps'),  # specified easyconfig, found in robot search path
            (self.test_prefix, 'gompi/2015a-test'),  # specified easyconfig, found in robot search path
            (from_pr_prefix, 'FFTW/3.3.4-gompi-2015a'),  # part of PR easyconfigs
            (from_pr_prefix, 'gompi/2015a'),  # part of PR easyconfigs
            (test_ecs_path, 'GCC/4.9.2'),  # dependency for PR easyconfigs, found in robot search path
        ]
        for path_prefix, module in modules:
            ec_fn = "%s.eb" % '-'.join(module.split('/'))
            regex = re.compile(r"^ \* \[.\] %s.*%s \(module: %s\)$" % (path_prefix, ec_fn, module), re.M)
            self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

    def test_get_toolchain_hierarchy(self):
        """Test get_toolchain_hierarchy function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        goolf_hierarchy = get_toolchain_hierarchy({'name': 'goolf', 'version': '1.4.10'})
        self.assertEqual(goolf_hierarchy, [
            {'name': 'GCC', 'version': '4.7.2'},
            {'name': 'gompi', 'version': '1.4.10'},
            {'name': 'goolf', 'version': '1.4.10'},
        ])

        iimpi_hierarchy = get_toolchain_hierarchy({'name': 'iimpi', 'version': '5.5.3-GCC-4.8.3'})
        self.assertEqual(iimpi_hierarchy, [
            {'name': 'iccifort', 'version': '2013.5.192-GCC-4.8.3'},
            {'name': 'iimpi', 'version': '5.5.3-GCC-4.8.3'},
        ])

        # test also including dummy
        init_config(build_options={
            'add_dummy_to_minimal_toolchains': True,
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        get_toolchain_hierarchy.clear()
        gompi_hierarchy = get_toolchain_hierarchy({'name': 'gompi', 'version': '1.4.10'})
        self.assertEqual(gompi_hierarchy, [
            {'name': 'dummy', 'version': ''},
            {'name': 'GCC', 'version': '4.7.2'},
            {'name': 'gompi', 'version': '1.4.10'},
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
            'toolchain': {'name': 'GCC', 'version': '4.7.2'},
            'versionsuffix': '',
            'hidden': False,
        }
        dep2 = {
            'name': 'bar',
            'version': '3.4.5',
            'toolchain': {'name': 'gompi', 'version': '1.4.10'},
            'versionsuffix': '-test',
            'hidden': False,
        }
        onedep = {
            'name': 'onedep',
            'version': '3.14',
            'toolchain': {'name': 'goolf', 'version': '1.4.10'},
            'dependencies': [dep1],
            'full_mod_name': 'onedep/3.14-goolf-1.4.10',
            'spec': 'onedep-3.14-goolf-1.4.10.eb',
        }
        threedeps = {
            'name': 'threedeps',
            'version': '9.8.7',
            'toolchain': {'name': 'goolf', 'version': '1.4.10'},
            'dependencies': [dep1, dep2, nodeps],
            'full_mod_name': 'threedeps/9.8.7-goolf-1.4.10',
            'spec': 'threedeps-9.8.7-goolf-1.4.10.eb',
        }
        ecs = [
            nodeps,
            onedep,
            threedeps,
        ]
        mods = ['foo/2.3.4-GCC-4.7.2', 'bar/3.4.5-gompi-1.4.10', 'bar/3.4.5-GCC-4.7.2']

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
        self.assertEqual(new_easyconfigs[0]['full_mod_name'], 'threedeps/9.8.7-goolf-1.4.10')
        self.assertEqual(len(new_easyconfigs[0]['dependencies']), 1)
        self.assertEqual(new_easyconfigs[0]['dependencies'][0]['name'], 'bar')

        self.assertTrue(new_avail_modules, mods + ['nodeps/1.2.3', 'onedep/3.14-goolf-1.4.10'])

        # also check results with retaining all dependencies enabled
        ordered_ecs, new_easyconfigs, new_avail_modules = find_resolved_modules(ecs, [], self.modtool,
                                                                                retain_all_deps=True)

        self.assertEqual(len(ordered_ecs), 2)
        self.assertEqual([ec['full_mod_name'] for ec in ordered_ecs], ['nodeps/1.2.3', 'onedep/3.14-goolf-1.4.10'])

        self.assertEqual(len(new_easyconfigs), 1)
        self.assertEqual(len(new_easyconfigs[0]['dependencies']), 2)
        self.assertEqual([dep['name'] for dep in new_easyconfigs[0]['dependencies']], ['foo', 'bar'])

        self.assertTrue(new_avail_modules, ['nodeps/1.2.3', 'onedep/3.14-goolf-1.4.10'])

    def test_robot_find_minimal_toolchain_for_dependency(self):
        """Test robot_find_minimal_toolchain_for_dependency."""

        # replace log.experimental with log.warning to allow experimental code
        easybuild.framework.easyconfig.tools._log.experimental = easybuild.framework.easyconfig.tools._log.warning

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        #
        # First test that it can do basic resolution
        #
        gzip15 = {
            'name': 'gzip',
            'version': '1.5',
            'versionsuffix': '',
            'toolchain': {'name': 'goolf', 'version': '1.4.10'},
        }
        get_toolchain_hierarchy.clear()
        new_gzip15_toolchain = robot_find_minimal_toolchain_of_dependency(gzip15, self.modtool)
        self.assertEqual(new_gzip15_toolchain, gzip15['toolchain'])

        # no easyconfig for gzip 1.4 with matching non-dummy (sub)toolchain
        gzip14 = {
            'name': 'gzip',
            'version': '1.4',
            'versionsuffix': '',
            'toolchain': {'name': 'goolf', 'version': '1.4.10'},
        }
        get_toolchain_hierarchy.clear()
        self.assertEqual(robot_find_minimal_toolchain_of_dependency(gzip14, self.modtool), None)

        gzip14['toolchain'] = {'name': 'gompi', 'version': '1.4.10'}

        #
        # Second test also including dummy toolchain
        #
        init_config(build_options={
            'add_dummy_to_minimal_toolchains': True,
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })
        # specify alternative parent toolchain
        gompi_1410 = {'name': 'gompi', 'version': '1.4.10'}
        get_toolchain_hierarchy.clear()
        new_gzip14_toolchain = robot_find_minimal_toolchain_of_dependency(gzip14, self.modtool, parent_tc=gompi_1410)
        self.assertTrue(new_gzip14_toolchain != gzip14['toolchain'])
        self.assertEqual(new_gzip14_toolchain, {'name': 'dummy', 'version': ''})

        # default: use toolchain from dependency
        gzip14['toolchain'] = gompi_1410
        get_toolchain_hierarchy.clear()
        new_gzip14_toolchain = robot_find_minimal_toolchain_of_dependency(gzip14, self.modtool)
        self.assertTrue(new_gzip14_toolchain != gzip14['toolchain'])
        self.assertEqual(new_gzip14_toolchain, {'name': 'dummy', 'version': ''})

        #
        # Finally test if it can recognise existing modules and use those
        #
        init_config(build_options={
            'minimal_toolchains': True,
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        barec = os.path.join(self.test_prefix, 'bar-1.2.3-goolf-1.4.10.eb')
        barec_txt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'bar'",
            "version = '1.2.3'",
            "homepage = 'http://example.com'",
            "description = 'foo'",
            "toolchain = {'name': 'goolf', 'version': '1.4.10'}",
            # deliberately listing components of toolchain as dependencies without specifying subtoolchains,
            # to test resolving of dependencies with minimal toolchain
            # for each of these, we know test easyconfigs are available (which are required here)
            "dependencies = [",
            "   ('OpenMPI', '1.6.4'),",  # available with GCC/4.7.2
            "   ('OpenBLAS', '0.2.6', '-LAPACK-3.4.2'),",  # available with gompi/1.4.10
            "   ('ScaLAPACK', '2.0.2', '-OpenBLAS-0.2.6-LAPACK-3.4.2'),",  # available with gompi/1.4.10
            "   ('SQLite', '3.8.10.2'),",  # available with goolf/1.4.10, gompi/1.4.10 and GCC/4.7.2
            "]",
        ])
        write_file(barec, barec_txt)
        bar = EasyConfig(barec)

        # Check that all bar dependencies have been processed as expected
        openmpi = bar.dependencies()[0]
        openblas = bar.dependencies()[1]
        scalapack = bar.dependencies()[2]
        sqlite = bar.dependencies()[3]
        self.assertEqual(det_full_ec_version(openmpi), '1.6.4-GCC-4.7.2')
        self.assertEqual(det_full_ec_version(openblas), '0.2.6-gompi-1.4.10-LAPACK-3.4.2')
        self.assertEqual(det_full_ec_version(scalapack), '2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2')
        self.assertEqual(det_full_ec_version(sqlite), '3.8.10.2-GCC-4.7.2')

        # Add the gompi/1.4.10 version of SQLite as an available module
        module_parent = os.path.join(self.test_prefix, 'minimal_toolchain_modules')
        module_file = os.path.join(module_parent, 'SQLite', '3.8.10.2-gompi-1.4.10')
        module_txt = '\n'.join([
            "#%Module",
            "set root /tmp/SQLite/3.8.10.2",
            "setenv EBROOTSQLITE $root",
            "setenv EBVERSIONSQLITE 3.8.10.2",
            "setenv  EBDEVELSQLITE $root/easybuild/SQLite-3.8.10.2-easybuild-devel",
        ])
        write_file(module_file, module_txt)
        os.environ['MODULEPATH'] = module_parent # Add the parent directory to the MODULEPATH
        invalidate_module_caches_for(module_parent)

        # Reinitialize the environment for the updated MODULEPATH and use_existing_modules
        init_config(build_options={
            'minimal_toolchains': True,
            'use_existing_modules': True,
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })

        # Check gompi is now being picked up
        bar = EasyConfig(barec) # Re-parse the parent easyconfig
        sqlite = bar.dependencies()[3]
        self.assertEqual(det_full_ec_version(sqlite), '3.8.10.2-gompi-1.4.10')

        # Add the goolf version as an available version and check that gets precedence over the gompi version
        module_file = os.path.join(module_parent, 'SQLite', '3.8.10.2-goolf-1.4.10')
        write_file(module_file, module_txt)
        invalidate_module_caches_for(module_parent)
        bar = EasyConfig(barec) # Re-parse the parent easyconfig
        sqlite = bar.dependencies()[3]
        self.assertEqual(det_full_ec_version(sqlite), '3.8.10.2-goolf-1.4.10')


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(RobotTest)

if __name__ == '__main__':
    unittestmain()
