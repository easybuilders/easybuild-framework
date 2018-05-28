##
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
import sys
from distutils.version import StrictVersion
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.modules as mod
from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import copy_file, copy_dir, mkdir, read_file, write_file
from easybuild.tools.modules import EnvironmentModules, EnvironmentModulesTcl, Lmod, NoModulesTool
from easybuild.tools.modules import curr_module_paths, get_software_libdir, get_software_root, get_software_version
from easybuild.tools.modules import invalidate_module_caches_for, modules_tool, reset_module_caches
from easybuild.tools.run import run_cmd


# number of modules included for testing purposes
TEST_MODULES_COUNT = 79


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

    def test_avail(self):
        """Test if getting a (restricted) list of available modules works."""
        self.init_testmods()

        # test modules include 3 GCC modules and one GCCcore module
        ms = self.modtool.available('GCC')
        expected = ['GCC/4.6.3', 'GCC/4.6.4', 'GCC/4.7.2']
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
            self.assertTrue('OpenMPI/.1.6.4-GCC-4.6.4' in ms)
        else:
            self.assertEqual(len(ms), TEST_MODULES_COUNT)

    def test_exists(self):
        """Test if testing for module existence works."""
        self.init_testmods()
        self.assertEqual(self.modtool.exist(['OpenMPI/1.6.4-GCC-4.6.4']), [True])
        self.assertEqual(self.modtool.exist(['OpenMPI/1.6.4-GCC-4.6.4'], skip_avail=True), [True])
        self.assertEqual(self.modtool.exist(['foo/1.2.3']), [False])
        self.assertEqual(self.modtool.exist(['foo/1.2.3'], skip_avail=True), [False])

        # exists works on hidden modules
        self.assertEqual(self.modtool.exist(['toy/.0.0-deps']), [True])
        self.assertEqual(self.modtool.exist(['toy/.0.0-deps'], skip_avail=True), [True])

        # also partial module names work
        self.assertEqual(self.modtool.exist(['OpenMPI']), [True])
        self.assertEqual(self.modtool.exist(['OpenMPI'], skip_avail=True), [True])
        # but this doesn't...
        self.assertEqual(self.modtool.exist(['OpenMPI/1.6.4']), [False])
        self.assertEqual(self.modtool.exist(['OpenMPI/1.6.4'], skip_avail=True), [False])

        # exists works on hidden modules in Lua syntax (only with Lmod)
        if isinstance(self.modtool, Lmod):
            test_modules_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))
            # make sure only the .lua module file is there, otherwise this test doesn't work as intended
            self.assertTrue(os.path.exists(os.path.join(test_modules_path, 'bzip2', '.1.0.6.lua')))
            self.assertFalse(os.path.exists(os.path.join(test_modules_path, 'bzip2', '.1.0.6')))
            self.assertEqual(self.modtool.exist(['bzip2/.1.0.6']), [True])

        # exists also works on lists of module names
        # list should be sufficiently long, since for short lists 'show' is always used
        mod_names = ['OpenMPI/1.6.4-GCC-4.6.4', 'foo/1.2.3', 'GCC',
                     'ScaLAPACK/1.8.0-gompi-1.1.0-no-OFED',
                     'ScaLAPACK/1.8.0-gompi-1.1.0-no-OFED-ATLAS-3.8.4-LAPACK-3.4.0-BLACS-1.1',
                     'Compiler/GCC/4.7.2/OpenMPI/1.6.4', 'toy/.0.0-deps']
        self.assertEqual(self.modtool.exist(mod_names), [True, False, True, False, True, True, True])
        self.assertEqual(self.modtool.exist(mod_names, skip_avail=True), [True, False, True, False, True, True, True])

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
        mods = [
            # module use on non-existent dir (Tcl-based env mods), or missing dep (Lmod)
            'Compiler/GCC/4.7.2/OpenMPI/1.6.4',
            # missing dep
            'MPI/GCC/4.7.2/OpenMPI/1.6.4/ScaLAPACK/2.0.2-OpenBLAS-0.2.6-LAPACK-3.4.2',
        ]
        for mod in mods:
            self.assertErrorRegex(EasyBuildError, '.*', self.modtool.load, [mod])

        # by default, modules are always loaded, even if they are already loaded
        self.modtool.load(['GCC/4.6.4', 'OpenMPI/1.6.4-GCC-4.6.4'])

        # unset $EBROOTGCC, it should get set again later by loading GCC again
        del os.environ['EBROOTGCC']

        # GCC should be loaded, but should not be listed last (OpenMPI was loaded last)
        loaded_modules = self.modtool.loaded_modules()
        self.assertTrue('GCC/4.6.4' in loaded_modules)
        self.assertFalse(loaded_modules[-1] == 'GCC/4.6.4')

        # if GCC is loaded again, $EBROOTGCC should be set again, and GCC should be listed last
        self.modtool.load(['GCC/4.6.4'])

        # environment modules v4.0 does not reload already loaded modules, will be changed in v4.2
        modtool_ver = StrictVersion(self.modtool.version)
        if not isinstance(self.modtool, EnvironmentModules) or modtool_ver >= StrictVersion('4.2'):
            self.assertTrue(os.environ.get('EBROOTGCC'))

        if isinstance(self.modtool, Lmod):
            # order of loaded modules only changes with Lmod
            self.assertTrue(self.modtool.loaded_modules()[-1] == 'GCC/4.6.4')

        # set things up for checking that GCC does *not* get reloaded when requested
        if 'EBROOTGCC' in os.environ:
            del os.environ['EBROOTGCC']
        self.modtool.load(['OpenMPI/1.6.4-GCC-4.6.4'])
        if isinstance(self.modtool, Lmod):
            # order of loaded modules only changes with Lmod
            self.assertTrue(self.modtool.loaded_modules()[-1] == 'OpenMPI/1.6.4-GCC-4.6.4')

        # reloading can be disabled using allow_reload=False
        self.modtool.load(['GCC/4.6.4'], allow_reload=False)
        self.assertEqual(os.environ.get('EBROOTGCC'), None)
        self.assertFalse(loaded_modules[-1] == 'GCC/4.6.4')

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
            os.makedirs(os.path.join(root, 'lib'))
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
        os.makedirs(os.path.join(root, 'lib64'))
        os.environ['EBROOT%s' % env_var_name] = root
        self.assertErrorRegex(EasyBuildError, "Multiple library subdirectories found.*", get_software_libdir, name)
        self.assertEqual(get_software_libdir(name, only_one=False), ['lib', 'lib64'])

        # only directories containing files in specified list should be retained
        open(os.path.join(root, 'lib64', 'foo'), 'w').write('foo')
        self.assertEqual(get_software_libdir(name, fs=['foo']), 'lib64')

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
        gcc_mod_file = os.path.join(test_dir, 'modules', 'GCC', '4.7.2')

        modtool = modules_tool()
        res  = modtool.modulefile_path('GCC/4.7.2')
        self.assertTrue(os.path.samefile(res, gcc_mod_file))

        if isinstance(self.modtool, Lmod):
            res  = modtool.modulefile_path('bzip2/.1.0.6')
            self.assertTrue(os.path.samefile(res, os.path.join(test_dir, 'modules', 'bzip2', '.1.0.6.lua')))
            res  = modtool.modulefile_path('bzip2/.1.0.6', strip_ext=True)
            self.assertTrue(res.endswith('test/framework/modules/bzip2/.1.0.6'))

        # hack into 'module show GCC/4.7.2' cache and inject alternate output that modulecmd.tcl sometimes produces
        # make sure we only extract the module file path, nothing else...
        # cfr. https://github.com/easybuilders/easybuild/issues/368
        modulepath = os.environ['MODULEPATH'].split(':')
        mod_show_cache_key = modtool.mk_module_cache_key('GCC/4.7.2')
        mod.MODULE_SHOW_CACHE[mod_show_cache_key] = '\n'.join([
            "import os",
            "os.environ['MODULEPATH_modshare'] = '%s'" % ':'.join(m + ':1' for m in modulepath),
            "os.environ['MODULEPATH'] = '%s'" % ':'.join(modulepath),
            "------------------------------------------------------------------------------",
            "%s:" % gcc_mod_file,
            "------------------------------------------------------------------------------",
            # remainder of output doesn't really matter in this context
            "setenv		EBROOTGCC /prefix/GCC/4.7.2"
        ])
        res  = modtool.modulefile_path('GCC/4.7.2')
        self.assertTrue(os.path.samefile(res, os.path.join(test_dir, 'modules', 'GCC', '4.7.2')))

        reset_module_caches()

    def test_path_to_top_of_module_tree(self):
        """Test function to determine path to top of the module tree."""

        path = self.modtool.path_to_top_of_module_tree([], 'gompi/1.3.12', '', ['GCC/4.6.4', 'OpenMPI/1.6.4-GCC-4.6.4'])
        self.assertEqual(path, [])
        path = self.modtool.path_to_top_of_module_tree([], 'toy/.0.0-deps', '', ['gompi/1.3.12'])
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
        init_modpaths = [os.path.join(mod_prefix, 'Core')]

        deps = ['GCC/4.7.2', 'OpenMPI/1.6.4', 'FFTW/3.3.3', 'OpenBLAS/0.2.6-LAPACK-3.4.2',
                'ScaLAPACK/2.0.2-OpenBLAS-0.2.6-LAPACK-3.4.2']
        core = os.path.join(mod_prefix, 'Core')
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'goolf/1.4.10', core, deps)
        self.assertEqual(path, [])
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'GCC/4.7.2', core, [])
        self.assertEqual(path, [])
        full_mod_subdir = os.path.join(mod_prefix, 'Compiler', 'GCC', '4.7.2')
        deps = ['GCC/4.7.2', 'hwloc/1.6.2']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'OpenMPI/1.6.4', full_mod_subdir, deps)
        self.assertEqual(path, ['GCC/4.7.2'])
        full_mod_subdir = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4')
        deps = ['GCC/4.7.2', 'OpenMPI/1.6.4']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'FFTW/3.3.3', full_mod_subdir, deps)
        self.assertEqual(path, ['OpenMPI/1.6.4', 'GCC/4.7.2'])

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
            print "Skipping test_path_to_top_of_module_tree_lua, required Lmod as modules tool"

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
            'GCC/4.7.2': [os.path.join(mod_dir, 'Compiler', 'GCC', '4.7.2')],
            'OpenMPI/1.6.4': [os.path.join(mod_dir, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4')],
            'FFTW/3.3.3': [],
        }
        res = self.modtool.modpath_extensions_for(['GCC/4.7.2', 'OpenMPI/1.6.4', 'FFTW/3.3.3'])
        self.assertEqual(res, expected)

        expected = {
            'icc/2013.5.192-GCC-4.8.3': [os.path.join(mod_dir, 'Compiler', 'intel', '2013.5.192-GCC-4.8.3')],
            'ifort/2013.5.192-GCC-4.8.3': [os.path.join(mod_dir, 'Compiler', 'intel', '2013.5.192-GCC-4.8.3')],
        }
        res = self.modtool.modpath_extensions_for(['icc/2013.5.192-GCC-4.8.3', 'ifort/2013.5.192-GCC-4.8.3'])
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
            "    module use %s/Compiler/intel/2013.5.192-GCC-4.8.3" % mod_dir,  # indented without guard
            # quoted path
            'module use "%s/Compiler/GCC/4.7.2"' % mod_dir,
            # using prepend-path & quoted
            ' prepend-path MODULEPATH [ file join %s "MPI/GCC/4.7.2/OpenMPI/1.6.4" ]' % mod_dir,
            # conditional 'use' on subdirectory in $HOME, e.g. when --subdir-user-modules is used
            "if { [ file isdirectory $env(HOME)/modules/Compiler/GCC/4.7.2 ] } {",
            '    module use [ file join $env(HOME) "modules/Compiler/GCC/4.7.2" ]',
            "}",
            "setenv EXAMPLE example",
            # more (fictional) extensions that use os.getenv
            'prepend-path   MODULEPATH    "$env(HOME)"',
            'module use  "%s/$env(USER)/test"' % self.test_prefix,
        ])
        write_file(test_modfile, test_modtxt)

        expected = {
            test_mod: [
                os.path.join(mod_dir, 'Compiler', 'intel', '2013.5.192-GCC-4.8.3'),
                os.path.join(mod_dir, 'Compiler', 'GCC', '4.7.2'),
                os.path.join(mod_dir, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4'),
                os.path.join(os.environ['HOME'], 'modules', 'Compiler', 'GCC', '4.7.2'),
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
                '   prepend_path("MODULEPATH", "%s/Compiler/intel/2013.5.192-GCC-4.8.3")' % mod_dir,
                'prepend_path("MODULEPATH","%s/Compiler/GCC/4.7.2")' % mod_dir,
                'prepend_path("MODULEPATH", "%s/MPI/GCC/4.7.2/OpenMPI/1.6.4")' % mod_dir,
                # conditional 'use' on subdirectory in $HOME, e.g. when --subdir-user-modules is used
                'if isDir(pathJoin(os.getenv("HOME"), "modules/Compiler/GCC/4.7.2")) then',
                '    prepend_path("MODULEPATH", pathJoin(os.getenv("HOME"), "modules/Compiler/GCC/4.7.2"))',
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

        deps = ['GCC/4.7.2', 'OpenMPI/1.6.4', 'FFTW/3.3.3', 'OpenBLAS/0.2.6-LAPACK-3.4.2',
                'ScaLAPACK/2.0.2-OpenBLAS-0.2.6-LAPACK-3.4.2']
        core = os.path.join(mod_prefix, 'Core')
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'goolf/1.4.10', os.path.join(core, 'toolchain'), deps)
        self.assertEqual(path, [])
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'GCC/4.7.2', os.path.join(core, 'compiler'), [])
        self.assertEqual(path, [])
        full_mod_subdir = os.path.join(mod_prefix, 'Compiler', 'GCC', '4.7.2', 'mpi')
        deps = ['GCC/4.7.2', 'hwloc/1.6.2']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'OpenMPI/1.6.4', full_mod_subdir, deps)
        self.assertEqual(path, ['GCC/4.7.2'])
        full_mod_subdir = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4', 'numlib')
        deps = ['GCC/4.7.2', 'OpenMPI/1.6.4']
        path = self.modtool.path_to_top_of_module_tree(init_modpaths, 'FFTW/3.3.3', full_mod_subdir, deps)
        self.assertEqual(path, ['OpenMPI/1.6.4', 'GCC/4.7.2'])

    def test_modules_tool_stateless(self):
        """Check whether ModulesTool instance is stateless between runs."""
        test_modules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules')

        # copy test Core/Compiler modules, we need to rewrite the 'module use' statement in the one we're going to load
        copy_dir(os.path.join(test_modules_path, 'Core'), os.path.join(self.test_prefix, 'Core'))
        copy_dir(os.path.join(test_modules_path, 'Compiler'), os.path.join(self.test_prefix, 'Compiler'))

        modtxt = read_file(os.path.join(self.test_prefix, 'Core', 'GCC', '4.7.2'))
        modpath_extension = os.path.join(self.test_prefix, 'Compiler', 'GCC', '4.7.2')
        modtxt = re.sub('module use .*', 'module use %s' % modpath_extension, modtxt, re.M)
        write_file(os.path.join(self.test_prefix, 'Core', 'GCC', '4.7.2'), modtxt)

        modtxt = read_file(os.path.join(self.test_prefix, 'Compiler', 'GCC', '4.7.2', 'OpenMPI', '1.6.4'))
        modpath_extension = os.path.join(self.test_prefix, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4')
        mkdir(modpath_extension, parents=True)
        modtxt = re.sub('module use .*', 'module use %s' % modpath_extension, modtxt, re.M)
        write_file(os.path.join(self.test_prefix, 'Compiler', 'GCC', '4.7.2', 'OpenMPI', '1.6.4'), modtxt)

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
        self.assertErrorRegex(EasyBuildError, load_err_msg, self.modtool.load, ['GCC/4.6.3'])

        # GCC/4.7.2 is one of the available Core modules
        self.modtool.load(['GCC/4.7.2'])

        # OpenMPI/1.6.4 becomes available after loading GCC/4.7.2 module
        self.modtool.load(['OpenMPI/1.6.4'])
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

        # GCC/4.7.2 is available (note: also as non-Core module outside of hierarchy)
        self.modtool.load(['GCC/4.7.2'])

        # OpenMPI/1.6.4 is *not* available with current $MODULEPATH (loaded GCC/4.7.2 was not a hierarchical module)
        if isinstance(self.modtool, Lmod):
            # OpenMPI/1.6.4 exists, but is not available for load;
            # exact error message depends on Lmod version
            load_err_msg = '|'.join([
                r'These[\s\sn]*module\(s\)[\s\sn]*exist[\s\sn]*but[\s\sn]*cannot[\s\sn]*be',
                'The[\s\sn]*following[\s\sn]*module\(s\)[\s\sn]*are[\s\sn]*unknown',
            ])
        else:
            load_err_msg = "Unable to locate a modulefile"

        self.assertErrorRegex(EasyBuildError, load_err_msg, self.modtool.load, ['OpenMPI/1.6.4'])

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

        # purposely extending $MODULEPATH with non-existing path, should be handled fine
        nonpath = os.path.join(self.test_prefix, 'nosuchfileordirectory')
        self.modtool.use(nonpath)
        modulepaths = [p for p in os.environ.get('MODULEPATH', '').split(os.pathsep) if p]
        self.assertTrue(any([os.path.samefile(nonpath, mp) for mp in modulepaths]))
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
        avail_cache_key = mod.MODULE_AVAIL_CACHE.keys()[0]
        cached_res = mod.MODULE_AVAIL_CACHE[avail_cache_key]
        self.assertTrue(cached_res == res)

        # running avail again results in getting cached result, exactly the same result as before
        # depending on the modules tool being used, it may not be the same list instance, because of post-processing
        self.assertTrue(self.modtool.available() == res)

        # run 'show', should be all cached
        show_res_gcc = self.modtool.show('GCC/4.7.2')
        show_res_fftw = self.modtool.show('FFTW')
        self.assertEqual(len(mod.MODULE_SHOW_CACHE), 2)
        self.assertTrue(show_res_gcc in mod.MODULE_SHOW_CACHE.values())
        self.assertTrue(show_res_fftw in mod.MODULE_SHOW_CACHE.values())
        self.assertTrue(self.modtool.show('GCC/4.7.2') is show_res_gcc)
        self.assertTrue(self.modtool.show('FFTW') is show_res_fftw)

        # invalidate caches with correct path
        modulepaths = [p for p in os.environ.get('MODULEPATH', '').split(os.pathsep) if p]
        self.assertTrue(any([os.path.exists(mp) and os.path.samefile(test_mods_path, mp) for mp in modulepaths]))
        paths_in_key = [p for p in avail_cache_key[0].split('=')[1].split(os.pathsep) if p]
        self.assertTrue(any([os.path.exists(p) and os.path.samefile(test_mods_path, p) for p in paths_in_key]))

        # verify cache invalidation, caches should be empty again
        invalidate_module_caches_for(test_mods_path)
        self.assertEqual(mod.MODULE_AVAIL_CACHE, {})
        self.assertEqual(mod.MODULE_SHOW_CACHE, {})

    def test_module_use(self):
        """Test 'module use'."""
        test_dir1 = os.path.join(self.test_prefix, 'one')
        test_dir2 = os.path.join(self.test_prefix, 'two')
        test_dir3 = os.path.join(self.test_prefix, 'three')

        self.assertFalse(test_dir1 in os.environ.get('MODULEPATH', ''))
        self.modtool.use(test_dir1)
        self.assertTrue(os.environ.get('MODULEPATH', '').startswith('%s:' % test_dir1))

        # also test use with high priority
        self.modtool.use(test_dir2, priority=10000)
        self.assertTrue(os.environ['MODULEPATH'].startswith('%s:' % test_dir2))

        # check whether prepend with priority actually works (only for Lmod)
        if isinstance(self.modtool, Lmod):
            self.modtool.use(test_dir3)
            self.assertTrue(os.environ['MODULEPATH'].startswith('%s:%s:' % (test_dir2, test_dir3)))

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
        hwloc_mod = os.path.join(core_mod_dir, 'hwloc', '1.6.2')
        write_file(hwloc_mod, "#%Module\nsetenv EBROOTHWLOC /path/to/dummy/hwloc")

        # set up $MODULEPATH to point to top of hierarchy
        self.modtool.use(core_mod_dir)

        self.assertEqual(os.environ.get('EBROOTHWLOC'), None)

        # check whether dummy hwloc is loaded
        self.modtool.load(['hwloc/1.6.2'])
        self.assertEqual(os.environ['EBROOTHWLOC'], '/path/to/dummy/hwloc')

        # make sure that compiler-dependent hwloc test module exists
        gcc_mod_dir = os.path.join(mod_dir, 'Compiler', 'GCC', '4.7.2')
        self.assertTrue(os.path.exists(os.path.join(gcc_mod_dir, 'hwloc', '1.6.2')))

        # test loading of compiler-dependent hwloc test module
        self.modtool.purge()
        self.modtool.use(gcc_mod_dir)
        self.modtool.load(['hwloc/1.6.2'])
        self.assertEqual(os.environ['EBROOTHWLOC'], '/tmp/software/Compiler/GCC/4.7.2/hwloc/1.6.2')

        # ensure that correct module is loaded when hierarchy is defined by loading the GCC module
        # (side-effect is that ModulesTool instance doesn't track the change being made to $MODULEPATH)
        # verifies bug fixed in https://github.com/easybuilders/easybuild-framework/pull/1795
        self.modtool.purge()
        self.modtool.unuse(gcc_mod_dir)
        self.modtool.load(['GCC/4.7.2'])
        self.assertEqual(os.environ['EBROOTGCC'], '/tmp/software/Core/GCC/4.7.2')
        self.modtool.load(['hwloc/1.6.2'])
        self.assertEqual(os.environ['EBROOTHWLOC'], '/tmp/software/Compiler/GCC/4.7.2/hwloc/1.6.2')

        # also test whether correct temporary module is loaded even though same module file already exists elsewhere
        # with Lmod, this requires prepending the temporary module path to $MODULEPATH with high priority
        tmp_moddir = os.path.join(self.test_prefix, 'tmp_modules')
        hwloc_mod = os.path.join(tmp_moddir, 'hwloc', '1.6.2')
        hwloc_mod_txt = '\n'.join([
            '#%Module',
            "module load GCC/4.7.2",
            "setenv EBROOTHWLOC /path/to/tmp/hwloc-1.6.2",
        ])
        write_file(hwloc_mod, hwloc_mod_txt)
        self.modtool.purge()
        self.modtool.use(tmp_moddir, priority=10000)
        self.modtool.load(['hwloc/1.6.2'])
        self.assertTrue(os.environ['EBROOTHWLOC'], "/path/to/tmp/hwloc-1.6.2")

    def test_exit_code_check(self):
        """Verify that EasyBuild checks exit code of executed module commands"""
        if isinstance(self.modtool, Lmod):
            error_pattern = "Module command 'module load nosuchmoduleavailableanywhere' failed with exit code"
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
        self.modtool.load(['OpenMPI/1.6.4-GCC-4.6.4'])

        # default action is to print a clear warning message
        stderr = check_loaded_modules()
        patterns = [
            r"^WARNING: Found one or more non-allowed loaded \(EasyBuild-generated\) modules in current environment:",
            r"^\* GCC/4.6.4",
            r"^\* hwloc/1.6.2-GCC-4.6.4",
            r"^\* OpenMPI/1.6.4-GCC-4.6.4",
            "This is not recommended since it may affect the installation procedure\(s\) performed by EasyBuild.",
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
        error_pattern = r"Found one or more non-allowed loaded .* module.*\n\* OpenMPI/1.6.4-GCC-4.6.4\n\nThis is not"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.modtool.check_loaded_modules)

        # check for warning message when purge is being run on loaded modules
        build_options.update({'detect_loaded_modules': 'purge'})
        init_config(build_options=build_options)
        expected = "WARNING: Found non-allowed loaded (EasyBuild-generated) modules (OpenMPI/1.6.4-GCC-4.6.4), "
        expected += "running 'module purge'"
        self.assertEqual(check_loaded_modules(), expected)

        # check for warning message when loaded modules are unloaded
        self.modtool.load(['OpenMPI/1.6.4-GCC-4.6.4'])
        build_options.update({'detect_loaded_modules': 'unload'})
        init_config(build_options=build_options)
        expected = "WARNING: Unloading non-allowed loaded (EasyBuild-generated) modules: OpenMPI/1.6.4-GCC-4.6.4"
        self.assertEqual(check_loaded_modules(), expected)

        # when loaded modules are allowed there are no warnings/errors
        self.modtool.load(['OpenMPI/1.6.4-GCC-4.6.4'])
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
            nmt = NoModulesTool(testing=true)
            assertEqual(len(nmt.available()), 0)
            assertEqual(len(nmt.available(mod_names='foo')), 0)
            assertEqual(len(nmt.list()), 0)
            assertEqual(nmt.exist(['foo', 'bar']), [False, False])
            assertEqual(nmt.exist(['foo', 'bar'], r'^\s*\S*/%s.*:\s*$', skip_avail=False), [False, False])

def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ModulesTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
