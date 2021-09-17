##
# Copyright 2012-2021 Ghent University
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
Unit tests for modules.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""

import os
import re
import tempfile
import shutil
import stat
import sys
from distutils.version import StrictVersion
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.modules as mod
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import adjust_permissions, copy_file, copy_dir, mkdir
from easybuild.tools.filetools import read_file, remove_dir, remove_file, symlink, write_file
from easybuild.tools.modules import EnvironmentModules, EnvironmentModulesC, EnvironmentModulesTcl, Lmod, NoModulesTool
from easybuild.tools.modules import curr_module_paths, get_software_libdir, get_software_root, get_software_version
from easybuild.tools.modules import invalidate_module_caches_for, modules_tool, reset_module_caches
from easybuild.tools.run import run_cmd


# number of modules included for testing purposes
TEST_MODULES_COUNT = 82


class ModulesTest(EnhancedTestCase):
    """Test cases for modules."""

    def init_testmods(self, test_modules_paths=None):
        """Initialize set of test modules for test."""
        if test_modules_paths is None:
            test_modules_paths = [os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))]
        self.reset_modulepath(test_modules_paths)

    # for Lmod, this test has to run first, to avoid that it fails;
    # no modules are found if another test ran before it, but using a (very) long module path works fine interactively
    def test_long_module_path(self):
        """Test dealing with a (very) long module path."""

        # create a really long modules install path
        tmpdir = tempfile.mkdtemp()
        long_mod_path = tmpdir
        subdir = 'foo'
        # Lmod v5.1.5 doesn't support module paths longer than 256 characters, so stay just under that magic limit
        while (len(os.path.abspath(long_mod_path)) + len(subdir)) < 240:
            long_mod_path = os.path.join(long_mod_path, subdir)

        # copy one of the test modules there
        gcc_mod_dir = os.path.join(long_mod_path, 'GCC')
        os.makedirs(gcc_mod_dir)
        gcc_mod_path = os.path.join(os.path.dirname(__file__), 'modules', 'GCC', '4.6.3')
        copy_file(gcc_mod_path, gcc_mod_dir)

        # try and use long modules path
        self.init_testmods(test_modules_paths=[long_mod_path])
        ms = self.modtool.available()

        self.assertEqual(ms, ['GCC/4.6.3'])

        shutil.rmtree(tmpdir)

    def test_run_module(self):
        """Test for ModulesTool.run_module method."""

        testdir = os.path.dirname(os.path.abspath(__file__))

        for key in ['EBROOTGCC', 'EBROOTOPENMPI', 'EBROOTOPENBLAS']:
            if key in os.environ:
                del os.environ[key]

        # arguments can be passed in two ways: multiple arguments, or just 1 list argument
        self.modtool.run_module('load', 'GCC/6.4.0-2.28')
        self.assertEqual(os.environ['EBROOTGCC'], '/prefix/software/GCC/6.4.0-2.28')

        # restore original environment
        modify_env(os.environ, self.orig_environ, verbose=False)
        self.reset_modulepath([os.path.join(testdir, 'modules')])

        self.assertFalse('EBROOTGCC' in os.environ)
        self.modtool.run_module(['load', 'GCC/6.4.0-2.28'])
        self.assertEqual(os.environ['EBROOTGCC'], '/prefix/software/GCC/6.4.0-2.28')

        # skip tests that rely on exit codes when using EnvironmentModulesTcl modules tool,
        # because it doesn't use proper exit codes
        if not isinstance(self.modtool, EnvironmentModulesTcl):

            # by default, exit code is checked and an error is raised if we run something that fails
            error_pattern = "Module command '.*thisdoesnotmakesense' failed with exit code [1-9]"
            self.assertErrorRegex(EasyBuildError, error_pattern, self.modtool.run_module, 'thisdoesnotmakesense')

            # we need to use a different error pattern here with EnvironmentModulesC,
            # because a load of a non-existing module doesnt' trigger a non-zero exit code...
            # it will still fail though, just differently
            if isinstance(self.modtool, EnvironmentModulesC):
                error_pattern = "Unable to locate a modulefile for 'nosuchmodule/1.2.3'"
            else:
                error_pattern = "Module command '.*load nosuchmodule/1.2.3' failed with exit code [1-9]"
            self.assertErrorRegex(EasyBuildError, error_pattern, self.modtool.run_module, 'load', 'nosuchmodule/1.2.3')

        # we can choose to blatently ignore the exit code,
        # and also disable the output check that serves as a fallback;
        # we also enable return_output here, because trying to apply the environment changes produced
        # by a faulty command is bound to cause trouble...
        kwargs = {
            'check_exit_code': False,
            'check_output': False,
            'return_output': True,
        }
        self.modtool.run_module('thisdoesnotmakesense', **kwargs)
        self.modtool.run_module('load', 'nosuchmodule/1.2.3', **kwargs)

        # by default, the output (stdout+stderr) produced by the command is processed;
        # result is a list of useful info (module names in case of list/avail)
        res = self.modtool.run_module('list')
        self.assertEqual(res, [{'mod_name': 'GCC/6.4.0-2.28', 'default': None}])

        res = self.modtool.run_module('avail', 'GCC/4.6.3')
        self.assertTrue(isinstance(res, list))
        self.assertEqual(sorted([x['mod_name'] for x in res]), ['GCC/4.6.3'])

        # loading a module produces no output, so we get an empty list
        res = self.modtool.run_module('load', 'OpenMPI/2.1.2-GCC-6.4.0-2.28')
        self.assertEqual(res, [])
        self.assertEqual(os.environ['EBROOTOPENMPI'], '/prefix/software/OpenMPI/2.1.2-GCC-6.4.0-2.28')

        # we can opt into getting back the raw output (stdout + stderr);
        # in that cases, the output includes Python statements to change the environment;
        # the changes that would be made by the module command are *not* applied to the environment
        out = self.modtool.run_module('load', 'OpenBLAS/0.2.20-GCC-6.4.0-2.28', return_output=True)
        patterns = [
            r"^os.environ\[.EBROOTOPENBLAS.\]\s*=\s*./prefix/software/OpenBLAS/0.2.20-GCC-6.4.0-2.28.",
            r"^os.environ\[.LOADEDMODULES.\]\s*=.*OpenBLAS/0.2.20-GCC-6.4.0-2.28",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(out), "Pattern '%s' should be found in: %s" % (regex.pattern, out))

        # OpenBLAS module did *not* get loaded
        self.assertFalse('EBROOTOPENBLAS' in os.environ)
        res = self.modtool.list()
        expected = ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2-GCC-6.4.0-2.28', 'hwloc/1.11.8-GCC-6.4.0-2.28']
        self.assertEqual(sorted([x['mod_name'] for x in res]), expected)

        # we can also only obtain the stderr output (which contains the user-facing output),
        # and just drop the stdout output (which contains the statements to change the environment)
        out = self.modtool.run_module('show', 'OpenBLAS/0.2.20-GCC-6.4.0-2.28', return_stderr=True)
        patterns = [
            r"test/framework/modules/OpenBLAS/0.2.20-GCC-6.4.0-2.28:\s*$",
            r"setenv\W+EBROOTOPENBLAS.+/prefix/software/OpenBLAS/0.2.20-GCC-6.4.0-2.28",
            r"prepend[_-]path\W+LD_LIBRARY_PATH.+/prefix/software/OpenBLAS/0.2.20-GCC-6.4.0-2.28/lib",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(out), "Pattern '%s' should be found in: %s" % (regex.pattern, out))

        # show method only returns user-facing output (obtained via stderr), not changes to the environment
        regex = re.compile(r'^os\.environ\[', re.M)
        self.assertFalse(regex.search(out), "Pattern '%s' should not be found in: %s" % (regex.pattern, out))

    def test_avail(self):
        """Test if getting a (restricted) list of available modules works."""
        self.init_testmods()

        # test modules include 3 GCC modules and one GCCcore module
        ms = self.modtool.available('GCC')
        expected = ['GCC/4.6.3', 'GCC/4.6.4', 'GCC/6.4.0-2.28', 'GCC/7.3.0-2.30']
        # Tcl-only modules tool does an exact match on module name, Lmod & Tcl/C do prefix matching
        # EnvironmentModules is a subclass of EnvironmentModulesTcl, but Modules 4+ behaves similarly to Tcl/C impl.,
        # so also append GCCcore/6.2.0 if we are an instance of EnvironmentModules
        if not isinstance(self.modtool, EnvironmentModulesTcl) or isinstance(self.modtool, EnvironmentModules):
            expected.append('GCCcore/6.2.0')
        self.assertEqual(ms, expected)

        # test modules include one GCC/4.6.3 module
        ms = self.modtool.available(mod_name='GCC/4.6.3')
        self.assertEqual(ms, ['GCC/4.6.3'])

        # all test modules are accounted for
        ms = self.modtool.available()

        if isinstance(self.modtool, Lmod) and StrictVersion(self.modtool.version) >= StrictVersion('5.7.5'):
            # with recent versions of Lmod, also the hidden modules are included in the output of 'avail'
            self.assertEqual(len(ms), TEST_MODULES_COUNT + 3)
            self.assertTrue('bzip2/.1.0.6' in ms)
            self.assertTrue('toy/.0.0-deps' in ms)
            self.assertTrue('OpenMPI/.2.1.2-GCC-6.4.0-2.28' in ms)
        else:
            self.assertEqual(len(ms), TEST_MODULES_COUNT)

    def test_exist(self):
        """Test if testing for module existence works."""
        self.init_testmods()
        self.assertEqual(self.modtool.exist(['OpenMPI/2.1.2-GCC-6.4.0-2.28']), [True])
        self.assertEqual(self.modtool.exist(['OpenMPI/2.1.2-GCC-6.4.0-2.28'], skip_avail=True), [True])
        self.assertEqual(self.modtool.exist(['foo/1.2.3']), [False])
        self.assertEqual(self.modtool.exist(['foo/1.2.3'], skip_avail=True), [False])

        # exist works on hidden modules
        self.assertEqual(self.modtool.exist(['toy/.0.0-deps']), [True])
        self.assertEqual(self.modtool.exist(['toy/.0.0-deps'], skip_avail=True), [True])

        # also partial module names work
        self.assertEqual(self.modtool.exist(['OpenMPI']), [True])
        self.assertEqual(self.modtool.exist(['OpenMPI'], skip_avail=True), [True])
        # but this doesn't...
        self.assertEqual(self.modtool.exist(['OpenMPI/2.1.2']), [False])
        self.assertEqual(self.modtool.exist(['OpenMPI/2.1.2'], skip_avail=True), [False])

        # if we instruct modtool.exist not to consider partial module names, it doesn't
        self.assertEqual(self.modtool.exist(['OpenMPI'], maybe_partial=False), [False])
        self.assertEqual(self.modtool.exist(['OpenMPI'], maybe_partial=False, skip_avail=True), [False])

        # exist works on hidden modules in Lua syntax (only with Lmod)
        test_modules_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))
        if isinstance(self.modtool, Lmod):
            # make sure only the .lua module file is there, otherwise this test doesn't work as intended
            self.assertTrue(os.path.exists(os.path.join(test_modules_path, 'bzip2', '.1.0.6.lua')))
            self.assertFalse(os.path.exists(os.path.join(test_modules_path, 'bzip2', '.1.0.6')))
            self.assertEqual(self.modtool.exist(['bzip2/.1.0.6']), [True])

        # exist also works on lists of module names
        # list should be sufficiently long, since for short lists 'show' is always used
        mod_names = ['OpenMPI/2.1.2-GCC-6.4.0-2.28', 'foo/1.2.3', 'GCC',
                     'ScaLAPACK/2.0.2-gompi-2017b-OpenBLAS-0.2.20'
                     'ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20',
                     'Compiler/GCC/6.4.0-2.28/OpenMPI/2.1.2', 'toy/.0.0-deps']
        self.assertEqual(self.modtool.exist(mod_names), [True, False, True, False, True, True])
        self.assertEqual(self.modtool.exist(mod_names, skip_avail=True), [True, False, True, False, True, True])

        # verify whether checking for existence of a module wrapper works
        self.modtool.unuse(test_modules_path)
        self.modtool.use(self.test_prefix)

        java_mod_dir = os.path.join(self.test_prefix, 'Java')
        write_file(os.path.join(java_mod_dir, '1.8.0_181'), '#%Module')
        write_file(os.path.join(self.test_prefix, 'toy', '42.1337'), '#%Module')

        if self.modtool.__class__ == EnvironmentModulesC:
            modulerc_tcl_txt = '\n'.join([
                '#%Module',
                'if {"Java/1.8" eq [module-info version Java/1.8]} {',
                '    module-version Java/1.8.0_181 1.8',
                '}',
                'if {"Java/site_default" eq [module-info version Java/site_default]} {',
                '    module-version Java/1.8.0_181 site_default',
                '}',
            ])
        else:
            modulerc_tcl_txt = '\n'.join([
                '#%Module',
                'module-version Java/1.8.0_181 1.8',
                'module-version Java/1.8.0_181 site_default',
                'module-alias Java/Alias toy/42.1337',
                # 'module-alias Java/NonExist non_existant/1',  # (only) LMod has this in module avail, disable for now
                'module-alias JavaAlias Java/1.8.0_181',  # LMod 7+ only
            ])

        write_file(os.path.join(java_mod_dir, '.modulerc'), modulerc_tcl_txt)

        avail_mods = self.modtool.available()
        self.assertTrue('Java/1.8.0_181' in avail_mods)
        if isinstance(self.modtool, Lmod) and StrictVersion(self.modtool.version) >= StrictVersion('7.0'):
            self.assertTrue('Java/1.8' in avail_mods)
            self.assertTrue('Java/site_default' in avail_mods)
            self.assertTrue('JavaAlias' in avail_mods)
            self.assertEqual(self.modtool.exist(['JavaAlias']), [True])

        self.assertEqual(self.modtool.exist(['Java/1.8', 'Java/1.8.0_181']), [True, True])

        # module-version with different version suffix than the base module
        self.assertEqual(self.modtool.exist(['Java/site_default']), [True])
        # Check for aliases:
        # - completely different nameTrue, True,
        # - alias to non existant module
        # Skipped for EnvironmentModulesC as module-alias not working correctly there
        if self.modtool.__class__ != EnvironmentModulesC:
            self.assertEqual(self.modtool.exist(['Java/Alias', 'Java/NonExist']), [True, False])

        # set 'module avail' cache entries to empty lists,
        # to enforce fallback to 'module show'
        import easybuild.tools.modules
        for key in easybuild.tools.modules.MODULE_AVAIL_CACHE:
            easybuild.tools.modules.MODULE_AVAIL_CACHE[key] = []

        # clear 'module show' cache, to keep control below
        easybuild.tools.modules.MODULE_SHOW_CACHE.clear()
        self.assertEqual(self.modtool.exist(['Java/1.8', 'Java/1.8.0_181']), [True, True])

        # mimic more verbose stderr output produced by old Tmod version,
        # including a warning produced when multiple .modulerc files are being picked up
        # see https://github.com/easybuilders/easybuild-framework/issues/3376
        ml_show_java18_stderr = '\n'.join([
            "module-version    Java/1.8.0_181 1.8",
            "WARNING: Duplicate version symbol '1.8' found",
            "module-version  Java/1.8.0_181 1.8",
            "-------------------------------------------------------------------",
            "/modulefiles/lang/Java/1.8.0_181:",
            "-------------------------------------------------------------------",
        ])

        # overwrite 'module show' cache entries with output that includes extra lines
        for key in easybuild.tools.modules.MODULE_SHOW_CACHE:
            easybuild.tools.modules.MODULE_SHOW_CACHE[key] = ml_show_java18_stderr

        self.assertEqual(self.modtool.exist(['Java/1.8', 'Java/1.8.0_181']), [True, True])

        reset_module_caches()

        # what if we're in an HMNS setting...
        mkdir(os.path.join(self.test_prefix, 'Core'))
        shutil.move(java_mod_dir, os.path.join(self.test_prefix, 'Core', 'Java'))

        self.assertTrue('Core/Java/1.8.0_181' in self.modtool.available())
        self.assertEqual(self.modtool.exist(['Core/Java/1.8.0_181']), [True])
        # there's a workaround to ensure that module wrappers/aliases are recognized when they're
        # being checked with the full module name (see https://github.com/TACC/Lmod/issues/446);
        # that's necessary when using a hierarchical module naming scheme,
        # see https://github.com/easybuilders/easybuild-framework/issues/3335
        self.assertEqual(self.modtool.exist(['Core/Java/1.8', 'Core/Java/site_default']), [True, True])

        # also check with .modulerc.lua for Lmod 7.8 or newer
        if isinstance(self.modtool, Lmod) and StrictVersion(self.modtool.version) >= StrictVersion('7.8'):
            shutil.move(os.path.join(self.test_prefix, 'Core', 'Java'), java_mod_dir)
            reset_module_caches()

            remove_file(os.path.join(java_mod_dir, '.modulerc'))
            write_file(os.path.join(java_mod_dir, '.modulerc.lua'),
                       '\n'.join([
                           'module_version("Java/1.8.0_181", "1.8")',
                           'module_version("Java/1.8.0_181", "site_default")',
                           'module_alias("JavaAlias", "Java/1.8")',
                       ]))

            avail_mods = self.modtool.available()
            self.assertTrue('Java/1.8.0_181' in avail_mods)
            self.assertTrue('Java/1.8' in avail_mods)
            self.assertEqual(self.modtool.exist(['Java/1.8', 'Java/1.8.0_181']), [True, True])

            # check for an alias with a different version suffix than the base module
            self.assertEqual(self.modtool.exist(['Java/site_default']), [True])
            # And completely different name
            self.assertEqual(self.modtool.exist(['JavaAlias']), [True])

            reset_module_caches()

            # back to HMNS setup
            shutil.move(java_mod_dir, os.path.join(self.test_prefix, 'Core', 'Java'))
            self.assertTrue('Core/Java/1.8.0_181' in self.modtool.available())
            self.assertEqual(self.modtool.exist(['Core/Java/1.8.0_181']), [True])
            self.assertEqual(self.modtool.exist(['Core/Java/1.8']), [True])
            self.assertEqual(self.modtool.exist(['Core/Java/site_default']), [True])

        # Test alias in home directory .modulerc
        if isinstance(self.modtool, Lmod) and StrictVersion(self.modtool.version) >= StrictVersion('7.0'):
            # Required or temporary HOME would be in MODULEPATH already
            self.init_testmods()
            # Sanity check: Module aliases don't exist yet
            self.assertEqual(self.modtool.exist(['OpenMPI/99', 'OpenMPIAlias']), [False, False])
            # Use a temporary dir, not the users HOME
            os.environ['HOME'] = tempfile.mkdtemp()
            reset_module_caches()
            write_file(os.path.join(os.environ['HOME'], '.modulerc'), '\n'.join([
                '#%Module',
                'module-version OpenMPI/2.1.2-GCC-6.4.0-2.28 99',
                'module-alias OpenMPIAlias OpenMPI/2.1.2-GCC-6.4.0-2.28',
            ]))
            self.assertEqual(self.modtool.exist(['OpenMPI/99', 'OpenMPIAlias']), [True, True])

    def test_load(self):
        """ test if we load one module it is in the loaded_modules """
        self.init_testmods()
        ms = self.modtool.available()
        # exclude modules not on the top level of a hierarchy
        ms = [m for m in ms if not (m.startswith('Core') or m.startswith('Compiler/') or m.startswith('MPI/') or
                                    m.startswith('CategorizedHMNS'))]

        for m in ms:
            self.modtool.load([m])
            self.assertTrue(m in self.modtool.loaded_modules())
            self.modtool.purge()

        # trying to load a module not on the top level of a hierarchy should fail
        modnames = [
            # module use on non-existent dir (Tcl-based env mods), or missing dep (Lmod)
            'Compiler/GCC/6.4.0-2.28/OpenMPI/2.1.2',
            # missing dep
            'MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2/ScaLAPACK/2.0.2-OpenBLAS-0.2.20',
        ]
        for modname in modnames:
            self.assertErrorRegex(EasyBuildError, '.*', self.modtool.load, [modname])

        # by default, modules are always loaded, even if they are already loaded
        self.modtool.load(['GCC/6.4.0-2.28', 'OpenMPI/2.1.2-GCC-6.4.0-2.28'])

        # unset $EBROOTGCC, it should get set again later by loading GCC again
        del os.environ['EBROOTGCC']

        # GCC should be loaded, but should not be listed last (OpenMPI was loaded last)
        loaded_modules = self.modtool.loaded_modules()
        self.assertTrue('GCC/6.4.0-2.28' in loaded_modules)
        self.assertFalse(loaded_modules[-1] == 'GCC/6.4.0-2.28')

        # if GCC is loaded again, $EBROOTGCC should be set again, and GCC should be listed last
        self.modtool.load(['GCC/6.4.0-2.28'])

        # environment modules v4.0 does not reload already loaded modules, will be changed in v4.2
        modtool_ver = StrictVersion(self.modtool.version)
        if not isinstance(self.modtool, EnvironmentModules) or modtool_ver >= StrictVersion('4.2'):
            self.assertTrue(os.environ.get('EBROOTGCC'))

        if isinstance(self.modtool, Lmod):
            # order of loaded modules only changes with Lmod
            self.assertTrue(self.modtool.loaded_modules()[-1] == 'GCC/6.4.0-2.28')

        # set things up for checking that GCC does *not* get reloaded when requested
        if 'EBROOTGCC' in os.environ:
            del os.environ['EBROOTGCC']
        self.modtool.load(['OpenMPI/2.1.2-GCC-6.4.0-2.28'])
        if isinstance(self.modtool, Lmod):
            # order of loaded modules only changes with Lmod
            self.assertTrue(self.modtool.loaded_modules()[-1] == 'OpenMPI/2.1.2-GCC-6.4.0-2.28')

        # reloading can be disabled using allow_reload=False
        self.modtool.load(['GCC/6.4.0-2.28'], allow_reload=False)
        self.assertEqual(os.environ.get('EBROOTGCC'), None)
        self.assertFalse(loaded_modules[-1] == 'GCC/6.4.0-2.28')

    def test_show(self):
        """Test for ModulesTool.show method."""

        out = self.modtool.show('GCC/7.3.0-2.30')

        patterns = [
            # full path to module is included in output of 'show'
            r"test/framework/modules/GCC/7.3.0-2.30:\s*$",
            r"setenv\W+EBROOTGCC.+prefix/software/GCC/7.3.0-2.30",
            r"^prepend[_-]path\W+PATH.+/prefix/software/GCC/7.3.0-2.30/bin",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(out), "Pattern '%s' should be found in: %s" % (regex.pattern, out))

        # show method only returns user-facing output (obtained via stderr), not changes to the environment
        regex = re.compile(r'^os\.environ\[', re.M)
        self.assertFalse(regex.search(out), "Pattern '%s' should not be found in: %s" % (regex.pattern, out))

    def test_curr_module_paths(self):
        """Test for curr_module_paths function."""

        # first, create a couple of (empty) directories to use as entries in $MODULEPATH
        test1 = os.path.join(self.test_prefix, 'test1')
        mkdir(test1)
        test2 = os.path.join(self.test_prefix, 'test2')
        mkdir(test2)
        test3 = os.path.join(self.test_prefix, 'test3')
        mkdir(test3)

        os.environ['MODULEPATH'] = ''
        self.assertEqual(curr_module_paths(), [])

        os.environ['MODULEPATH'] = '%s:%s:%s' % (test1, test2, test3)
        self.assertEqual(curr_module_paths(), [test1, test2, test3])

        # empty entries and non-existing directories are filtered out
        os.environ['MODULEPATH'] = '/doesnotexist:%s::%s:' % (test2, test1)
        self.assertEqual(curr_module_paths(), [test2, test1])

    def test_check_module_path(self):
        """Test ModulesTool.check_module_path() method"""

        # first, create a couple of (empty) directories to use as entries in $MODULEPATH
        test1 = os.path.join(self.test_prefix, 'test1')
        mkdir(test1)
        test2 = os.path.join(self.test_prefix, 'test2')
        mkdir(test2)
        test3 = os.path.join(self.test_prefix, 'test3')
        mkdir(test3)

        os.environ['MODULEPATH'] = test1

        modtool = modules_tool()

        # directory where modules are installed based on current configuration is automatically added in front
        mod_install_dir = os.path.join(self.test_installpath, 'modules', 'all')
        self.assertEqual(modtool.mod_paths, [mod_install_dir, test1])

        # if mod_paths is reset, it can be restored using check_module_path
        modtool.mod_paths = None
        modtool.check_module_path()
        self.assertEqual(modtool.mod_paths, [mod_install_dir, test1])

        # no harm done with multiple subsequent calls
        modtool.check_module_path()
        self.assertEqual(modtool.mod_paths, [mod_install_dir, test1])

        # if $MODULEPATH is tweaked, mod_paths and $MODULEPATH can be corrected with check_module_path
        os.environ['MODULEPATH'] = test2
        modtool.check_module_path()
        self.assertEqual(modtool.mod_paths, [mod_install_dir, test1, test2])
        self.assertEqual(os.environ['MODULEPATH'], os.pathsep.join([mod_install_dir, test1, test2]))

        # check behaviour if non-existing directories are included in $MODULEPATH
        os.environ['MODULEPATH'] = '%s:/does/not/exist:%s' % (test3, test2)
        modtool.check_module_path()
        # non-existing dir is filtered from mod_paths, but stays in $MODULEPATH
        self.assertEqual(modtool.mod_paths, [mod_install_dir, test1, test3, test2])
        self.assertEqual(os.environ['MODULEPATH'],
                         os.pathsep.join([mod_install_dir, test1, test3, '/does/not/exist', test2]))

    def test_check_module_path_hmns(self):
        """Test behaviour of check_module_path with HierarchicalMNS."""

        # to verify that https://github.com/easybuilders/easybuild-framework/issues/3084 is fixed
        # (see also https://github.com/easybuilders/easybuild-framework/issues/2226);
        # this bug can be triggered by having at least one non-existing directory in $MODULEPATH,
        # and using HierarchicalMNS

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config()

        top_mod_dir = os.path.join(self.test_installpath, 'modules', 'all')
        core_mod_dir = os.path.join(top_mod_dir, 'Core')
        mkdir(core_mod_dir, parents=True)

        doesnotexist = os.path.join(self.test_prefix, 'doesnotexist')
        self.assertFalse(os.path.exists(doesnotexist))

        os.environ['MODULEPATH'] = '%s:%s' % (core_mod_dir, doesnotexist)
        modtool = modules_tool()

        self.assertEqual(modtool.mod_paths, [os.path.dirname(core_mod_dir), core_mod_dir])
        self.assertEqual(os.environ['MODULEPATH'], '%s:%s:%s' % (top_mod_dir, core_mod_dir, doesnotexist))

        # hack prepend_module_path to make sure it's not called again if check_module_path is called again;
        # prepend_module_path is fairly expensive, so should be avoided,
        # see https://github.com/easybuilders/easybuild-framework/issues/3084
        def broken_prepend_module_path(*args, **kwargs):
            raise EasyBuildError("broken prepend_module_path")

        modtool.prepend_module_path = broken_prepend_module_path

        # if this doesn't trigger a raised error from the hacked prepend_module_path, the bug is fixed
        modtool.check_module_path()

        self.assertEqual(modtool.mod_paths, [os.path.dirname(core_mod_dir), core_mod_dir])
        self.assertEqual(os.environ['MODULEPATH'], '%s:%s:%s' % (top_mod_dir, core_mod_dir, doesnotexist))

    def test_prepend_module_path(self):
        """Test prepend_module_path method."""
        test_path = tempfile.mkdtemp(prefix=self.test_prefix)
        self.modtool.prepend_module_path(test_path)
        self.assertTrue(os.path.samefile(curr_module_paths()[0], test_path))

        # prepending same path again is fine, no changes to $MODULEPATH
        modulepath = curr_module_paths()
        self.modtool.prepend_module_path(test_path)
        self.assertEqual(modulepath, curr_module_paths())

        # prepending path that is 'deeper down' in $MODULEPATH works, brings it back to front
        test_mods_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules')
        self.assertTrue(any(os.path.samefile(test_mods_dir, p) for p in modulepath))
        self.modtool.prepend_module_path(test_mods_dir)
        self.assertTrue(os.path.samefile(curr_module_paths()[0], test_mods_dir))

        # prepending path that is a symlink to the current head of $MODULEPATH is a no-op
        modulepath = curr_module_paths()
        symlink_path = os.path.join(self.test_prefix, 'symlink_modules')
        os.symlink(modulepath[0], symlink_path)
        self.modtool.prepend_module_path(symlink_path)
        self.assertEqual(modulepath, curr_module_paths())

        # test prepending with high priority
        test_path_bis = tempfile.mkdtemp(prefix=self.test_prefix)
        test_path_tris = tempfile.mkdtemp(prefix=self.test_prefix)
        self.modtool.prepend_module_path(test_path_bis, priority=10000)
        self.assertEqual(test_path_bis, curr_module_paths()[0])

        # check whether prepend with priority actually works (only for Lmod)
        if isinstance(self.modtool, Lmod):
            self.modtool.prepend_module_path(test_path_tris)
            modulepath = curr_module_paths()
            self.assertEqual(test_path_bis, modulepath[0])
            self.assertEqual(test_path_tris, modulepath[1])

    def test_ld_library_path(self):
        """Make sure LD_LIBRARY_PATH is what it should be when loaded multiple modules."""
        self.init_testmods()

        testpath = '/this/is/just/a/test'
        os.environ['LD_LIBRARY_PATH'] = testpath

        # load module and check that previous LD_LIBRARY_PATH is still there, at the end
        self.modtool.load(['GCC/4.6.3'])
        self.assertTrue(re.search("%s$" % testpath, os.environ['LD_LIBRARY_PATH']))
        self.modtool.purge()

        # check that previous LD_LIBRARY_PATH is still there, at the end
        self.assertTrue(re.search("%s$" % testpath, os.environ['LD_LIBRARY_PATH']))
        self.modtool.purge()

    def test_purge(self):
        """Test if purging of modules works."""
        self.init_testmods()
        ms = self.modtool.available()

        self.modtool.load([ms[0]])
        self.assertTrue(len(self.modtool.loaded_modules()) > 0)

        self.modtool.purge()
        self.assertTrue(len(self.modtool.loaded_modules()) == 0)

        self.modtool.purge()
        self.assertTrue(len(self.modtool.loaded_modules()) == 0)

    def test_get_software_root_version_libdir(self):
        """Test get_software_X functions."""

        tmpdir = tempfile.mkdtemp()
        test_cases = [
            ('GCC', 'GCC'),
            ('grib_api', 'GRIB_API'),
            ('netCDF-C++', 'NETCDFMINCPLUSPLUS'),
            ('Score-P', 'SCOREMINP'),
        ]
        for (name, env_var_name) in test_cases:
            # mock stuff that get_software_X functions rely on
            root = os.path.join(tmpdir, name)
            mkdir(os.path.join(root, 'lib'), parents=True)
            os.environ['EBROOT%s' % env_var_name] = root
            version = '0.0-%s' % root
            os.environ['EBVERSION%s' % env_var_name] = version

            self.assertEqual(get_software_root(name), root)
            self.assertEqual(get_software_version(name), version)
            self.assertEqual(get_software_libdir(name), 'lib')

            os.environ.pop('EBROOT%s' % env_var_name)
            os.environ.pop('EBVERSION%s' % env_var_name)

        # check expected result of get_software_libdir with multiple lib subdirs
        root = os.path.join(tmpdir, name)
        mkdir(os.path.join(root, 'lib64'))
        os.environ['EBROOT%s' % env_var_name] = root
        self.assertErrorRegex(EasyBuildError, "Multiple library subdirectories found.*", get_software_libdir, name)
        self.assertEqual(get_software_libdir(name, only_one=False), ['lib', 'lib64'])

        # only directories containing files in specified list should be retained
        write_file(os.path.join(root, 'lib64', 'foo'), 'foo')
        self.assertEqual(get_software_libdir(name, fs=['foo']), 'lib64')

        # duplicate paths due to symlink get filtered
        remove_dir(os.path.join(root, 'lib64'))
        symlink(os.path.join(root, 'lib'), os.path.join(root, 'lib64'))
        self.assertEqual(get_software_libdir(name), 'lib')

        # same goes for lib symlinked to lib64
        remove_file(os.path.join(root, 'lib64'))
        remove_dir(os.path.join(root, 'lib'))
        mkdir(os.path.join(root, 'lib64'))
        symlink(os.path.join(root, 'lib64'), os.path.join(root, 'lib'))
        # still returns 'lib' because that's the first subdir considered
        self.assertEqual(get_software_libdir(name), 'lib')

        # clean up for previous tests
        os.environ.pop('EBROOT%s' % env_var_name)

        # if root/version for specified software package can not be found, these functions should return None
        self.assertEqual(get_software_root('foo'), None)
        self.assertEqual(get_software_version('foo'), None)
        self.assertEqual(get_software_libdir('foo'), None)

        # if no library subdir is found, get_software_libdir should return None
        os.environ['EBROOTFOO'] = tmpdir
        self.assertEqual(get_software_libdir('foo'), None)
        os.environ.pop('EBROOTFOO')

        shutil.rmtree(tmpdir)

    def test_wrong_modulepath(self):
        """Test whether modules tool can deal with a broken $MODULEPATH."""
        test_modules_path = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules'))
        modules_test_installpath = os.path.join(self.test_installpath, 'modules', 'all')
        os.environ['MODULEPATH'] = '/some/non-existing/path:/this/doesnt/exists/anywhere:%s' % test_modules_path
        init_config()
        # purposely *not* using self.modtool here;
        # need to check whether creating new ModulesTool instance doesn't break when $MODULEPATH contains faulty paths
        modtool = modules_tool()
        self.assertEqual(len(modtool.mod_paths), 2)
        self.assertTrue(os.path.samefile(modtool.mod_paths[0], modules_test_installpath))
        self.assertEqual(modtool.mod_paths[1], test_modules_path)
        self.assertTrue(len(modtool.available()) > 0)

    def test_modulefile_path(self):
        """Test modulefile_path method"""
        test_dir = os.path.abspath(os.path.dirname(__file__))
        gcc_mod_file = os.path.join(test_dir, 'modules', 'GCC', '6.4.0-2.28')

        modtool = modules_tool()
        res = modtool.modulefile_path('GCC/6.4.0-2.28')
        self.assertTrue(os.path.samefile(res, gcc_mod_file))

        if isinstance(self.modtool, Lmod):
            res = modtool.modulefile_path('bzip2/.1.0.6')
            self.assertTrue(os.path.samefile(res, os.path.join(test_dir, 'modules', 'bzip2', '.1.0.6.lua')))
            res = modtool.modulefile_path('bzip2/.1.0.6', strip_ext=True)
            self.assertTrue(res.endswith('test/framework/modules/bzip2/.1.0.6'))

        reset_module_caches()

    def test_path_to_top_of_module_tree(self):
        """Test function to determine path to top of the module tree."""

        deps = ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2-GCC-6.4.0-2.28']
        path = self.modtool.path_to_top_of_module_tree([], 'gompi/2018a', '', deps)
        self.assertEqual(path, [])
        path = self.modtool.path_to_top_of_module_tree([], 'toy/.0.0-deps', '', ['gompi/2018a'])
        self.assertEqual(path, [])
        path = self.modtool.path_to_top_of_module_tree([], 'toy/0.0', '', [])
        self.assertEqual(path, [])

    def test_path_to_top_of_module_tree_hierarchical_mns(self):
        """Test function to determine path to top of the module tree for a hierarchical module naming scheme."""

        ecs_dir = os.path.join(os.path.dirname(__file__), 'easyconfigs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [ecs_dir],
            'valid_stops': all_stops,
            'validate': False,
        }
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options=build_options)
        self.setup_hierarchical_modules()
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')
        core = os.path.join(mod_prefix, 'Core')
        init_modpaths = [core]

        deps = ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2', 'FFTW/3.3.7', 'OpenBLAS/0.2.20',
                'ScaLAPACK/2.0.2-OpenBLAS-0.2.20']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'foss/2018a', core, deps)
        self.assertEqual(path, [])
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'GCC/6.4.0-2.28', core, [])
        self.assertEqual(path, [])

        # toolchain module must be loaded to determine path to top of module tree for non-Core modules
        self.modtool.load(['GCC/6.4.0-2.28'])
        full_mod_subdir = os.path.join(mod_prefix, 'Compiler', 'GCC', '6.4.0-2.28')
        deps = ['GCC/6.4.0-2.28', 'hwloc/1.11.8']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'OpenMPI/2.1.2', full_mod_subdir, deps)
        self.assertEqual(path, ['GCC/6.4.0-2.28'])

        self.modtool.load(['gompi/2018a'])
        full_mod_subdir = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2')
        deps = ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'FFTW/3.3.7', full_mod_subdir, deps)
        self.assertEqual(path, ['OpenMPI/2.1.2', 'GCC/6.4.0-2.28'])

    def test_path_to_top_of_module_tree_lua(self):
        """Test path_to_top_of_module_tree function on modules in Lua syntax."""
        if isinstance(self.modtool, Lmod):
            orig_modulepath = os.environ.get('MODULEPATH')
            self.modtool.unuse(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules'))
            curr_modulepath = os.environ.get('MODULEPATH')
            error_msg = "Incorrect $MODULEPATH value after unuse: %s (orig: %s)" % (curr_modulepath, orig_modulepath)
            self.assertEqual(curr_modulepath, None, error_msg)

            top_moddir = os.path.join(self.test_prefix, 'test_modules')
            core_dir = os.path.join(top_moddir, 'Core')
            mkdir(core_dir, parents=True)
            self.modtool.use(core_dir)
            self.assertTrue(os.path.samefile(os.environ.get('MODULEPATH'), core_dir))

            # install toy modules in Lua syntax that are sufficient to test path_to_top_of_module_tree with
            intel_mod_dir = os.path.join(top_moddir, 'Compiler', 'intel', '2016')
            intel_mod = 'prepend_path("MODULEPATH", "%s")\n' % intel_mod_dir
            write_file(os.path.join(core_dir, 'intel', '2016.lua'), intel_mod)

            impi_mod_dir = os.path.join(top_moddir, 'MPI', 'intel', '2016', 'impi', '2016')
            impi_mod = 'prepend_path("MODULEPATH", "%s")\n' % impi_mod_dir
            write_file(os.path.join(intel_mod_dir, 'impi', '2016.lua'), impi_mod)

            imkl_mod = 'io.stderr:write("Hi from the imkl module")\n'
            write_file(os.path.join(impi_mod_dir, 'imkl', '2016.lua'), imkl_mod)

            self.assertEqual(self.modtool.available(), ['intel/2016'])

            imkl_deps = ['intel/2016', 'impi/2016']

            # modules that compose toolchain are expected to be loaded
            self.modtool.load(imkl_deps)

            res = self.modtool.path_to_top_of_module_tree(core_dir, 'imkl/2016', impi_mod_dir, imkl_deps)
            self.assertEqual(res, ['impi/2016', 'intel/2016'])

        else:
            print("Skipping test_path_to_top_of_module_tree_lua, requires Lmod as modules tool")

    def test_interpret_raw_path_lua(self):
        """Test interpret_raw_path_lua method"""

        self.assertEqual(self.modtool.interpret_raw_path_lua('"test"'), "test")
        self.assertEqual(self.modtool.interpret_raw_path_lua('"just/a/path"'), "just/a/path")

        os.environ['TEST_VAR'] = 'test123'
        self.assertEqual(self.modtool.interpret_raw_path_lua('os.getenv("TEST_VAR")'), 'test123')
        self.assertEqual(self.modtool.interpret_raw_path_lua('os.getenv("NO_SUCH_ENVIRONMENT_VARIABLE")'), '')

        lua_str = 'pathJoin(os.getenv("TEST_VAR"), "bar")'
        self.assertEqual(self.modtool.interpret_raw_path_lua(lua_str), 'test123/bar')

        lua_str = 'pathJoin("foo", os.getenv("TEST_VAR"), "bar", os.getenv("TEST_VAR"))'
        self.assertEqual(self.modtool.interpret_raw_path_lua(lua_str), 'foo/test123/bar/test123')

    def test_interpret_raw_path_tcl(self):
        """Test interpret_raw_path_tcl method"""

        self.assertEqual(self.modtool.interpret_raw_path_tcl('"test"'), "test")
        self.assertEqual(self.modtool.interpret_raw_path_tcl('"just/a/path"'), "just/a/path")

        os.environ['TEST_VAR'] = 'test123'
        self.assertEqual(self.modtool.interpret_raw_path_tcl('$env(TEST_VAR)'), 'test123')
        self.assertEqual(self.modtool.interpret_raw_path_tcl('$env(NO_SUCH_ENVIRONMENT_VARIABLE)'), '')

        self.assertEqual(self.modtool.interpret_raw_path_tcl('$env(TEST_VAR)/bar'), 'test123/bar')

        tcl_str = 'foo/$env(TEST_VAR)/bar/$env(TEST_VAR)'
        self.assertEqual(self.modtool.interpret_raw_path_tcl(tcl_str), 'foo/test123/bar/test123')

        tcl_str = '[ file join $env(TEST_VAR) "foo/bar" ]'
        self.assertEqual(self.modtool.interpret_raw_path_tcl(tcl_str), 'test123/foo/bar')

    def test_modpath_extensions_for(self):
        """Test modpath_extensions_for method."""
        self.setup_hierarchical_modules()

        mod_dir = os.path.join(self.test_installpath, 'modules', 'all')
        expected = {
            'GCC/6.4.0-2.28': [os.path.join(mod_dir, 'Compiler', 'GCC', '6.4.0-2.28')],
            'OpenMPI/2.1.2': [os.path.join(mod_dir, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2')],
            'FFTW/3.3.7': [],
        }
        res = self.modtool.modpath_extensions_for(['GCC/6.4.0-2.28', 'OpenMPI/2.1.2', 'FFTW/3.3.7'])
        self.assertEqual(res, expected)

        intel_mod_dir = os.path.join(mod_dir, 'Compiler', 'intel')
        expected = {
            'icc/2016.1.150-GCC-4.9.3-2.25': [os.path.join(intel_mod_dir, '2016.1.150-GCC-4.9.3-2.25')],
            'ifort/2016.1.150-GCC-4.9.3-2.25': [os.path.join(intel_mod_dir, '2016.1.150-GCC-4.9.3-2.25')],
        }
        res = self.modtool.modpath_extensions_for(['icc/2016.1.150-GCC-4.9.3-2.25', 'ifort/2016.1.150-GCC-4.9.3-2.25'])
        self.assertEqual(res, expected)

        # error for non-existing modules
        error_pattern = "Can't get value from a non-existing module"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.modtool.modpath_extensions_for, ['nosuchmodule/1.2'])

        # make sure $HOME/$USER is set to something we can easily check
        os.environ['HOME'] = os.path.join(self.test_prefix, 'HOME')
        os.environ['USER'] = 'testuser'

        mkdir(os.path.join(self.test_prefix, os.environ['USER'], 'test'), parents=True)

        # test result in case conditional loads are used
        test_mod = 'test-modpaths/1.2.3.4'
        test_modfile = os.path.join(mod_dir, test_mod)

        # only prepend-path entries for MODULEPATH and 'module use' statements are really relevant
        test_modtxt = '\n'.join([
            '#%Module',
            'prepend-path PATH /example/bin',
            "    module use %s/Compiler/intel/2016.1.150-GCC-4.9.3-2.25" % mod_dir,  # indented without guard
            # quoted path
            'module use "%s/Compiler/GCC/6.4.0-2.28"' % mod_dir,
            # using prepend-path & quoted
            ' prepend-path MODULEPATH [ file join %s "MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2" ]' % mod_dir,
            # conditional 'use' on subdirectory in $HOME, e.g. when --subdir-user-modules is used
            "if { [ file isdirectory $env(HOME)/modules/Compiler/GCC/6.4.0-2.28 ] } {",
            '    module use [ file join $env(HOME) "modules/Compiler/GCC/6.4.0-2.28" ]',
            "}",
            "setenv EXAMPLE example",
            # more (fictional) extensions that use os.getenv
            'prepend-path   MODULEPATH    "$env(HOME)"',
            'module use  "%s/$env(USER)/test"' % self.test_prefix,
        ])
        write_file(test_modfile, test_modtxt)

        expected = {
            test_mod: [
                os.path.join(mod_dir, 'Compiler', 'intel', '2016.1.150-GCC-4.9.3-2.25'),
                os.path.join(mod_dir, 'Compiler', 'GCC', '6.4.0-2.28'),
                os.path.join(mod_dir, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2'),
                os.path.join(os.environ['HOME'], 'modules', 'Compiler', 'GCC', '6.4.0-2.28'),
                os.environ['HOME'],
                os.path.join(self.test_prefix, os.environ['USER'], 'test'),
            ]
        }
        self.assertEqual(self.modtool.modpath_extensions_for([test_mod]), expected)

        # also test with module file in Lua syntax if Lmod is used as modules tool
        if isinstance(self.modtool, Lmod):

            test_mod = 'test-modpaths-lua/1.2.3.4'
            test_modfile = os.path.join(mod_dir, test_mod + '.lua')

            # only prepend_path entries for MODULEPATH are really relevant
            test_modtxt = '\n'.join([
                'prepend_path("PATH", "/example/bin")',
                # indented without guard
                '   prepend_path("MODULEPATH", "%s/Compiler/intel/2016.1.150-GCC-4.9.3-2.25")' % mod_dir,
                'prepend_path("MODULEPATH","%s/Compiler/GCC/6.4.0-2.28")' % mod_dir,
                'prepend_path("MODULEPATH", "%s/MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2")' % mod_dir,
                # conditional 'use' on subdirectory in $HOME, e.g. when --subdir-user-modules is used
                'if isDir(pathJoin(os.getenv("HOME"), "modules/Compiler/GCC/6.4.0-2.28")) then',
                '    prepend_path("MODULEPATH", pathJoin(os.getenv("HOME"), "modules/Compiler/GCC/6.4.0-2.28"))',
                'end',
                'setenv("EXAMPLE", "example")',
                # more (fictional) extensions that use os.getenv
                'prepend_path("MODULEPATH", os.getenv("HOME"))',
                'prepend_path("MODULEPATH", pathJoin("%s", os.getenv("USER"), "test"))' % self.test_prefix,
            ])
            write_file(test_modfile, test_modtxt)

            expected = {test_mod: expected['test-modpaths/1.2.3.4']}

            self.assertEqual(self.modtool.modpath_extensions_for([test_mod]), expected)

    def test_path_to_top_of_module_tree_categorized_hmns(self):
        """
        Test function to determine path to top of the module tree for a categorized hierarchical module naming
        scheme.
        """

        ecs_dir = os.path.join(os.path.dirname(__file__), 'easyconfigs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [ecs_dir],
            'valid_stops': all_stops,
            'validate': False,
        }
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'CategorizedHMNS'
        init_config(build_options=build_options)
        self.setup_categorized_hmns_modules()
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')
        init_modpaths = [os.path.join(mod_prefix, 'Core', 'compiler'), os.path.join(mod_prefix, 'Core', 'toolchain')]

        deps = ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2', 'FFTW/3.3.7', 'OpenBLAS/0.2.20',
                'ScaLAPACK/2.0.2-OpenBLAS-0.2.20']
        core = os.path.join(mod_prefix, 'Core')
        tc = os.path.join(core, 'toolchain')
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'foss/2018a', tc, deps)
        self.assertEqual(path, [])
        comp = os.path.join(core, 'compiler')
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'GCC/6.4.0-2.28', comp, [])
        self.assertEqual(path, [])

        # toolchain module must be loaded to determine path to top of module tree for non-Core modules
        self.modtool.load(['GCC/6.4.0-2.28'])
        full_mod_subdir = os.path.join(mod_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'mpi')
        deps = ['GCC/6.4.0-2.28', 'hwloc/1.11.8']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'OpenMPI/2.1.2', full_mod_subdir, deps)
        self.assertEqual(path, ['GCC/6.4.0-2.28'])

        self.modtool.load(['gompi/2018a'])
        full_mod_subdir = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2', 'numlib')
        deps = ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'FFTW/3.3.7', full_mod_subdir, deps)
        self.assertEqual(path, ['OpenMPI/2.1.2', 'GCC/6.4.0-2.28'])

    def test_modules_tool_stateless(self):
        """Check whether ModulesTool instance is stateless between runs."""
        test_modules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules')

        # copy test Core/Compiler modules, we need to rewrite the 'module use' statement in the one we're going to load
        copy_dir(os.path.join(test_modules_path, 'Core'), os.path.join(self.test_prefix, 'Core'))
        copy_dir(os.path.join(test_modules_path, 'Compiler'), os.path.join(self.test_prefix, 'Compiler'))

        modtxt = read_file(os.path.join(self.test_prefix, 'Core', 'GCC', '6.4.0-2.28'))
        modpath_extension = os.path.join(self.test_prefix, 'Compiler', 'GCC', '6.4.0-2.28')
        modtxt = re.sub('module use .*', 'module use %s' % modpath_extension, modtxt, re.M)
        write_file(os.path.join(self.test_prefix, 'Core', 'GCC', '6.4.0-2.28'), modtxt)

        modtxt = read_file(os.path.join(self.test_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2'))
        modpath_extension = os.path.join(self.test_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2')
        mkdir(modpath_extension, parents=True)
        modtxt = re.sub('module use .*', 'module use %s' % modpath_extension, modtxt, re.M)
        write_file(os.path.join(self.test_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2'), modtxt)

        # force reset of any singletons by reinitiating config
        init_config()

        # make sure $LMOD_DEFAULT_MODULEPATH, since Lmod picks it up and tweaks $MODULEPATH to match it
        if 'LMOD_DEFAULT_MODULEPATH' in os.environ:
            del os.environ['LMOD_DEFAULT_MODULEPATH']

        self.reset_modulepath([os.path.join(self.test_prefix, 'Core')])

        if isinstance(self.modtool, Lmod):
            # GCC/4.6.3 is nowhere to be found (in $MODULEPATH)
            load_err_msg = r"The[\s\n]*following[\s\n]*module\(s\)[\s\n]*are[\s\n]*unknown"
        else:
            load_err_msg = "Unable to locate a modulefile"

        # GCC/4.6.3 is *not* an available Core module
        os.environ['LC_ALL'] = 'C'
        self.assertErrorRegex(EasyBuildError, load_err_msg, self.modtool.load, ['GCC/4.6.3'])

        # GCC/6.4.0-2.28 is one of the available Core modules
        self.modtool.load(['GCC/6.4.0-2.28'])

        # OpenMPI/2.1.2 becomes available after loading GCC/6.4.0-2.28 module
        self.modtool.load(['OpenMPI/2.1.2'])
        self.modtool.purge()

        if 'LMOD_DEFAULT_MODULEPATH' in os.environ:
            del os.environ['LMOD_DEFAULT_MODULEPATH']

        # reset $MODULEPATH, obtain new ModulesTool instance,
        # which should not remember anything w.r.t. previous $MODULEPATH value
        os.environ['MODULEPATH'] = test_modules_path
        self.modtool = modules_tool()

        # GCC/4.6.3 is available
        self.modtool.load(['GCC/4.6.3'])
        self.modtool.purge()

        # GCC/6.4.0-2.28 is available (note: also as non-Core module outside of hierarchy)
        self.modtool.load(['GCC/6.4.0-2.28'])

        # OpenMPI/2.1.2 is *not* available with current $MODULEPAT
        # (loaded GCC/6.4.0-2.28 was not a hierarchical module)
        if isinstance(self.modtool, Lmod):
            # OpenMPI/2.1.2 exists, but is not available for load;
            # exact error message depends on Lmod version
            load_err_msg = '|'.join([
                r'These[\s\sn]*module\(s\)[\s\sn]*exist[\s\sn]*but[\s\sn]*cannot[\s\sn]*be',
                r'The[\s\sn]*following[\s\sn]*module\(s\)[\s\sn]*are[\s\sn]*unknown',
            ])
        else:
            load_err_msg = "Unable to locate a modulefile"

        self.assertErrorRegex(EasyBuildError, load_err_msg, self.modtool.load, ['OpenMPI/2.1.2'])

    def test_mk_module_cache_key(self):
        """Test mk_module_cache_key method."""
        os.environ['MODULEPATH'] = '%s:/tmp/test' % self.test_prefix
        res = self.modtool.mk_module_cache_key('thisisapartialkey')
        self.assertTrue(isinstance(res, tuple))
        self.assertEqual(res, ('MODULEPATH=%s:/tmp/test' % self.test_prefix, self.modtool.COMMAND, 'thisisapartialkey'))

        del os.environ['MODULEPATH']
        res = self.modtool.mk_module_cache_key('thisisapartialkey')
        self.assertEqual(res, ('MODULEPATH=', self.modtool.COMMAND, 'thisisapartialkey'))

    def test_module_caches(self):
        """Test module caches and invalidate_module_caches_for function."""
        self.assertEqual(mod.MODULE_AVAIL_CACHE, {})

        # purposely extending $MODULEPATH with an empty path, should be handled fine
        nonpath = os.path.join(self.test_prefix, 'nosuchfileordirectory')
        mkdir(nonpath)
        self.modtool.use(nonpath)
        modulepaths = [p for p in os.environ.get('MODULEPATH', '').split(os.pathsep) if p]
        self.assertTrue(any(os.path.samefile(nonpath, mp) for mp in modulepaths))
        shutil.rmtree(nonpath)

        # create symlink to entry in $MODULEPATH we're going to use, and add it to $MODULEPATH
        # invalidate_module_caches_for should be able to deal with this
        test_mods_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules')
        mods_symlink = os.path.join(self.test_prefix, 'modules_symlink')
        os.symlink(test_mods_path, mods_symlink)
        self.modtool.use(mods_symlink)

        # no caching for 'avail' commands with an argument
        self.assertTrue(self.modtool.available('GCC'))
        self.assertEqual(mod.MODULE_AVAIL_CACHE, {})

        # run 'avail' without argument, result should get cached
        res = self.modtool.available()

        # just a single cache entry
        self.assertEqual(len(mod.MODULE_AVAIL_CACHE), 1)

        # fetch cache entry
        avail_cache_key = list(mod.MODULE_AVAIL_CACHE.keys())[0]
        cached_res = mod.MODULE_AVAIL_CACHE[avail_cache_key]
        self.assertTrue(cached_res == res)

        # running avail again results in getting cached result, exactly the same result as before
        # depending on the modules tool being used, it may not be the same list instance, because of post-processing
        self.assertTrue(self.modtool.available() == res)

        # run 'show', should be all cached
        show_res_gcc = self.modtool.show('GCC/6.4.0-2.28')
        show_res_fftw = self.modtool.show('FFTW')
        self.assertEqual(len(mod.MODULE_SHOW_CACHE), 2)
        self.assertTrue(show_res_gcc in mod.MODULE_SHOW_CACHE.values())
        self.assertTrue(show_res_fftw in mod.MODULE_SHOW_CACHE.values())
        self.assertTrue(self.modtool.show('GCC/6.4.0-2.28') is show_res_gcc)
        self.assertTrue(self.modtool.show('FFTW') is show_res_fftw)

        # invalidate caches with correct path
        modulepaths = [p for p in os.environ.get('MODULEPATH', '').split(os.pathsep) if p]
        self.assertTrue(any(os.path.exists(mp) and os.path.samefile(test_mods_path, mp) for mp in modulepaths))
        paths_in_key = [p for p in avail_cache_key[0].split('=')[1].split(os.pathsep) if p]
        self.assertTrue(any(os.path.exists(p) and os.path.samefile(test_mods_path, p) for p in paths_in_key))

        # verify cache invalidation, caches should be empty again
        invalidate_module_caches_for(test_mods_path)
        self.assertEqual(mod.MODULE_AVAIL_CACHE, {})
        self.assertEqual(mod.MODULE_SHOW_CACHE, {})

    def test_module_use_unuse(self):
        """Test 'module use' and 'module unuse'."""
        test_dir1 = os.path.join(self.test_prefix, 'one')
        test_dir2 = os.path.join(self.test_prefix, 'two')
        test_dir3 = os.path.join(self.test_prefix, 'three')

        for subdir in ('one', 'two', 'three'):
            modtxt = '\n'.join([
                '#%Module',
                "setenv TEST123 %s" % subdir,
            ])
            write_file(os.path.join(self.test_prefix, subdir, 'test'), modtxt)

        self.assertFalse(test_dir1 in os.environ.get('MODULEPATH', ''))
        self.modtool.use(test_dir1)
        self.assertTrue(os.environ['MODULEPATH'].startswith('%s:' % test_dir1))
        self.modtool.use(test_dir2)
        self.assertTrue(os.environ['MODULEPATH'].startswith('%s:' % test_dir2))
        self.modtool.use(test_dir3)
        self.assertTrue(os.environ['MODULEPATH'].startswith('%s:' % test_dir3))

        # Adding an empty modulepath is not possible
        modulepath = os.environ.get('MODULEPATH', '')
        self.assertErrorRegex(EasyBuildError, "Cannot add empty path", self.modtool.use, '')
        self.assertEqual(os.environ.get('MODULEPATH', ''), modulepath)

        # make sure the right test module is loaded
        self.modtool.load(['test'])
        self.assertEqual(os.getenv('TEST123'), 'three')
        self.modtool.unload(['test'])

        self.modtool.unuse(test_dir3)
        self.assertFalse(test_dir3 in os.environ.get('MODULEPATH', ''))

        self.modtool.load(['test'])
        self.assertEqual(os.getenv('TEST123'), 'two')
        self.modtool.unload(['test'])

        self.modtool.unuse(test_dir2)
        self.assertFalse(test_dir2 in os.environ.get('MODULEPATH', ''))

        self.modtool.load(['test'])
        self.assertEqual(os.getenv('TEST123'), 'one')
        self.modtool.unload(['test'])

        self.modtool.unuse(test_dir1)
        self.assertFalse(test_dir1 in os.environ.get('MODULEPATH', ''))

        # also test use with high priority
        self.modtool.use(test_dir2, priority=10000)
        self.assertTrue(os.environ['MODULEPATH'].startswith('%s:' % test_dir2))

        self.modtool.load(['test'])
        self.assertEqual(os.getenv('TEST123'), 'two')
        self.modtool.unload(['test'])

        # Tests for Lmod only
        if isinstance(self.modtool, Lmod):
            # check whether prepend with priority actually works (priority is specific to Lmod)
            self.modtool.use(test_dir1, priority=100)
            self.modtool.use(test_dir3)
            self.assertTrue(os.environ['MODULEPATH'].startswith('%s:%s:%s:' % (test_dir2, test_dir1, test_dir3)))
            self.modtool.load(['test'])
            self.assertEqual(os.getenv('TEST123'), 'two')
            self.modtool.unload(['test'])

            self.modtool.unuse(test_dir2)
            self.modtool.load(['test'])
            self.assertEqual(os.getenv('TEST123'), 'one')
            self.modtool.unload(['test'])

            self.modtool.unuse(test_dir1)
            self.modtool.load(['test'])
            self.assertEqual(os.getenv('TEST123'), 'three')
            self.modtool.unload(['test'])

            # Check load and unload for a single path when it is the only one
            # Only for Lmod as we have some shortcuts for avoiding the module call there
            old_module_path = os.environ['MODULEPATH']
            del os.environ['MODULEPATH']
            self.modtool.use(test_dir1)
            self.assertEqual(os.environ['MODULEPATH'], test_dir1)
            self.modtool.unuse(test_dir1)
            self.assertFalse('MODULEPATH' in os.environ)
            os.environ['MODULEPATH'] = old_module_path  # Restore

    def test_add_and_remove_module_path(self):
        """Test add_module_path and whether remove_module_path undoes changes of add_module_path"""
        test_dir1 = tempfile.mkdtemp(suffix="_dir1")
        test_dir2 = tempfile.mkdtemp(suffix="_dir2")
        old_module_path = os.environ.get('MODULEPATH')
        del os.environ['MODULEPATH']
        self.modtool.add_module_path(test_dir1)
        self.assertEqual(os.environ['MODULEPATH'], test_dir1)
        self.modtool.add_module_path(test_dir2)
        test_dir_2_and_1 = os.pathsep.join([test_dir2, test_dir1])
        self.assertEqual(os.environ['MODULEPATH'], test_dir_2_and_1)
        # Adding the same path does not change the path
        self.modtool.add_module_path(test_dir1)
        self.assertEqual(os.environ['MODULEPATH'], test_dir_2_and_1)
        self.modtool.add_module_path(test_dir2)
        self.assertEqual(os.environ['MODULEPATH'], test_dir_2_and_1)
        # Even when a (meaningless) slash is added
        # This occurs when using an empty modules directory name
        self.modtool.add_module_path(os.path.join(test_dir1, ''))
        self.assertEqual(os.environ['MODULEPATH'], test_dir_2_and_1)

        # Similar tests for remove_module_path
        self.modtool.remove_module_path(test_dir2)
        self.assertEqual(os.environ['MODULEPATH'], test_dir1)
        # Same again -> no-op
        self.modtool.remove_module_path(test_dir2)
        self.assertEqual(os.environ['MODULEPATH'], test_dir1)
        # And with empty last part
        self.modtool.remove_module_path(os.path.join(test_dir1, ''))
        self.assertEqual(os.environ.get('MODULEPATH', ''), '')

        # And with some more trickery
        # Lmod seems to remove empty paths: /foo//bar/. -> /foo/bar
        # Environment-Modules 4.x seems to resolve relative paths: /foo/../foo -> /foo
        # Hence we can only check the real paths
        def get_resolved_module_path():
            return os.pathsep.join(os.path.realpath(p) for p in os.environ['MODULEPATH'].split(os.pathsep))

        test_dir1_relative = os.path.join(test_dir1, '..', os.path.basename(test_dir1))
        test_dir2_dot = os.path.join(os.path.dirname(test_dir2), '.', os.path.basename(test_dir2))
        self.modtool.add_module_path(test_dir1_relative)
        self.assertEqual(get_resolved_module_path(), test_dir1)
        # Adding the same path, but in a different form may be possible, but may also be ignored, e.g. in EnvModules
        self.modtool.add_module_path(test_dir1)
        if get_resolved_module_path() != test_dir1:
            self.assertEqual(get_resolved_module_path(), os.pathsep.join([test_dir1, test_dir1]))
            self.modtool.remove_module_path(test_dir1)
            self.assertEqual(get_resolved_module_path(), test_dir1)
        self.modtool.add_module_path(test_dir2_dot)
        self.assertEqual(get_resolved_module_path(), test_dir_2_and_1)
        self.modtool.remove_module_path(test_dir2_dot)
        self.assertEqual(get_resolved_module_path(), test_dir1)
        # Force adding such a dot path which can be removed with either variant
        os.environ['MODULEPATH'] = os.pathsep.join([test_dir2_dot, test_dir1_relative])
        self.modtool.remove_module_path(test_dir2_dot)
        self.assertEqual(get_resolved_module_path(), test_dir1)
        os.environ['MODULEPATH'] = os.pathsep.join([test_dir2_dot, test_dir1_relative])
        self.modtool.remove_module_path(test_dir2)
        self.assertEqual(get_resolved_module_path(), test_dir1)

        os.environ['MODULEPATH'] = old_module_path  # Restore

    def test_module_use_bash(self):
        """Test whether effect of 'module use' is preserved when a new bash session is started."""
        # this test is here as check for a nasty bug in how the modules tool is deployed
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/1756,
        # https://bugzilla.redhat.com/show_bug.cgi?id=1326075
        modules_dir = os.path.abspath(os.path.join(self.test_prefix, 'modules'))
        self.assertFalse(modules_dir in os.environ['MODULEPATH'])

        mkdir(modules_dir, parents=True)
        self.modtool.use(modules_dir)
        modulepath = os.environ['MODULEPATH']
        self.assertTrue(modules_dir in modulepath)

        out, _ = run_cmd("bash -c 'echo MODULEPATH: $MODULEPATH'", simple=False)
        self.assertEqual(out.strip(), "MODULEPATH: %s" % modulepath)
        self.assertTrue(modules_dir in out)

    def test_load_in_hierarchy(self):
        """Test whether loading a module in a module hierarchy results in loading the correct module."""
        self.setup_hierarchical_modules()

        mod_dir = os.path.join(self.test_installpath, 'modules', 'all')
        core_mod_dir = os.path.join(mod_dir, 'Core')

        # create an extra (dummy) hwloc module in Core
        hwloc_mod = os.path.join(core_mod_dir, 'hwloc', '1.11.8')
        write_file(hwloc_mod, "#%Module\nsetenv EBROOTHWLOC /path/to/dummy/hwloc")

        # set up $MODULEPATH to point to top of hierarchy
        self.modtool.use(core_mod_dir)

        self.assertEqual(os.environ.get('EBROOTHWLOC'), None)

        # check whether dummy hwloc is loaded
        self.modtool.load(['hwloc/1.11.8'])
        self.assertEqual(os.environ['EBROOTHWLOC'], '/path/to/dummy/hwloc')

        # make sure that compiler-dependent hwloc test module exists
        gcc_mod_dir = os.path.join(mod_dir, 'Compiler', 'GCC', '6.4.0-2.28')
        self.assertTrue(os.path.exists(os.path.join(gcc_mod_dir, 'hwloc', '1.11.8')))

        # test loading of compiler-dependent hwloc test module
        self.modtool.purge()
        self.modtool.use(gcc_mod_dir)
        self.modtool.load(['hwloc/1.11.8'])
        self.assertEqual(os.environ['EBROOTHWLOC'], '/tmp/software/Compiler/GCC/6.4.0-2.28/hwloc/1.11.8')

        # ensure that correct module is loaded when hierarchy is defined by loading the GCC module
        # (side-effect is that ModulesTool instance doesn't track the change being made to $MODULEPATH)
        # verifies bug fixed in https://github.com/easybuilders/easybuild-framework/pull/1795
        self.modtool.purge()
        self.modtool.unuse(gcc_mod_dir)
        self.modtool.load(['GCC/6.4.0-2.28'])
        self.assertEqual(os.environ['EBROOTGCC'], '/tmp/software/Core/GCC/6.4.0-2.28')
        self.modtool.load(['hwloc/1.11.8'])
        self.assertEqual(os.environ['EBROOTHWLOC'], '/tmp/software/Compiler/GCC/6.4.0-2.28/hwloc/1.11.8')

        # also test whether correct temporary module is loaded even though same module file already exists elsewhere
        # with Lmod, this requires prepending the temporary module path to $MODULEPATH with high priority
        tmp_moddir = os.path.join(self.test_prefix, 'tmp_modules')
        hwloc_mod = os.path.join(tmp_moddir, 'hwloc', '1.11.8')
        hwloc_mod_txt = '\n'.join([
            '#%Module',
            "module load GCC/6.4.0-2.28",
            "setenv EBROOTHWLOC /path/to/tmp/hwloc-1.11.8",
        ])
        write_file(hwloc_mod, hwloc_mod_txt)
        self.modtool.purge()
        self.modtool.use(tmp_moddir, priority=10000)
        self.modtool.load(['hwloc/1.11.8'])
        self.assertTrue(os.environ['EBROOTHWLOC'], "/path/to/tmp/hwloc-1.11.8")

    def test_exit_code_check(self):
        """Verify that EasyBuild checks exit code of executed module commands"""
        if isinstance(self.modtool, Lmod):
            error_pattern = "Module command '.*load nosuchmoduleavailableanywhere' failed with exit code"
        else:
            # Tcl implementations exit with 0 even when a non-existing module is loaded...
            error_pattern = "Unable to locate a modulefile for 'nosuchmoduleavailableanywhere'"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.modtool.load, ['nosuchmoduleavailableanywhere'])

    def test_check_loaded_modules(self):
        """Test check_loaded_modules method."""
        # try and make sure we start with a clean slate
        self.modtool.purge()

        def check_loaded_modules():
            "Helper function to run check_loaded_modules and check on stdout/stderr."
            # there should be no errors/warnings by default if no (EasyBuild-generated) modules are loaded
            self.mock_stdout(True)
            self.mock_stderr(True)
            self.modtool.check_loaded_modules()
            stdout, stderr = self.get_stdout(), self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(stdout, '')
            return stderr.strip()

        # by default, having an EasyBuild module loaded is allowed
        self.modtool.load(['EasyBuild/fake'])

        # no output to stderr (no warnings/errors)
        self.assertEqual(check_loaded_modules(), '')

        self.modtool.unload(['EasyBuild/fake'])

        # load OpenMPI module, which also loads GCC & hwloc
        self.modtool.load(['OpenMPI/2.1.2-GCC-6.4.0-2.28'])

        # default action is to print a clear warning message
        stderr = check_loaded_modules()
        patterns = [
            r"^WARNING: Found one or more non-allowed loaded \(EasyBuild-generated\) modules in current environment:",
            r"^\* GCC/6.4.0-2.28",
            r"^\* hwloc/1.11.8-GCC-6.4.0-2.28",
            r"^\* OpenMPI/2.1.2-GCC-6.4.0-2.28",
            r"This is not recommended since it may affect the installation procedure\(s\) performed by EasyBuild.",
            "To make EasyBuild allow particular loaded modules, use the --allow-loaded-modules configuration option.",
            "To specify action to take when loaded modules are detected, use "
            "--detect-loaded-modules={error,ignore,purge,unload,warn}",
        ]
        for pattern in patterns:
            self.assertTrue(re.search(pattern, stderr, re.M), "Pattern '%s' found in: %s" % (pattern, stderr))

        # reconfigure EasyBuild to ignore loaded modules for GCC & hwloc & error out when loaded modules are detected
        options = init_config(args=['--allow-loaded-modules=GCC,hwloc', '--detect-loaded-modules=error'])
        build_options = {
            'allow_loaded_modules': options.allow_loaded_modules,
            'detect_loaded_modules': options.detect_loaded_modules,
        }
        init_config(build_options=build_options)

        # error mentioning 1 non-allowed module (OpenMPI), both GCC and hwloc loaded modules are allowed
        error_pattern = r"Found one or more non-allowed loaded .* module.*\n"
        error_pattern += r"\* OpenMPI/2.1.2-GCC-6.4.0-2.28\n\nThis is not"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.modtool.check_loaded_modules)

        # check for warning message when purge is being run on loaded modules
        build_options.update({'detect_loaded_modules': 'purge'})
        init_config(build_options=build_options)
        expected = "WARNING: Found non-allowed loaded (EasyBuild-generated) modules (OpenMPI/2.1.2-GCC-6.4.0-2.28), "
        expected += "running 'module purge'"
        self.assertEqual(check_loaded_modules(), expected)

        # check for warning message when loaded modules are unloaded
        self.modtool.load(['OpenMPI/2.1.2-GCC-6.4.0-2.28'])
        build_options.update({'detect_loaded_modules': 'unload'})
        init_config(build_options=build_options)
        expected = "WARNING: Unloading non-allowed loaded (EasyBuild-generated) modules: OpenMPI/2.1.2-GCC-6.4.0-2.28"
        self.assertEqual(check_loaded_modules(), expected)

        # when loaded modules are allowed there are no warnings/errors
        self.modtool.load(['OpenMPI/2.1.2-GCC-6.4.0-2.28'])
        build_options.update({'detect_loaded_modules': 'ignore'})
        init_config(build_options=build_options)
        self.assertEqual(check_loaded_modules(), '')

        # error if any $EBROOT* environment variables are defined that don't match a loaded module
        os.environ['EBROOTSOFTWAREWITHOUTAMATCHINGMODULE'] = '/path/to/software/without/a/matching/module'
        stderr = check_loaded_modules()
        warning_msg = "WARNING: Found defined $EBROOT* environment variables without matching loaded module: "
        warning_msg = "$EBROOTSOFTWAREWITHOUTAMATCHINGMODULE\n"
        self.assertTrue(warning_msg in stderr)

        build_options.update({'check_ebroot_env_vars': 'error'})
        init_config(build_options=build_options)
        error_msg = r"Found defined \$EBROOT\* environment variables without matching loaded module: "
        error_msg += r"\$EBROOTSOFTWAREWITHOUTAMATCHINGMODULE\n"
        self.assertErrorRegex(EasyBuildError, error_msg, check_loaded_modules)

        build_options.update({'check_ebroot_env_vars': 'ignore'})
        init_config(build_options=build_options)
        stderr = check_loaded_modules()
        self.assertEqual(stderr, '')

        build_options.update({'check_ebroot_env_vars': 'unset'})
        init_config(build_options=build_options)
        stderr = check_loaded_modules()
        warning_msg = "WARNING: Found defined $EBROOT* environment variables without matching loaded module: "
        warning_msg += "$EBROOTSOFTWAREWITHOUTAMATCHINGMODULE; unsetting them"
        self.assertEqual(stderr, warning_msg)
        self.assertTrue(os.environ.get('EBROOTSOFTWAREWITHOUTAMATCHINGMODULE') is None)

        # specified action for detected loaded modules is verified early
        error_msg = "Unknown action specified to --detect-loaded-modules: sdvbfdgh"
        self.assertErrorRegex(EasyBuildError, error_msg, init_config, args=['--detect-loaded-modules=sdvbfdgh'])

    def test_NoModulesTool(self):
        """Test use of NoModulesTool class."""
        nmt = NoModulesTool(testing=True)
        self.assertEqual(len(nmt.available()), 0)
        self.assertEqual(len(nmt.available(mod_names='foo')), 0)
        self.assertEqual(len(nmt.list()), 0)
        self.assertEqual(nmt.exist(['foo', 'bar']), [False, False])
        self.assertEqual(nmt.exist(['foo', 'bar'], r'^\s*\S*/%s.*:\s*$', skip_avail=False), [False, False])

    def test_modulecmd_strip_source(self):
        """Test stripping of 'source' command in output of 'modulecmd python load'."""

        init_config(build_options={'allow_modules_tool_mismatch': True})

        # install dummy modulecmd command that always produces a 'source command' in its output
        modulecmd = os.path.join(self.test_prefix, 'modulecmd')
        modulecmd_txt = '\n'.join([
            '#!/bin/bash',
            # if last argument (${!#})) is --version, print version
            'if [ x"${!#}" == "x--version" ]; then',
            '  echo 3.2.10',
            # otherwise, echo Python commands: set $TEST123 and include a faulty 'source' command
            'else',
            '  echo "source /opt/cray/pe/modules/3.2.10.6/init/bash"',
            "  echo \"os.environ['TEST123'] = 'test123'\"",
            'fi',
        ])
        write_file(modulecmd, modulecmd_txt)
        adjust_permissions(modulecmd, stat.S_IXUSR, add=True)

        os.environ['PATH'] = '%s:%s' % (self.test_prefix, os.getenv('PATH'))

        modtool = EnvironmentModulesC()
        modtool.run_module('load', 'test123')
        self.assertEqual(os.getenv('TEST123'), 'test123')

    def test_get_setenv_value_from_modulefile(self):
        """Test for ModulesTool.get_setenv_value_from_modulefile method."""

        init_config(build_options={'generate_devel_module': True})

        topdir = os.path.dirname(os.path.abspath(__file__))
        eb_path = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, read_file(eb_path))
        write_file(test_ec, "\nmodextravars = {'FOO': 'value with spaces'}", append=True)

        toy_eb = EasyBlock(EasyConfig(test_ec))
        toy_eb.make_module_step()

        expected_root = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
        ebroot = self.modtool.get_setenv_value_from_modulefile('toy/0.0', 'EBROOTTOY')
        self.assertTrue(os.path.samefile(ebroot, expected_root))

        ebversion = self.modtool.get_setenv_value_from_modulefile('toy/0.0', 'EBVERSIONTOY')
        self.assertEqual(ebversion, '0.0')

        foo = self.modtool.get_setenv_value_from_modulefile('toy/0.0', 'FOO')
        self.assertEqual(foo, "value with spaces")

        res = self.modtool.get_setenv_value_from_modulefile('toy/0.0', 'NO_SUCH_VARIABLE_SET')
        self.assertEqual(res, None)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ModulesTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
