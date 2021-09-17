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
Unit tests for module_generator.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion
from unittest import TextTestRunner, TestSuite

from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.tools import config
from easybuild.tools.filetools import mkdir, read_file, remove_file, write_file
from easybuild.tools.module_generator import ModuleGeneratorLua, ModuleGeneratorTcl, dependencies_for
from easybuild.tools.module_naming_scheme.utilities import is_valid_module_name
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ActiveMNS
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.modules import EnvironmentModulesC, EnvironmentModulesTcl, Lmod
from easybuild.tools.utilities import quote_str
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, find_full_path, init_config


class ModuleGeneratorTest(EnhancedTestCase):
    """Tests for module_generator module."""

    MODULE_GENERATOR_CLASS = None

    def setUp(self):
        """Test setup."""
        super(ModuleGeneratorTest, self).setUp()
        # find .eb file
        topdir = os.path.dirname(os.path.abspath(__file__))
        eb_path = os.path.join(topdir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb')
        eb_full_path = find_full_path(eb_path)
        self.assertTrue(eb_full_path)

        ec = EasyConfig(eb_full_path)
        self.eb = EasyBlock(ec)
        self.modgen = self.MODULE_GENERATOR_CLASS(self.eb)
        self.modgen.app.installdir = tempfile.mkdtemp(prefix='easybuild-modgen-test-')

        self.orig_module_naming_scheme = config.get_module_naming_scheme()

    def test_descr(self):
        """Test generation of module description (which includes '#%Module' header)."""

        descr = "gzip (GNU zip) is a popular data compression program as a replacement for compress"
        homepage = "http://www.gzip.org/"

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                "proc ModulesHelp { } {",
                "    puts stderr {",
                '',
                'Description',
                '===========',
                "%s" % descr,
                '',
                '',
                "More information",
                "================",
                " - Homepage: %s" % homepage,
                "    }",
                "}",
                '',
                "module-whatis {Description: %s}" % descr,
                "module-whatis {Homepage: %s}" % homepage,
                "module-whatis {URL: %s}" % homepage,
                '',
                "set root %s" % self.modgen.app.installdir,
                '',
                "conflict gzip",
                '',
            ])

        else:
            expected = '\n'.join([
                "help([==[",
                '',
                'Description',
                '===========',
                "%s" % descr,
                '',
                '',
                "More information",
                "================",
                " - Homepage: %s" % homepage,
                ']==])',
                '',
                "whatis([==[Description: %s]==])" % descr,
                "whatis([==[Homepage: %s]==])" % homepage,
                "whatis([==[URL: %s]==])" % homepage,
                '',
                'local root = "%s"' % self.modgen.app.installdir,
                '',
                'conflict("gzip")',
                '',
            ])

        desc = self.modgen.get_description()
        self.assertEqual(desc, expected)

        # Test description with list of 'whatis' strings
        self.eb.cfg['whatis'] = ['foo', 'bar']
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                "proc ModulesHelp { } {",
                "    puts stderr {",
                '',
                'Description',
                '===========',
                "%s" % descr,
                '',
                '',
                "More information",
                "================",
                " - Homepage: %s" % homepage,
                "    }",
                "}",
                '',
                "module-whatis {foo}",
                "module-whatis {bar}",
                '',
                "set root %s" % self.modgen.app.installdir,
                '',
                "conflict gzip",
                '',
            ])

        else:
            expected = '\n'.join([
                "help([==[",
                '',
                'Description',
                '===========',
                "%s" % descr,
                '',
                '',
                "More information",
                "================",
                " - Homepage: %s" % homepage,
                ']==])',
                '',
                "whatis([==[foo]==])",
                "whatis([==[bar]==])",
                '',
                'local root = "%s"' % self.modgen.app.installdir,
                '',
                'conflict("gzip")',
                '',
            ])

        desc = self.modgen.get_description()
        self.assertEqual(desc, expected)

    def test_set_default_module(self):
        """
        Test load part in generated module file.
        """

        # note: the lua modulefiles are only supported by Lmod. Therefore,
        # skipping when it is not the case
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua and not isinstance(self.modtool, Lmod):
            return

        # creating base path
        base_path = os.path.join(self.test_prefix, 'all')
        mkdir(base_path)

        # creating package module
        module_name = 'foobar_mod'
        modules_base_path = os.path.join(base_path, module_name)
        mkdir(modules_base_path)

        # creating two empty modules
        txt = self.modgen.MODULE_SHEBANG
        if txt:
            txt += '\n'
        txt += self.modgen.get_description()
        txt += self.modgen.set_environment('foo', 'bar')

        version_one = '1.0'
        version_one_path = os.path.join(modules_base_path, version_one + self.modgen.MODULE_FILE_EXTENSION)
        write_file(version_one_path, txt)

        version_two = '2.0'
        version_two_path = os.path.join(modules_base_path, version_two + self.modgen.MODULE_FILE_EXTENSION)
        write_file(version_two_path, txt)

        # using base_path to possible module load
        self.modtool.use(base_path)

        # setting foo version as default
        self.modgen.set_as_default(modules_base_path, version_one)
        self.modtool.load([module_name])
        full_module_name = module_name + '/' + version_one

        self.assertTrue(full_module_name in self.modtool.loaded_modules())
        self.modtool.purge()

        # setting bar version as default
        self.modgen.set_as_default(modules_base_path, version_two)
        self.modtool.load([module_name])
        full_module_name = module_name + '/' + version_two

        self.assertTrue(full_module_name in self.modtool.loaded_modules())
        self.modtool.purge()

    def test_is_loaded(self):
        """Test is_loaded method."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            test_cases = [
                # single module name as argument
                ('foo', "is-loaded foo"),
                ('Python/2.7.15-GCCcore-8.2.0', "is-loaded Python/2.7.15-GCCcore-8.2.0"),
                ('%(mod_name)s', "is-loaded %(mod_name)s"),
                # list of multiple module names as argument should result in list of is-loaded statements
                (['foo'], ['is-loaded foo']),
                (['foo/1.2.3', 'bar/4.5.6'], ['is-loaded foo/1.2.3', 'is-loaded bar/4.5.6']),
                (['foo', 'bar', 'baz'], ['is-loaded foo', 'is-loaded bar', 'is-loaded baz']),
            ]
        else:
            test_cases = [
                # single module name as argument
                ('foo', 'isloaded("foo")'),
                ('Python/2.7.15-GCCcore-8.2.0', 'isloaded("Python/2.7.15-GCCcore-8.2.0")'),
                ('%(mod_name)s', 'isloaded("%(mod_name)s")'),
                # list of multiple module names as argument
                (['foo'], ['isloaded("foo")']),
                (['foo/1.2.3', 'bar/4.5.6'], ['isloaded("foo/1.2.3")', 'isloaded("bar/4.5.6")']),
                (['foo', 'bar', 'baz'], ['isloaded("foo")', 'isloaded("bar")', 'isloaded("baz")']),
            ]

        for mod_names, expected in test_cases:
            self.assertEqual(self.modgen.is_loaded(mod_names), expected)

    def test_load(self):
        """Test load part in generated module file."""

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            # default: guarded module load (which implies no recursive unloading)
            expected = '\n'.join([
                '',
                "if { ![ is-loaded mod_name ] } {",
                "    module load mod_name",
                "}",
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name"))

            # with recursive unloading: no if is-loaded guard
            expected = '\n'.join([
                '',
                "if { [ module-info mode remove ] || ![ is-loaded mod_name ] } {",
                "    module load mod_name",
                "}",
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name", recursive_unload=True))

            init_config(build_options={'recursive_mod_unload': True})
            self.assertEqual(expected, self.modgen.load_module("mod_name"))

            # Lmod 7.6+ depends-on
            if self.modtool.supports_depends_on:
                expected = '\n'.join([
                    '',
                    "depends-on mod_name",
                    '',
                ])
                self.assertEqual(expected, self.modgen.load_module("mod_name", depends_on=True))
                init_config(build_options={'mod_depends_on': 'True'})
                self.assertEqual(expected, self.modgen.load_module("mod_name"))
            else:
                expected = "depends-on statements in generated module are not supported by modules tool"
                self.assertErrorRegex(EasyBuildError, expected, self.modgen.load_module, "mod_name", depends_on=True)
                init_config(build_options={'mod_depends_on': 'True'})
                self.assertErrorRegex(EasyBuildError, expected, self.modgen.load_module, "mod_name")
        else:
            # default: guarded module load (which implies no recursive unloading)
            expected = '\n'.join([
                '',
                'if not ( isloaded("mod_name") ) then',
                '    load("mod_name")',
                'end',
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name"))

            # with recursive unloading: if isloaded guard with unload
            # check
            expected = '\n'.join([
                '',
                'if mode() == "unload" or not ( isloaded("mod_name") ) then',
                '    load("mod_name")',
                'end',
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name", recursive_unload=True))

            init_config(build_options={'recursive_mod_unload': True})
            self.assertEqual(expected, self.modgen.load_module("mod_name"))

            # Lmod 7.6+ depends_on
            if self.modtool.supports_depends_on:
                expected = '\n'.join([
                    '',
                    'depends_on("mod_name")',
                    '',
                ])
                self.assertEqual(expected, self.modgen.load_module("mod_name", depends_on=True))
                init_config(build_options={'mod_depends_on': 'True'})
                self.assertEqual(expected, self.modgen.load_module("mod_name"))
            else:
                expected = "depends_on statements in generated module are not supported by modules tool"
                self.assertErrorRegex(EasyBuildError, expected, self.modgen.load_module, "mod_name", depends_on=True)
                init_config(build_options={'mod_depends_on': 'True'})
                self.assertErrorRegex(EasyBuildError, expected, self.modgen.load_module, "mod_name")

    def test_load_multi_deps(self):
        """Test generated load statement when multi_deps is involved."""

        # first check with typical two-version multi_deps
        multi_dep_mods = ['Python/3.7.4', 'Python/2.7.16']
        res = self.modgen.load_module('Python/3.7.4', multi_dep_mods=multi_dep_mods)

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "if { ![ is-loaded Python/3.7.4 ] && ![ is-loaded Python/2.7.16 ] } {",
                "    module load Python/3.7.4",
                '}',
                '',
            ])
        else:  # Lua syntax
            expected = '\n'.join([
                '',
                'if not ( isloaded("Python/3.7.4") ) and not ( isloaded("Python/2.7.16") ) then',
                '    load("Python/3.7.4")',
                'end',
                '',
            ])
        self.assertEqual(expected, res)

        if self.modtool.supports_depends_on:
            # two versions with depends_on
            res = self.modgen.load_module('Python/3.7.4', multi_dep_mods=multi_dep_mods, depends_on=True)

            if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
                expected = '\n'.join([
                    '',
                    "if { [ module-info mode remove ] || [ is-loaded Python/2.7.16 ] } {",
                    "    depends-on Python",
                    '} else {',
                    "    depends-on Python/3.7.4",
                    '}',
                    '',
                ])
            else:  # Lua syntax
                expected = '\n'.join([
                    '',
                    'if mode() == "unload" or isloaded("Python/2.7.16") then',
                    '    depends_on("Python")',
                    'else',
                    '    depends_on("Python/3.7.4")',
                    'end',
                    '',
                ])
            self.assertEqual(expected, res)

        # now test with more than two versions...
        multi_dep_mods = ['foo/1.2.3', 'foo/2.3.4', 'foo/3.4.5', 'foo/4.5.6']
        res = self.modgen.load_module('foo/1.2.3', multi_dep_mods=multi_dep_mods)

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "if { ![ is-loaded foo/1.2.3 ] && ![ is-loaded foo/2.3.4 ] && " +
                "![ is-loaded foo/3.4.5 ] && ![ is-loaded foo/4.5.6 ] } {",
                "    module load foo/1.2.3",
                '}',
                '',
            ])
        else:  # Lua syntax
            expected = '\n'.join([
                '',
                'if not ( isloaded("foo/1.2.3") ) and not ( isloaded("foo/2.3.4") ) and ' +
                'not ( isloaded("foo/3.4.5") ) and not ( isloaded("foo/4.5.6") ) then',
                '    load("foo/1.2.3")',
                'end',
                '',
            ])
        self.assertEqual(expected, res)

        if self.modtool.supports_depends_on:
            # more than two versions, with depends_on
            res = self.modgen.load_module('foo/1.2.3', multi_dep_mods=multi_dep_mods, depends_on=True)

            if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
                expected = '\n'.join([
                    '',
                    "if { [ module-info mode remove ] || [ is-loaded foo/2.3.4 ] || [ is-loaded foo/3.4.5 ] " +
                    "|| [ is-loaded foo/4.5.6 ] } {",
                    "    depends-on foo",
                    "} else {",
                    "    depends-on foo/1.2.3",
                    '}',
                    '',
                ])
            else:  # Lua syntax
                expected = '\n'.join([
                    '',
                    'if mode() == "unload" or isloaded("foo/2.3.4") or isloaded("foo/3.4.5") or ' +
                    'isloaded("foo/4.5.6") then',
                    '    depends_on("foo")',
                    'else',
                    '    depends_on("foo/1.2.3")',
                    'end',
                    '',
                ])
            self.assertEqual(expected, res)

        # what if we only list a single version?
        # see https://github.com/easybuilders/easybuild-framework/issues/3080
        res = self.modgen.load_module('one/1.0', multi_dep_mods=['one/1.0'])

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "if { ![ is-loaded one/1.0 ] } {",
                "    module load one/1.0",
                '}',
                '',
            ])
        else:  # Lua syntax
            expected = '\n'.join([
                '',
                'if not ( isloaded("one/1.0") ) then',
                '    load("one/1.0")',
                'end',
                '',
            ])
        self.assertEqual(expected, res)

        if self.modtool.supports_depends_on:
            res = self.modgen.load_module('one/1.0', multi_dep_mods=['one/1.0'], depends_on=True)

            if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
                expected = '\ndepends-on one/1.0\n'
            else:  # Lua syntax
                expected = '\ndepends_on("one/1.0")\n'
            self.assertEqual(expected, res)

    def test_modulerc(self):
        """Test modulerc method."""
        self.assertErrorRegex(EasyBuildError, "Incorrect module_version value type", self.modgen.modulerc, 'foo')

        arg = {'foo': 'bar'}
        error_pattern = "Incorrect module_version spec, expected keys"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.modgen.modulerc, arg)

        mod_ver_spec = {'modname': 'test/1.2.3.4.5', 'sym_version': '1.2.3', 'version': '1.2.3.4.5'}
        modulerc_path = os.path.join(self.test_prefix, 'test', self.modgen.DOT_MODULERC)

        # with Lmod 6.x, both .modulerc and wrapper module must be in the same location
        if isinstance(self.modtool, Lmod) and LooseVersion(self.modtool.version) < LooseVersion('7.0'):
            error = "Expected module file .* not found; "
            error += "Lmod 6.x requires that .modulerc and wrapped module file are in same directory"
            self.assertErrorRegex(EasyBuildError, error, self.modgen.modulerc, mod_ver_spec, filepath=modulerc_path)

        # if the wrapped module file is in place, everything should be fine
        write_file(os.path.join(self.test_prefix, 'test', '1.2.3.4.5'), '#%Module')
        modulerc = self.modgen.modulerc(mod_ver_spec, filepath=modulerc_path)

        # first, check raw contents of generated .modulerc file
        expected = '\n'.join([
            '#%Module',
            "module-version test/1.2.3.4.5 1.2.3",
        ])

        # two exceptions: EnvironmentModulesC, or Lmod 7.8 (or newer) and Lua syntax
        if self.modtool.__class__ == EnvironmentModulesC:
            expected = '\n'.join([
                '#%Module',
                'if {"test/1.2.3" eq [module-info version test/1.2.3]} {',
                '    module-version test/1.2.3.4.5 1.2.3',
                '}',
            ])
        elif self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            if isinstance(self.modtool, Lmod) and LooseVersion(self.modtool.version) >= LooseVersion('7.8'):
                expected = 'module_version("test/1.2.3.4.5", "1.2.3")'

        self.assertEqual(modulerc, expected)
        self.assertEqual(read_file(modulerc_path), expected)

        self.modtool.use(self.test_prefix)

        # 'show' picks up on symbolic versions, regardless of modules tool being used
        self.assertEqual(self.modtool.exist(['test/1.2.3.4.5', 'test/1.2.3.4', 'test/1.2.3']), [True, False, True])

        # loading of module with symbolic version works
        self.modtool.load(['test/1.2.3'])
        # test/1.2.3.4.5 is actually loaded (rather than test/1.2.3)
        res = self.modtool.list()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['mod_name'], 'test/1.2.3.4.5')

        # if same symbolic version is added again, nothing changes
        self.modgen.modulerc(mod_ver_spec, filepath=modulerc_path)
        self.assertEqual(read_file(modulerc_path), expected)

        # adding another module version results in appending to existing .modulerc file
        write_file(os.path.join(self.test_prefix, 'test', '4.5.6'), '#%Module')
        mod_ver_spec = {'modname': 'test/4.5.6', 'sym_version': '4', 'version': '4.5.6'}
        self.modgen.modulerc(mod_ver_spec, filepath=modulerc_path)

        if self.modtool.__class__ == EnvironmentModulesC:
            expected += '\n'.join([
                '',
                'if {"test/4" eq [module-info version test/4]} {',
                '    module-version test/4.5.6 4',
                '}',
            ])
        elif self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            if isinstance(self.modtool, Lmod) and LooseVersion(self.modtool.version) >= LooseVersion('7.8'):
                expected += '\nmodule_version("test/4.5.6", "4")'
            else:
                expected += "\nmodule-version test/4.5.6 4"
        else:
            expected += "\nmodule-version test/4.5.6 4"

        self.assertEqual(read_file(modulerc_path), expected)

        # adding same symbolic version again doesn't cause trouble or changes...
        self.modgen.modulerc(mod_ver_spec, filepath=modulerc_path)
        self.assertEqual(read_file(modulerc_path), expected)

        # starting from scratch yields expected results (only last symbolic version present)
        remove_file(modulerc_path)
        self.modgen.modulerc(mod_ver_spec, filepath=modulerc_path)

        expected = '\n'.join([
            '#%Module',
            "module-version test/4.5.6 4",
        ])

        # two exceptions: EnvironmentModulesC, or Lmod 7.8 (or newer) and Lua syntax
        if self.modtool.__class__ == EnvironmentModulesC:
            expected = '\n'.join([
                '#%Module',
                'if {"test/4" eq [module-info version test/4]} {',
                '    module-version test/4.5.6 4',
                '}',
            ])
        elif self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            if isinstance(self.modtool, Lmod) and LooseVersion(self.modtool.version) >= LooseVersion('7.8'):
                expected = 'module_version("test/4.5.6", "4")'

        self.assertEqual(read_file(modulerc_path), expected)

    def test_unload(self):
        """Test unload part in generated module file."""

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "module unload mod_name",
            ])
        else:
            expected = '\n'.join([
                '',
                'unload("mod_name")',
            ])

        self.assertEqual(expected, self.modgen.unload_module("mod_name"))

    def test_swap(self):
        """Test for swap statements."""

        # unguarded swap
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "module swap bar",
                '',
            ])
        else:
            expected = '\n'.join([
                '',
                'unload("foo")',
                'load("bar")',
                '',
            ])

        self.assertEqual(expected, self.modgen.swap_module('foo', 'bar', guarded=False))

        # guarded swap (enabled by default)
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "if { [ is-loaded foo ] } {",
                "    module swap bar",
                '} else {',
                "    module load bar",
                '}',
                '',
            ])
        else:
            expected = '\n'.join([
                '',
                'if isloaded("foo") then',
                '    unload("foo")',
                '    load("bar")',
                'else',
                '    load("bar")',
                'end',
                '',
            ])

        self.assertEqual(expected, self.modgen.swap_module('foo', 'bar', guarded=True))
        self.assertEqual(expected, self.modgen.swap_module('foo', 'bar'))

        # create tiny test Tcl module to make sure that tested modules tools support single-argument swap
        # see https://github.com/easybuilders/easybuild-framework/issues/3396;
        # this is known to fail with the ancient Tcl-only implementation of environment modules,
        # but that's considered to be a non-issue (since this is mostly relevant for Cray systems,
        # which are either using EnvironmentModulesC (3.2.10), EnvironmentModules (4.x) or Lmod...
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl and self.modtool.__class__ != EnvironmentModulesTcl:
            test_mod_txt = "#%Module\nmodule swap GCC/7.3.0-2.30"

            test_mod_fn = 'test_single_arg_swap/1.2.3'
            write_file(os.path.join(self.test_prefix, test_mod_fn), test_mod_txt)

            self.modtool.load(['GCC/4.6.3'])
            self.modtool.use(self.test_prefix)
            self.modtool.load(['test_single_arg_swap/1.2.3'])

            expected = ['GCC/7.3.0-2.30', 'test_single_arg_swap/1.2.3']
            self.assertEqual(sorted([m['mod_name'] for m in self.modtool.list()]), expected)

    def test_append_paths(self):
        """Test generating append-paths statements."""
        # test append_paths

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = ''.join([
                "append-path\tkey\t\t$root/path1\n",
                "append-path\tkey\t\t$root/path2\n",
                "append-path\tkey\t\t$root\n",
            ])
            paths = ['path1', 'path2', '']
            self.assertEqual(expected, self.modgen.append_paths("key", paths))
            # 2nd call should still give same result, no side-effects like manipulating passed list 'paths'!
            self.assertEqual(expected, self.modgen.append_paths("key", paths))

            expected = "append-path\tbar\t\t$root/foo\n"
            self.assertEqual(expected, self.modgen.append_paths("bar", "foo"))

            res = self.modgen.append_paths("key", ["/abs/path"], allow_abs=True)
            self.assertEqual("append-path\tkey\t\t/abs/path\n", res)

            res = self.modgen.append_paths('key', ['1234@example.com'], expand_relpaths=False)
            self.assertEqual("append-path\tkey\t\t1234@example.com\n", res)

        else:
            expected = ''.join([
                'append_path("key", pathJoin(root, "path1"))\n',
                'append_path("key", pathJoin(root, "path2"))\n',
                'append_path("key", root)\n',
            ])
            paths = ['path1', 'path2', '']
            self.assertEqual(expected, self.modgen.append_paths("key", paths))
            # 2nd call should still give same result, no side-effects like manipulating passed list 'paths'!
            self.assertEqual(expected, self.modgen.append_paths("key", paths))

            expected = 'append_path("bar", pathJoin(root, "foo"))\n'
            self.assertEqual(expected, self.modgen.append_paths("bar", "foo"))

            expected = 'append_path("key", "/abs/path")\n'
            self.assertEqual(expected, self.modgen.append_paths("key", ["/abs/path"], allow_abs=True))

            res = self.modgen.append_paths('key', ['1234@example.com'], expand_relpaths=False)
            self.assertEqual('append_path("key", "1234@example.com")\n', res)

        self.assertErrorRegex(EasyBuildError, "Absolute path %s/foo passed to update_paths "
                                              "which only expects relative paths." % self.modgen.app.installdir,
                              self.modgen.append_paths, "key2", ["bar", "%s/foo" % self.modgen.app.installdir])

    def test_module_extensions(self):
        """test the extensions() for extensions"""
        # not supported for Tcl modules
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            return

        # currently requires opt-in via --module-extensions
        init_config(build_options={'module_extensions': True})

        test_dir = os.path.abspath(os.path.dirname(__file__))
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')
        test_ec = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')

        ec = EasyConfig(test_ec)
        eb = EasyBlock(ec)
        modgen = self.MODULE_GENERATOR_CLASS(eb)
        desc = modgen.get_description()

        patterns = [
            r'^if convertToCanonical\(LmodVersion\(\)\) >= convertToCanonical\("8\.2\.8"\) then\n' +
            r'\s*extensions\("bar/0.0,barbar/0.0,ls,toy/0.0"\)\nend$',
        ]

        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(desc), "Pattern '%s' found in: %s" % (regex.pattern, desc))

    def test_prepend_paths(self):
        """Test generating prepend-paths statements."""
        # test prepend_paths

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = ''.join([
                "prepend-path\tkey\t\t$root/path1\n",
                "prepend-path\tkey\t\t$root/path2\n",
                "prepend-path\tkey\t\t$root\n",
            ])
            paths = ['path1', 'path2', '']
            self.assertEqual(expected, self.modgen.prepend_paths("key", paths))
            # 2nd call should still give same result, no side-effects like manipulating passed list 'paths'!
            self.assertEqual(expected, self.modgen.prepend_paths("key", paths))

            expected = "prepend-path\tbar\t\t$root/foo\n"
            self.assertEqual(expected, self.modgen.prepend_paths("bar", "foo"))

            res = self.modgen.prepend_paths("key", ["/abs/path"], allow_abs=True)
            self.assertEqual("prepend-path\tkey\t\t/abs/path\n", res)

            res = self.modgen.prepend_paths('key', ['1234@example.com'], expand_relpaths=False)
            self.assertEqual("prepend-path\tkey\t\t1234@example.com\n", res)

        else:
            expected = ''.join([
                'prepend_path("key", pathJoin(root, "path1"))\n',
                'prepend_path("key", pathJoin(root, "path2"))\n',
                'prepend_path("key", root)\n',
            ])
            paths = ['path1', 'path2', '']
            self.assertEqual(expected, self.modgen.prepend_paths("key", paths))
            # 2nd call should still give same result, no side-effects like manipulating passed list 'paths'!
            self.assertEqual(expected, self.modgen.prepend_paths("key", paths))

            expected = 'prepend_path("bar", pathJoin(root, "foo"))\n'
            self.assertEqual(expected, self.modgen.prepend_paths("bar", "foo"))

            expected = 'prepend_path("key", "/abs/path")\n'
            self.assertEqual(expected, self.modgen.prepend_paths("key", ["/abs/path"], allow_abs=True))

            res = self.modgen.prepend_paths('key', ['1234@example.com'], expand_relpaths=False)
            self.assertEqual('prepend_path("key", "1234@example.com")\n', res)

        self.assertErrorRegex(EasyBuildError, "Absolute path %s/foo passed to update_paths "
                                              "which only expects relative paths." % self.modgen.app.installdir,
                              self.modgen.prepend_paths, "key2", ["bar", "%s/foo" % self.modgen.app.installdir])

    def test_det_user_modpath(self):
        """Test for generic det_user_modpath method."""
        # None by default
        self.assertEqual(self.modgen.det_user_modpath(None), None)

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            self.assertEqual(self.modgen.det_user_modpath('my/own/modules'), '"my/own/modules" "all"')
        else:
            self.assertEqual(self.modgen.det_user_modpath('my/own/modules'), '"my/own/modules", "all"')

        # result is affected by --suffix-modules-path
        # {RUNTIME_ENV::FOO} gets translated into Tcl/Lua syntax for resolving $FOO at runtime
        init_config(build_options={'suffix_modules_path': ''})
        user_modpath = 'my/{RUNTIME_ENV::TEST123}/modules'
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            self.assertEqual(self.modgen.det_user_modpath(user_modpath), '"my" $::env(TEST123) "modules"')
        else:
            self.assertEqual(self.modgen.det_user_modpath(user_modpath), '"my", os.getenv("TEST123"), "modules"')

    def test_use(self):
        """Test generating module use statements."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            # Test regular 'module use' statements
            expected = ''.join([
                'module use "/some/path"\n',
                'module use "/foo/bar/baz"\n',
            ])
            self.assertEqual(self.modgen.use(["/some/path", "/foo/bar/baz"]), expected)

            # Test guarded 'module use' statements using prefix
            expected = ''.join([
                'if { [ file isdirectory [ file join "/foo" "/some/path" ] ] } {\n',
                '    module use [ file join "/foo" "/some/path" ]\n',
                '}\n',
            ])
            self.assertEqual(self.modgen.use(["/some/path"], prefix=quote_str("/foo"), guarded=True), expected)
        else:
            # Test regular 'module use' statements
            expected = ''.join([
                'prepend_path("MODULEPATH", "/some/path")\n',
                'prepend_path("MODULEPATH", "/foo/bar/baz")\n',
            ])
            self.assertEqual(self.modgen.use(["/some/path", "/foo/bar/baz"]), expected)

            # Test guarded 'module use' statements using prefix
            expected = ''.join([
                'if isDir(pathJoin("/foo", "/some/path")) then\n',
                '    prepend_path("MODULEPATH", pathJoin("/foo", "/some/path"))\n',
                'end\n',
            ])
            self.assertEqual(self.modgen.use(["/some/path"], prefix=quote_str("/foo"), guarded=True), expected)

    def test_env(self):
        """Test setting of environment variables."""
        # test set_environment
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            self.assertEqual('setenv\tkey\t\t"value"\n', self.modgen.set_environment("key", "value"))
            self.assertEqual('setenv\tkey\t\t"va\\"lue"\n', self.modgen.set_environment("key", 'va"lue'))
            self.assertEqual('setenv\tkey\t\t"va\'lue"\n', self.modgen.set_environment("key", "va'lue"))
            self.assertEqual('setenv\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_environment("key", """va"l'ue"""))
        else:
            self.assertEqual('setenv("key", "value")\n', self.modgen.set_environment("key", "value"))

    def test_getenv_cmd(self):
        """Test getting value of environment variable."""

        test_mod_file = os.path.join(self.test_prefix, 'test', '1.2.3')

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            # can't have $LMOD_QUIET set when testing with Tcl syntax,
            # otherwise we won't get the output produced by the test module file...
            if 'LMOD_QUIET' in os.environ:
                del os.environ['LMOD_QUIET']

            self.assertEqual('$::env(HOSTNAME)', self.modgen.getenv_cmd('HOSTNAME'))
            self.assertEqual('$::env(HOME)', self.modgen.getenv_cmd('HOME'))

            expected = '[if { [info exists ::env(TEST)] } { concat $::env(TEST) } else { concat "foobar" } ]'
            getenv_txt = self.modgen.getenv_cmd('TEST', default='foobar')
            self.assertEqual(getenv_txt, expected)

            write_file(test_mod_file, '#%%Module\nputs stderr %s' % getenv_txt)
        else:
            self.assertEqual('os.getenv("HOSTNAME")', self.modgen.getenv_cmd('HOSTNAME'))
            self.assertEqual('os.getenv("HOME")', self.modgen.getenv_cmd('HOME'))

            expected = 'os.getenv("TEST") or "foobar"'
            getenv_txt = self.modgen.getenv_cmd('TEST', default='foobar')
            self.assertEqual(getenv_txt, expected)

            test_mod_file += '.lua'
            write_file(test_mod_file, "io.stderr:write(%s)" % getenv_txt)

        # only test loading of test module in Lua syntax when using Lmod
        if isinstance(self.modtool, Lmod) or not test_mod_file.endswith('.lua'):
            self.modtool.use(self.test_prefix)
            out = self.modtool.run_module('load', 'test/1.2.3', return_stderr=True)
            self.assertEqual(out.strip(), 'foobar')

            os.environ['TEST'] = 'test_value_that_is_not_foobar'
            out = self.modtool.run_module('load', 'test/1.2.3', return_stderr=True)
            self.assertEqual(out.strip(), 'test_value_that_is_not_foobar')

    def test_alias(self):
        """Test setting of alias in modulefiles."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            # test set_alias
            self.assertEqual('set-alias\tkey\t\t"value"\n', self.modgen.set_alias("key", "value"))
            self.assertEqual('set-alias\tkey\t\t"va\\"lue"\n', self.modgen.set_alias("key", 'va"lue'))
            self.assertEqual('set-alias\tkey\t\t"va\'lue"\n', self.modgen.set_alias("key", "va'lue"))
            self.assertEqual('set-alias\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_alias("key", """va"l'ue"""))
        else:
            self.assertEqual('set_alias("key", "value")\n', self.modgen.set_alias("key", "value"))

    def test_tcl_quoting(self):
        """
        Test escaping of double quotes when using Tcl modules
        """

        # note: this is for Tcl syntax only, skipping when it is not the case
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            return

        # creating base path
        base_path = os.path.join(self.test_prefix, 'all')
        mkdir(base_path)

        # creating package module
        module_name = 'tcl_quoting_mod'
        modules_base_path = os.path.join(base_path, module_name)
        mkdir(modules_base_path)

        # creating module that sets envvar with quotation marks
        txt = self.modgen.MODULE_SHEBANG
        if txt:
            txt += '\n'
        txt += self.modgen.get_description()
        test_envvar = 'TEST_FLAGS'
        test_flags = '-Xflags1="foo bar" -Xflags2="more flags" '
        txt += self.modgen.set_environment(test_envvar, test_flags)

        version_one = '1.0'
        version_one_path = os.path.join(modules_base_path, version_one + self.modgen.MODULE_FILE_EXTENSION)
        write_file(version_one_path, txt)

        # using base_path to possible module load
        self.modtool.use(base_path)

        self.modtool.load([module_name])
        full_module_name = module_name + '/' + version_one

        self.assertTrue(full_module_name in self.modtool.loaded_modules())
        self.assertEqual(os.getenv(test_envvar), test_flags)
        self.modtool.purge()

    def test_conditional_statement(self):
        """Test formatting of conditional statements."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            cond = "is-loaded foo"
            load = "module load bar"

            simple_cond = self.modgen.conditional_statement(cond, load)
            expected = '\n'.join([
                "if { [ is-loaded foo ] } {",
                "    module load bar",
                '}',
                '',
            ])
            self.assertEqual(simple_cond, expected)

            neg_cond = self.modgen.conditional_statement(cond, load, negative=True)
            expected = '\n'.join([
                "if { ![ is-loaded foo ] } {",
                "    module load bar",
                '}',
                '',
            ])
            self.assertEqual(neg_cond, expected)

            if_else_cond = self.modgen.conditional_statement(cond, load, else_body='puts "foo"')
            expected = '\n'.join([
                "if { [ is-loaded foo ] } {",
                "    module load bar",
                "} else {",
                '    puts "foo"',
                '}',
                '',
            ])
            self.assertEqual(if_else_cond, expected)

            if_else_cond = self.modgen.conditional_statement(cond, load, else_body='puts "foo"', indent=False)
            expected = '\n'.join([
                "if { [ is-loaded foo ] } {",
                "module load bar",
                "} else {",
                'puts "foo"',
                '}',
                '',
            ])
            self.assertEqual(if_else_cond, expected)

        elif self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            cond = 'isloaded("foo")'
            load = 'load("bar")'

            simple_cond = self.modgen.conditional_statement(cond, load)
            expected = '\n'.join([
                'if isloaded("foo") then',
                '    load("bar")',
                'end',
                '',
            ])
            self.assertEqual(simple_cond, expected)

            neg_cond = self.modgen.conditional_statement(cond, load, negative=True)
            expected = '\n'.join([
                'if not ( isloaded("foo") ) then',
                '    load("bar")',
                'end',
                '',
            ])
            self.assertEqual(neg_cond, expected)

            if_else_cond = self.modgen.conditional_statement(cond, load, else_body='load("bleh")')
            expected = '\n'.join([
                'if isloaded("foo") then',
                '    load("bar")',
                'else',
                '    load("bleh")',
                'end',
                '',
            ])
            self.assertEqual(if_else_cond, expected)

            if_else_cond = self.modgen.conditional_statement(cond, load, else_body='load("bleh")', indent=False)
            expected = '\n'.join([
                'if isloaded("foo") then',
                'load("bar")',
                'else',
                'load("bleh")',
                'end',
                '',
            ])
            self.assertEqual(if_else_cond, expected)

        else:
            self.assertTrue(False, "Unknown module syntax")

    def test_load_msg(self):
        """Test including a load message in the module file."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = "\nif { [ module-info mode load ] } {\nputs stderr \"test\"\n}\n"
            self.assertEqual(expected, self.modgen.msg_on_load('test'))

            tcl_load_msg = '\n'.join([
                '',
                "if { [ module-info mode load ] } {",
                "puts stderr \"test \\$test \\$test",
                "test \\$foo \\$bar\"",
                "}",
                '',
            ])
            self.assertEqual(tcl_load_msg, self.modgen.msg_on_load('test $test \\$test\ntest $foo \\$bar'))

        else:
            expected = '\nif mode() == "load" then\nio.stderr:write([==[test]==])\nend\n'
            self.assertEqual(expected, self.modgen.msg_on_load('test'))

            lua_load_msg = '\n'.join([
                '',
                'if mode() == "load" then',
                'io.stderr:write([==[test $test \\$test',
                'test $foo \\$bar]==])',
                'end',
                '',
            ])
            self.assertEqual(lua_load_msg, self.modgen.msg_on_load('test $test \\$test\ntest $foo \\$bar'))

    def test_module_naming_scheme(self):
        """Test using default module naming scheme."""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        init_config(build_options={'valid_stops': all_stops})

        ecs_dir = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        ec_files = [os.path.join(subdir, fil) for (subdir, _, files) in os.walk(ecs_dir) for fil in files]

        build_options = {
            'check_osdeps': False,
            'external_modules_metadata': {},
            'robot_path': [ecs_dir],
            'valid_stops': all_stops,
            'validate': False,
        }
        init_config(build_options=build_options)

        def test_mns():
            """Test default module naming scheme."""
            # test default naming scheme
            for ec_file in [f for f in ec_files if 'broken' not in os.path.basename(f)]:
                ec_path = os.path.abspath(ec_file)
                ecs = process_easyconfig(ec_path, validate=False)
                # derive module name directly from easyconfig file name
                ec_fn = os.path.basename(ec_file)
                if ec_fn in ec2mod_map:
                    # only check first, ignore any others (occurs when blocks are used (format v1.0 only))
                    self.assertEqual(ec2mod_map[ec_fn], ActiveMNS().det_full_module_name(ecs[0]['ec']))

        # test default module naming scheme
        default_ec2mod_map = {
            'GCC-4.6.3.eb': 'GCC/4.6.3',
            'gzip-1.4.eb': 'gzip/1.4',
            'gzip-1.4-GCC-4.6.3.eb': 'gzip/1.4-GCC-4.6.3',
            'gzip-1.5-foss-2018a.eb': 'gzip/1.5-foss-2018a',
            'gzip-1.5-intel-2018a.eb': 'gzip/1.5-intel-2018a',
            'toy-0.0.eb': 'toy/0.0',
            'toy-0.0-multiple.eb': 'toy/0.0-somesuffix',  # first block sets versionsuffix to '-somesuffix'
        }
        ec2mod_map = default_ec2mod_map
        test_mns()

        # generating module name from non-parsed easyconfig works fine
        non_parsed = {
            'name': 'foo',
            'version': '1.2.3',
            'versionsuffix': '-bar',
            'toolchain': {
                'name': 't00ls',
                'version': '6.6.6',
            },
        }
        self.assertEqual('foo/1.2.3-t00ls-6.6.6-bar', ActiveMNS().det_full_module_name(non_parsed))

        # make sure test module naming schemes are available
        mns_mods = ['broken_module_naming_scheme', 'test_module_naming_scheme', 'test_module_naming_scheme_more']
        for test_mns_mod in mns_mods:
            mns_path = "easybuild.tools.module_naming_scheme.%s" % test_mns_mod
            __import__(mns_path, globals(), locals(), [''])
        init_config(build_options=build_options)

        # verify that key errors in module naming scheme are reported properly
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'BrokenModuleNamingScheme'
        init_config(build_options=build_options)

        err_pattern = 'nosucheasyconfigparameteravailable'
        ec_file = os.path.join(ecs_dir, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb')
        self.assertErrorRegex(EasyBuildError, err_pattern, EasyConfig, ec_file)

        # test simple custom module naming scheme
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'TestModuleNamingScheme'
        init_config(build_options=build_options)
        ec2mod_map = {
            'GCC-4.6.3.eb': 'GCC/4.6.3',
            'gzip-1.4.eb': 'gzip/1.4',
            'gzip-1.4-GCC-4.6.3.eb': 'gnu/gzip/1.4',
            'gzip-1.5-foss-2018a.eb': 'gnu/openmpi/gzip/1.5',
            'gzip-1.5-intel-2018a.eb': 'intel/intelmpi/gzip/1.5',
            'toy-0.0.eb': 'toy/0.0',
            'toy-0.0-multiple.eb': 'toy/0.0',  # test module naming scheme ignores version suffixes
        }
        test_mns()

        ec = EasyConfig(os.path.join(ecs_dir, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb'))
        self.assertEqual(ec.toolchain.det_short_module_name(), 'foss/2018a')

        # test module naming scheme using all available easyconfig parameters
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'TestModuleNamingSchemeMore'
        init_config(build_options=build_options)
        # note: these checksums will change if another easyconfig parameter is added
        ec2mod_map = {
            'GCC-4.6.3.eb': 'GCC/355ab0c0b66cedfd6e87695ef152a0ebe45b8b28',
            'gzip-1.4.eb': 'gzip/c2e522ded75b05c2b2074042fc39b5562b9929c3',
            'gzip-1.4-GCC-4.6.3.eb': 'gzip/585eba598f33c64ef01c6fa47af0fc37f3751311',
            'gzip-1.5-foss-2018a.eb': 'gzip/65dc39f92bf634667c478c50e43f0cda96b093a9',
            'gzip-1.5-intel-2018a.eb': 'gzip/0a4725f4720103eff8ffdadf8ffb187b988fb805',
            'toy-0.0.eb': 'toy/d3cd467f89ab0bce1f2bcd553315524a3a5c8b34',
            'toy-0.0-multiple.eb': 'toy/d3cd467f89ab0bce1f2bcd553315524a3a5c8b34',
        }
        test_mns()

        # test determining module name for dependencies (i.e. non-parsed easyconfigs)
        # using a module naming scheme that requires all easyconfig parameters
        ec2mod_map['gzip-1.5-foss-2018a.eb'] = 'gzip/.65dc39f92bf634667c478c50e43f0cda96b093a9'
        for dep_ec, dep_spec in [
            ('GCC-4.6.3.eb', {
                'name': 'GCC',
                'version': '4.6.3',
                'versionsuffix': '',
                'toolchain': {'name': 'system', 'version': 'system'},
                'hidden': False,
            }),
            ('gzip-1.5-foss-2018a.eb', {
                'name': 'gzip',
                'version': '1.5',
                'versionsuffix': '',
                'toolchain': {'name': 'foss', 'version': '2018a'},
                'hidden': True,
            }),
            ('toy-0.0-multiple.eb', {
                'name': 'toy',
                'version': '0.0',
                'versionsuffix': '-multiple',
                'toolchain': {'name': 'system', 'version': 'system'},
                'hidden': False,
            }),
        ]:
            # determine full module name
            self.assertEqual(ActiveMNS().det_full_module_name(dep_spec), ec2mod_map[dep_ec])

        ec = EasyConfig(os.path.join(ecs_dir, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb'), hidden=True)
        self.assertEqual(ec.full_mod_name, ec2mod_map['gzip-1.5-foss-2018a.eb'])
        self.assertEqual(ec.toolchain.det_short_module_name(), 'foss/e69469ac250145c9e814e5dde93f5fde6d80375d')

        # restore default module naming scheme, and retest
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = self.orig_module_naming_scheme
        init_config(build_options=build_options)
        ec2mod_map = default_ec2mod_map
        test_mns()

    def test_mod_name_validation(self):
        """Test module naming validation."""
        # module name must be a string
        self.assertTrue(not is_valid_module_name(('foo', 'bar')))
        self.assertTrue(not is_valid_module_name(['foo', 'bar']))
        self.assertTrue(not is_valid_module_name(123))

        # module name must be relative
        self.assertTrue(not is_valid_module_name('/foo/bar'))

        # module name must only contain valid characters
        self.assertTrue(not is_valid_module_name('foo\x0bbar'))
        self.assertTrue(not is_valid_module_name('foo\x0cbar'))
        self.assertTrue(not is_valid_module_name('foo\rbar'))
        self.assertTrue(not is_valid_module_name('foo\0bar'))

        # valid module name must be accepted
        self.assertTrue(is_valid_module_name('gzip/foss-2018a-suffix'))
        self.assertTrue(is_valid_module_name('GCC/4.7.2'))
        self.assertTrue(is_valid_module_name('foo-bar/1.2.3'))
        self.assertTrue(is_valid_module_name('intel'))

    def test_is_short_modname_for(self):
        """Test is_short_modname_for method of module naming schemes."""
        test_cases = [
            ('GCC/4.7.2', 'GCC', True),
            ('gzip/1.6-gompi-2018a', 'gzip', True),
            ('OpenMPI/2.1.2-GCC-6.4.0-2.28', 'OpenMPI', True),
            ('ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20', 'ScaLAPACK', True),
            ('netCDF-C++/4.2-foss-2018a', 'netCDF-C++', True),
            ('gcc/4.7.2', 'GCC', False),
            ('ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20', 'OpenBLAS', False),
            ('apps/openblas/0.2.20', 'OpenBLAS', False),
            ('lib/math/OpenBLAS-stable/0.2.20', 'OpenBLAS', False),
            # required so PrgEnv can be listed versionless as external module in Cray toolchains
            ('PrgEnv', 'PrgEnv', True),
        ]
        for modname, softname, res in test_cases:
            if res:
                errormsg = "%s is recognised as a module for '%s'" % (modname, softname)
            else:
                errormsg = "%s is NOT recognised as a module for '%s'" % (modname, softname)
            self.assertEqual(ActiveMNS().is_short_modname_for(modname, softname), res, errormsg)

    def test_hierarchical_mns(self):
        """Test hierarchical module naming scheme."""

        moduleclasses = ['base', 'compiler', 'mpi', 'numlib', 'system', 'toolchain']
        ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [ecs_dir],
            'valid_stops': all_stops,
            'validate': False,
            'valid_module_classes': moduleclasses,
        }

        def test_ec(ecfile, short_modname, mod_subdir, modpath_exts, user_modpath_exts, init_modpaths):
            """Test whether active module naming scheme returns expected values."""
            ec = EasyConfig(glob.glob(os.path.join(ecs_dir, '*', '*', ecfile))[0])
            self.assertEqual(ActiveMNS().det_full_module_name(ec), os.path.join(mod_subdir, short_modname))
            self.assertEqual(ActiveMNS().det_short_module_name(ec), short_modname)
            self.assertEqual(ActiveMNS().det_module_subdir(ec), mod_subdir)
            self.assertEqual(ActiveMNS().det_modpath_extensions(ec), modpath_exts)
            self.assertEqual(ActiveMNS().det_user_modpath_extensions(ec), user_modpath_exts)
            self.assertEqual(ActiveMNS().det_init_modulepaths(ec), init_modpaths)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options=build_options)

        # format: easyconfig_file: (short_mod_name, mod_subdir, modpath_exts, user_modpath_exts, init_modpaths)
        iccver = '2016.1.150-GCC-4.9.3-2.25'
        impi_ec = 'impi-5.1.2.150-iccifort-2016.1.150-GCC-4.9.3-2.25.eb'
        imkl_ec = 'imkl-11.3.1.150-iimpi-2016.01.eb'
        test_ecs = {
            'GCC-6.4.0-2.28.eb': ('GCC/6.4.0-2.28', 'Core', ['Compiler/GCC/6.4.0-2.28'],
                                  ['Compiler/GCC/6.4.0-2.28'], ['Core']),
            'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb': ('OpenMPI/2.1.2', 'Compiler/GCC/6.4.0-2.28',
                                                ['MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2'],
                                                ['MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2'], ['Core']),
            'gzip-1.5-foss-2018a.eb': ('gzip/1.5', 'MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2', [],
                                       [], ['Core']),
            'foss-2018a.eb': ('foss/2018a', 'Core', [],
                              [], ['Core']),
            'icc-2016.1.150-GCC-4.9.3-2.25.eb': ('icc/%s' % iccver, 'Core', ['Compiler/intel/%s' % iccver],
                                                 ['Compiler/intel/%s' % iccver], ['Core']),
            'ifort-2016.1.150.eb': ('ifort/2016.1.150', 'Core', ['Compiler/intel/2016.1.150'],
                                    ['Compiler/intel/2016.1.150'], ['Core']),
            'iccifort-2019.4.243.eb': ('iccifort/2019.4.243', 'Core', ['Compiler/intel/2019.4.243'],
                                       ['Compiler/intel/2019.4.243'], ['Core']),
            'imkl-2019.4.243-iimpi-2019.08.eb': ('imkl/2019.4.243',
                                                 'MPI/intel/2019.4.243/impi/2019.4.243', [], [], ['Core']),
            'intel-compilers-2021.2.0.eb': ('intel-compilers/2021.2.0', 'Core',
                                            ['Compiler/intel/2021.2.0'], ['Compiler/intel/2021.2.0'], ['Core']),
            'impi-2021.2.0-intel-compilers-2021.2.0.eb': ('impi/2021.2.0', 'Compiler/intel/2021.2.0',
                                                          ['MPI/intel/2021.2.0/impi/2021.2.0'],
                                                          ['MPI/intel/2021.2.0/impi/2021.2.0'],
                                                          ['Core']),
            'imkl-2021.2.0-iimpi-2021a.eb': ('imkl/2021.2.0', 'MPI/intel/2021.2.0/impi/2021.2.0',
                                             [], [], ['Core']),
            'CUDA-9.1.85-GCC-6.4.0-2.28.eb': ('CUDA/9.1.85', 'Compiler/GCC/6.4.0-2.28',
                                              ['Compiler/GCC-CUDA/6.4.0-2.28-9.1.85'],
                                              ['Compiler/GCC-CUDA/6.4.0-2.28-9.1.85'], ['Core']),
            'CUDA-5.5.22.eb': ('CUDA/5.5.22', 'Core', [],
                               [], ['Core']),
            'CUDA-5.5.22-iccifort-2016.1.150-GCC-4.9.3-2.25.eb': ('CUDA/5.5.22',
                                                                  'Compiler/intel/%s' % iccver,
                                                                  ['Compiler/intel-CUDA/%s-5.5.22' % iccver],
                                                                  ['Compiler/intel-CUDA/%s-5.5.22' % iccver],
                                                                  ['Core']),
            'CUDA-10.1.243-iccifort-2019.4.243.eb': ('CUDA/10.1.243',
                                                     'Compiler/intel/2019.4.243',
                                                     ['Compiler/intel-CUDA/2019.4.243-10.1.243'],
                                                     ['Compiler/intel-CUDA/2019.4.243-10.1.243'],
                                                     ['Core']),
            impi_ec: ('impi/5.1.2.150', 'Compiler/intel/%s' % iccver, ['MPI/intel/%s/impi/5.1.2.150' % iccver],
                      ['MPI/intel/%s/impi/5.1.2.150' % iccver], ['Core']),
            imkl_ec: ('imkl/11.3.1.150', 'MPI/intel/%s/impi/5.1.2.150' % iccver, [],
                      [], ['Core']),
            'impi-5.1.2.150-iccifortcuda-2016.1.150.eb': ('impi/5.1.2.150', 'Compiler/intel-CUDA/%s-5.5.22' % iccver,
                                                          ['MPI/intel-CUDA/%s-5.5.22/impi/5.1.2.150' % iccver],
                                                          ['MPI/intel-CUDA/%s-5.5.22/impi/5.1.2.150' % iccver],
                                                          ['Core']),
            'CrayCCE-5.1.29.eb': ('CrayCCE/5.1.29', 'Core',
                                  ['Toolchain/CrayCCE/5.1.29'],
                                  ['Toolchain/CrayCCE/5.1.29'],
                                  ['Core']),
            'cpeGNU-21.04.eb': ('cpeGNU/21.04', 'Core',
                                ['Toolchain/cpeGNU/21.04'],
                                ['Toolchain/cpeGNU/21.04'],
                                ['Core']),
            'HPL-2.1-CrayCCE-5.1.29.eb': ('HPL/2.1', 'Toolchain/CrayCCE/5.1.29', [], [], ['Core']),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals)

        # impi with dummy toolchain, which doesn't make sense in a hierarchical context
        ec = EasyConfig(os.path.join(ecs_dir, 'i', 'impi', 'impi-5.1.2.150.eb'))
        self.assertErrorRegex(EasyBuildError, 'No compiler available.*MPI lib', ActiveMNS().det_modpath_extensions, ec)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'CategorizedHMNS'
        init_config(build_options=build_options)

        # format: easyconfig_file: (short_mod_name, mod_subdir, modpath_exts, user_modpath_exts)
        test_ecs = {
            'GCC-6.4.0-2.28.eb': ('GCC/6.4.0-2.28', 'Core/compiler',
                                  ['Compiler/GCC/6.4.0-2.28/%s' % c for c in moduleclasses],
                                  ['Compiler/GCC/6.4.0-2.28']),
            'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb': ('OpenMPI/2.1.2', 'Compiler/GCC/6.4.0-2.28/mpi',
                                                ['MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2/%s' % c for c in moduleclasses],
                                                ['MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2']),
            'gzip-1.5-foss-2018a.eb': ('gzip/1.5', 'MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2/tools',
                                       [], []),
            'foss-2018a.eb': ('foss/2018a', 'Core/toolchain',
                              [], []),
            'icc-2016.1.150-GCC-4.9.3-2.25.eb': ('icc/%s' % iccver, 'Core/compiler',
                                                 ['Compiler/intel/%s/%s' % (iccver, c) for c in moduleclasses],
                                                 ['Compiler/intel/%s' % iccver]),
            'ifort-2016.1.150.eb': ('ifort/2016.1.150', 'Core/compiler',
                                    ['Compiler/intel/2016.1.150/%s' % c for c in moduleclasses],
                                    ['Compiler/intel/2016.1.150']),
            'CUDA-9.1.85-GCC-6.4.0-2.28.eb': ('CUDA/9.1.85', 'Compiler/GCC/6.4.0-2.28/system',
                                              ['Compiler/GCC-CUDA/6.4.0-2.28-9.1.85/%s' % c for c in moduleclasses],
                                              ['Compiler/GCC-CUDA/6.4.0-2.28-9.1.85']),
            impi_ec: ('impi/5.1.2.150', 'Compiler/intel/%s/mpi' % iccver,
                      ['MPI/intel/%s/impi/5.1.2.150/%s' % (iccver, c) for c in moduleclasses],
                      ['MPI/intel/%s/impi/5.1.2.150' % iccver]),
            imkl_ec: ('imkl/11.3.1.150', 'MPI/intel/%s/impi/5.1.2.150/numlib' % iccver,
                      [], []),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals, init_modpaths=['Core/%s' % c for c in moduleclasses])

        # impi with dummy toolchain, which doesn't make sense in a hierarchical context
        ec = EasyConfig(os.path.join(ecs_dir, 'i', 'impi', 'impi-5.1.2.150.eb'))
        self.assertErrorRegex(EasyBuildError, 'No compiler available.*MPI lib', ActiveMNS().det_modpath_extensions, ec)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'CategorizedModuleNamingScheme'
        init_config(build_options=build_options)

        test_ecs = {
            'GCC-6.4.0-2.28.eb': ('compiler/GCC/6.4.0-2.28', '', [], [], []),
            'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb': ('mpi/OpenMPI/2.1.2-GCC-6.4.0-2.28', '', [], [], []),
            'gzip-1.5-foss-2018a.eb': ('tools/gzip/1.5-foss-2018a', '', [], [], []),
            'foss-2018a.eb': ('toolchain/foss/2018a', '', [], [], []),
            'impi-5.1.2.150.eb': ('mpi/impi/5.1.2.150', '', [], [], []),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = self.orig_module_naming_scheme
        init_config(build_options=build_options)

        test_ecs = {
            'GCC-6.4.0-2.28.eb': ('GCC/6.4.0-2.28', '', [], [], []),
            'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb': ('OpenMPI/2.1.2-GCC-6.4.0-2.28', '', [], [], []),
            'gzip-1.5-foss-2018a.eb': ('gzip/1.5-foss-2018a', '', [], [], []),
            'foss-2018a.eb': ('foss/2018a', '', [], [], []),
            'impi-5.1.2.150.eb': ('impi/5.1.2.150', '', [], [], []),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals)

    def test_dependencies_for(self):
        """Test for dependencies_for function."""
        expected = [
            'GCC/6.4.0-2.28',
            'OpenMPI/2.1.2-GCC-6.4.0-2.28',
            'OpenBLAS/0.2.20-GCC-6.4.0-2.28',
            'FFTW/3.3.7-gompi-2018a',
            'ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20',
            'hwloc/1.11.8-GCC-6.4.0-2.28',
            'gompi/2018a',
        ]
        self.assertEqual(dependencies_for('foss/2018a', self.modtool), expected)

        # only with depth=0, only direct dependencies are returned
        self.assertEqual(dependencies_for('foss/2018a', self.modtool, depth=0), expected[:-2])

        # Lmod 7.6+ is required to use depends-on
        if self.modtool.supports_depends_on:
            # also test on module file that includes depends_on statements
            test_modfile = os.path.join(self.test_prefix, 'test', '1.2.3')

            if self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
                test_modtxt = '\n'.join([
                    'depends_on("GCC/6.4.0-2.28")',
                    'depends_on("OpenMPI/2.1.2-GCC-6.4.0-2.28")',
                ])
                test_modfile += '.lua'
            else:
                test_modtxt = '\n'.join([
                    '#%Module',
                    "depends-on GCC/6.4.0-2.28",
                    "depends-on OpenMPI/2.1.2-GCC-6.4.0-2.28",
                ])

            write_file(test_modfile, test_modtxt)

            self.modtool.use(self.test_prefix)

            expected = [
                'GCC/6.4.0-2.28',
                'OpenMPI/2.1.2-GCC-6.4.0-2.28',
                'hwloc/1.11.8-GCC-6.4.0-2.28',  # recursive dep, via OpenMPI
            ]
            self.assertEqual(dependencies_for('test/1.2.3', self.modtool), expected)

    def test_det_installdir(self):
        """Test det_installdir method."""

        # first create a module file we can test with
        modtxt = self.modgen.MODULE_SHEBANG
        if modtxt:
            modtxt += '\n'

        modtxt += self.modgen.get_description()

        test_modfile = os.path.join(self.test_prefix, 'test' + self.modgen.MODULE_FILE_EXTENSION)
        write_file(test_modfile, modtxt)

        expected = self.modgen.app.installdir

        self.assertEqual(self.modgen.det_installdir(test_modfile), expected)

    def test_generated_module_file_swap(self):
        """Test loading a generated module file that includes swap statements."""

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            mod_ext = '.lua'

            if not isinstance(self.modtool, Lmod):
                # Lua module files are only supported by Lmod,
                # so early exit if that's not the case in the test setup
                return

        else:
            mod_ext = ''

        # empty test modules
        for modname in ('one/1.0', 'one/1.1'):
            modfile = os.path.join(self.test_prefix, modname + mod_ext)
            write_file(modfile, self.modgen.MODULE_SHEBANG)

        modulepath = os.getenv('MODULEPATH')
        if modulepath:
            self.modtool.unuse(modulepath)

        test_mod = os.path.join(self.test_prefix, 'test', '1.0' + mod_ext)
        test_mod_txt = '\n'.join([
            self.modgen.MODULE_SHEBANG,
            self.modgen.swap_module('one', 'one/1.1'),
        ])
        write_file(test_mod, test_mod_txt)

        # prepare environment for loading test module
        self.modtool.use(self.test_prefix)
        self.modtool.load(['one/1.0'])

        self.modtool.load(['test/1.0'])

        # check whether resulting environment is correct
        loaded_mods = self.modtool.list()
        self.assertEqual(loaded_mods[-1]['mod_name'], 'test/1.0')
        # one/1.0 module was swapped for one/1.1
        self.assertEqual(loaded_mods[-2]['mod_name'], 'one/1.1')


class TclModuleGeneratorTest(ModuleGeneratorTest):
    """Test for module_generator module for Tcl syntax."""
    MODULE_GENERATOR_CLASS = ModuleGeneratorTcl


class LuaModuleGeneratorTest(ModuleGeneratorTest):
    """Test for module_generator module for Tcl syntax."""
    MODULE_GENERATOR_CLASS = ModuleGeneratorLua


def suite():
    """ returns all the testcases in this module """
    suite = TestSuite()
    suite.addTests(TestLoaderFiltered().loadTestsFromTestCase(TclModuleGeneratorTest, sys.argv[1:]))
    suite.addTests(TestLoaderFiltered().loadTestsFromTestCase(LuaModuleGeneratorTest, sys.argv[1:]))
    return suite


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
