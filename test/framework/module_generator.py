##
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
##
"""
Unit tests for module_generator.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import tempfile
from unittest import TestLoader, TestSuite, TextTestRunner
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.tools import config
from easybuild.tools.module_generator import ModuleGeneratorLua, ModuleGeneratorTcl
from easybuild.tools.module_naming_scheme.utilities import is_valid_module_name
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ActiveMNS
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.utilities import quote_str
from test.framework.utilities import EnhancedTestCase, find_full_path, init_config


class ModuleGeneratorTest(EnhancedTestCase):
    """Tests for module_generator module."""

    MODULE_GENERATOR_CLASS = None

    def setUp(self):
        """Test setup."""
        super(ModuleGeneratorTest, self).setUp()
        # find .eb file
        eb_path = os.path.join(os.path.join(os.path.dirname(__file__), 'easyconfigs'), 'gzip-1.4.eb')
        eb_full_path = find_full_path(eb_path)
        self.assertTrue(eb_full_path)

        ec = EasyConfig(eb_full_path)
        self.eb = EasyBlock(ec)
        self.modgen = self.MODULE_GENERATOR_CLASS(self.eb)
        self.modgen.app.installdir = tempfile.mkdtemp(prefix='easybuild-modgen-test-')
        
        self.orig_module_naming_scheme = config.get_module_naming_scheme()

    def test_descr(self):
        """Test generation of module description (which includes '#%Module' header)."""

        gzip_txt = "gzip (GNU zip) is a popular data compression program as a replacement for compress "
        gzip_txt += "- Homepage: http://www.gzip.org/"

        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                "proc ModulesHelp { } {",
                "    puts stderr { %s" % gzip_txt,
                "    }",
                "}",
                '',
                "module-whatis {Description: %s}" % gzip_txt,
                '',
                "set root %s" % self.modgen.app.installdir,
                '',
                "conflict gzip",
                '',
            ])

        else:
            expected = '\n'.join([
                'help([[%s]])' % gzip_txt,
                '',
                "whatis([[Description: %s]])" % gzip_txt,
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
                "    puts stderr { %s" % gzip_txt,
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
                'help([[%s]])' % gzip_txt,
                '',
                "whatis([[foo]])",
                "whatis([[bar]])",
                '',
                'local root = "%s"' % self.modgen.app.installdir,
                '',
                'conflict("gzip")',
                '',
            ])

        desc = self.modgen.get_description()
        self.assertEqual(desc, expected)

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
                "module load mod_name",
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name", recursive_unload=True))

            init_config(build_options={'recursive_mod_unload': True})
            self.assertEqual(expected, self.modgen.load_module("mod_name"))
        else:
            # default: guarded module load (which implies no recursive unloading)
            expected = '\n'.join([
                '',
                'if not isloaded("mod_name") then',
                '    load("mod_name")',
                'end',
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name"))

            # with recursive unloading: no if isloaded guard
            expected = '\n'.join([
                '',
                'load("mod_name")',
                '',
            ])
            self.assertEqual(expected, self.modgen.load_module("mod_name", recursive_unload=True))

            init_config(build_options={'recursive_mod_unload': True})
            self.assertEqual(expected, self.modgen.load_module("mod_name"))

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
                "module swap foo bar",
                '',
            ])
        else:
            expected = '\n'.join([
                '',
                'swap("foo", "bar")',
                '',
            ])

        self.assertEqual(expected, self.modgen.swap_module('foo', 'bar', guarded=False))

        # guarded swap (enabled by default)
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            expected = '\n'.join([
                '',
                "if { [ is-loaded foo ] } {",
                "    module swap foo bar",
                '} else {',
                "    module load bar",
                '}',
                '',
            ])
        else:
            expected = '\n'.join([
                '',
                'if isloaded("foo") then',
                '    swap("foo", "bar")',
                'else',
                '    load("bar")',
                'end',
                '',
            ])

        self.assertEqual(expected, self.modgen.swap_module('foo', 'bar', guarded=True))
        self.assertEqual(expected, self.modgen.swap_module('foo', 'bar'))

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

        self.assertErrorRegex(EasyBuildError, "Absolute path %s/foo passed to prepend_paths " \
                                              "which only expects relative paths." % self.modgen.app.installdir,
                              self.modgen.prepend_paths, "key2", ["bar", "%s/foo" % self.modgen.app.installdir])

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
            self.assertEqual("setenv\tkey\t\t'va\"lue'\n", self.modgen.set_environment("key", 'va"lue'))
            self.assertEqual('setenv\tkey\t\t"va\'lue"\n', self.modgen.set_environment("key", "va'lue"))
            self.assertEqual('setenv\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_environment("key", """va"l'ue"""))
        else:
            self.assertEqual('setenv("key", "value")\n', self.modgen.set_environment("key", "value"))

    def test_getenv_cmd(self):
        """Test getting value of environment variable."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            self.assertEqual('$env(HOSTNAME)', self.modgen.getenv_cmd('HOSTNAME'))
            self.assertEqual('$env(HOME)', self.modgen.getenv_cmd('HOME'))
        else:
            self.assertEqual('os.getenv("HOSTNAME")', self.modgen.getenv_cmd('HOSTNAME'))
            self.assertEqual('os.getenv("HOME")', self.modgen.getenv_cmd('HOME'))

    def test_alias(self):
        """Test setting of alias in modulefiles."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            # test set_alias
            self.assertEqual('set-alias\tkey\t\t"value"\n', self.modgen.set_alias("key", "value"))
            self.assertEqual("set-alias\tkey\t\t'va\"lue'\n", self.modgen.set_alias("key", 'va"lue'))
            self.assertEqual('set-alias\tkey\t\t"va\'lue"\n', self.modgen.set_alias("key", "va'lue"))
            self.assertEqual('set-alias\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_alias("key", """va"l'ue"""))
        else:
            self.assertEqual('set_alias("key", "value")\n', self.modgen.set_alias("key", "value"))

    def test_conditional_statement(self):
        """Test formatting of conditional statements."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            simple_cond = self.modgen.conditional_statement("is-loaded foo", "module load bar")
            expected = '\n'.join([
                "if { [ is-loaded foo ] } {",
                "    module load bar",
                '}',
                '',
            ])
            self.assertEqual(simple_cond, expected)

            neg_cond = self.modgen.conditional_statement("is-loaded foo", "module load bar", negative=True)
            expected = '\n'.join([
                "if { ![ is-loaded foo ] } {",
                "    module load bar",
                '}',
                '',
            ])
            self.assertEqual(neg_cond, expected)

            if_else_cond = self.modgen.conditional_statement("is-loaded foo", "module load bar", else_body='puts "foo"')
            expected = '\n'.join([
                "if { [ is-loaded foo ] } {",
                "    module load bar",
                "} else {",
                '    puts "foo"',
                '}',
                '',
            ])
            self.assertEqual(if_else_cond, expected)

        elif self.MODULE_GENERATOR_CLASS == ModuleGeneratorLua:
            simple_cond = self.modgen.conditional_statement('isloaded("foo")', 'load("bar")')
            expected = '\n'.join([
                'if isloaded("foo") then',
                '    load("bar")',
                'end',
                '',
            ])
            self.assertEqual(simple_cond, expected)

            neg_cond = self.modgen.conditional_statement('isloaded("foo")', 'load("bar")', negative=True)
            expected = '\n'.join([
                'if not isloaded("foo") then',
                '    load("bar")',
                'end',
                '',
            ])
            self.assertEqual(neg_cond, expected)

            if_else_cond = self.modgen.conditional_statement('isloaded("foo")', 'load("bar")', else_body='load("bleh")')
            expected = '\n'.join([
                'if isloaded("foo") then',
                '    load("bar")',
                'else',
                '    load("bleh")',
                'end',
                '',
            ])
            self.assertEqual(if_else_cond, expected)
        else:
            self.assertTrue(False, "Unknown module syntax")

    def test_load_msg(self):
        """Test including a load message in the module file."""
        if self.MODULE_GENERATOR_CLASS == ModuleGeneratorTcl:
            tcl_load_msg = '\n'.join([
                '',
                "if { [ module-info mode load ] } {",
                "    puts stderr \"test \\$test \\$test",
                "    test \\$foo \\$bar\"",
                "}",
                '',
            ])
            self.assertEqual(tcl_load_msg, self.modgen.msg_on_load('test $test \\$test\ntest $foo \\$bar'))
        else:
            pass

    def test_module_naming_scheme(self):
        """Test using default module naming scheme."""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        init_config(build_options={'valid_stops': all_stops})

        ecs_dir = os.path.join(os.path.dirname(__file__), 'easyconfigs')
        ec_files = [os.path.join(subdir, fil) for (subdir, _, files) in os.walk(ecs_dir) for fil in files]
        # TODO FIXME: drop this once 2.0/.yeb support works
        ec_files = [fil for fil in ec_files if not ('v2.0/' in fil or 'yeb/' in fil)]

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
            for ec_file in [f for f in ec_files if not 'broken' in os.path.basename(f)]:
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
            'gzip-1.5-goolf-1.4.10.eb': 'gzip/1.5-goolf-1.4.10',
            'gzip-1.5-ictce-4.1.13.eb': 'gzip/1.5-ictce-4.1.13',
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
        self.assertErrorRegex(EasyBuildError, err_pattern, EasyConfig, os.path.join(ecs_dir, 'gzip-1.5-goolf-1.4.10.eb'))

        # test simple custom module naming scheme
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'TestModuleNamingScheme'
        init_config(build_options=build_options)
        ec2mod_map = {
            'GCC-4.6.3.eb': 'GCC/4.6.3',
            'gzip-1.4.eb': 'gzip/1.4',
            'gzip-1.4-GCC-4.6.3.eb': 'gnu/gzip/1.4',
            'gzip-1.5-goolf-1.4.10.eb': 'gnu/openmpi/gzip/1.5',
            'gzip-1.5-ictce-4.1.13.eb': 'intel/intelmpi/gzip/1.5',
            'toy-0.0.eb': 'toy/0.0',
            'toy-0.0-multiple.eb': 'toy/0.0',  # test module naming scheme ignores version suffixes
        }
        test_mns()

        ec = EasyConfig(os.path.join(ecs_dir, 'gzip-1.5-goolf-1.4.10.eb'))
        self.assertEqual(ec.toolchain.det_short_module_name(), 'goolf/1.4.10')

        # test module naming scheme using all available easyconfig parameters
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'TestModuleNamingSchemeMore'
        init_config(build_options=build_options)
        # note: these checksums will change if another easyconfig parameter is added
        ec2mod_map = {
            'GCC-4.6.3.eb': 'GCC/9e9ab5a1e978f0843b5aedb63ac4f14c51efb859',
            'gzip-1.4.eb': 'gzip/53d5c13e85cb6945bd43a58d1c8d4a4c02f3462d',
            'gzip-1.4-GCC-4.6.3.eb': 'gzip/585eba598f33c64ef01c6fa47af0fc37f3751311',
            'gzip-1.5-goolf-1.4.10.eb': 'gzip/fceb41e04c26b540b7276c4246d1ecdd1e8251c9',
            'gzip-1.5-ictce-4.1.13.eb': 'gzip/ae16b3a0a330d4323987b360c0d024f244ac4498',
            'toy-0.0.eb': 'toy/44a206d9e8c14130cc9f79e061468303c6e91b53',
            'toy-0.0-multiple.eb': 'toy/44a206d9e8c14130cc9f79e061468303c6e91b53',
        }
        test_mns()

        # test determining module name for dependencies (i.e. non-parsed easyconfigs)
        # using a module naming scheme that requires all easyconfig parameters
        ec2mod_map['gzip-1.5-goolf-1.4.10.eb'] = 'gzip/.fceb41e04c26b540b7276c4246d1ecdd1e8251c9'
        for dep_ec, dep_spec in [
            ('GCC-4.6.3.eb', {
                'name': 'GCC',
                'version': '4.6.3',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
                'hidden': False,
            }),
            ('gzip-1.5-goolf-1.4.10.eb', {
                'name': 'gzip',
                'version': '1.5',
                'versionsuffix': '',
                'toolchain': {'name': 'goolf', 'version': '1.4.10'},
                'hidden': True,
            }),
            ('toy-0.0-multiple.eb', {
                'name': 'toy',
                'version': '0.0',
                'versionsuffix': '-multiple',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
                'hidden': False,
            }),
        ]:
            # determine full module name
            self.assertEqual(ActiveMNS().det_full_module_name(dep_spec), ec2mod_map[dep_ec])

        ec = EasyConfig(os.path.join(ecs_dir, 'gzip-1.5-goolf-1.4.10.eb'), hidden=True)
        self.assertEqual(ec.full_mod_name, ec2mod_map['gzip-1.5-goolf-1.4.10.eb'])
        self.assertEqual(ec.toolchain.det_short_module_name(), 'goolf/a86eb41d8f9c1d6f2d3d61cdb8f420cc2a21cada')

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
        self.assertTrue(is_valid_module_name('gzip/goolf-1.4.10-suffix'))
        self.assertTrue(is_valid_module_name('GCC/4.7.2'))
        self.assertTrue(is_valid_module_name('foo-bar/1.2.3'))
        self.assertTrue(is_valid_module_name('ictce'))

    def test_is_short_modname_for(self):
        """Test is_short_modname_for method of module naming schemes."""
        test_cases = [
            ('GCC/4.7.2', 'GCC', True),
            ('gzip/1.6-gompi-1.4.10', 'gzip', True),
            ('OpenMPI/1.6.4-GCC-4.7.2-no-OFED', 'OpenMPI', True),
            ('BLACS/1.1-gompi-1.1.0-no-OFED', 'BLACS', True),
            ('ScaLAPACK/1.8.0-gompi-1.1.0-no-OFED-ATLAS-3.8.4-LAPACK-3.4.0-BLACS-1.1', 'ScaLAPACK', True),
            ('netCDF-C++/4.2-goolf-1.4.10', 'netCDF-C++', True),
            ('gcc/4.7.2', 'GCC', False),
            ('ScaLAPACK/1.8.0-gompi-1.1.0-no-OFED-ATLAS-3.8.4-LAPACK-3.4.0-BLACS-1.1', 'BLACS', False),
            ('apps/blacs/1.1', 'BLACS', False),
            ('lib/math/BLACS-stable/1.1', 'BLACS', False),
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
        ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
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
            ec = EasyConfig(os.path.join(ecs_dir, ecfile))
            self.assertEqual(ActiveMNS().det_full_module_name(ec), os.path.join(mod_subdir, short_modname))
            self.assertEqual(ActiveMNS().det_short_module_name(ec), short_modname)
            self.assertEqual(ActiveMNS().det_module_subdir(ec), mod_subdir)
            self.assertEqual(ActiveMNS().det_modpath_extensions(ec), modpath_exts)
            self.assertEqual(ActiveMNS().det_user_modpath_extensions(ec), user_modpath_exts)
            self.assertEqual(ActiveMNS().det_init_modulepaths(ec), init_modpaths)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options=build_options)

        # format: easyconfig_file: (short_mod_name, mod_subdir, modpath_exts, user_modpath_exts, init_modpaths)
        iccver = '2013.5.192-GCC-4.8.3'
        impi_ec = 'impi-4.1.3.049-iccifort-2013.5.192-GCC-4.8.3.eb'
        imkl_ec = 'imkl-11.1.2.144-iimpi-5.5.3-GCC-4.8.3.eb'
        test_ecs = {
            'GCC-4.7.2.eb': ('GCC/4.7.2', 'Core', ['Compiler/GCC/4.7.2'],
                             ['Compiler/GCC/4.7.2'], ['Core']),
            'OpenMPI-1.6.4-GCC-4.7.2.eb': ('OpenMPI/1.6.4', 'Compiler/GCC/4.7.2', ['MPI/GCC/4.7.2/OpenMPI/1.6.4'],
                             ['MPI/GCC/4.7.2/OpenMPI/1.6.4'], ['Core']),
            'gzip-1.5-goolf-1.4.10.eb': ('gzip/1.5', 'MPI/GCC/4.7.2/OpenMPI/1.6.4', [],
                             [], ['Core']),
            'goolf-1.4.10.eb': ('goolf/1.4.10', 'Core', [],
                             [], ['Core']),
            'icc-2013.5.192-GCC-4.8.3.eb': ('icc/%s' % iccver, 'Core', ['Compiler/intel/%s' % iccver],
                             ['Compiler/intel/%s' % iccver], ['Core']),
            'ifort-2013.3.163.eb': ('ifort/2013.3.163', 'Core', ['Compiler/intel/2013.3.163'],
                             ['Compiler/intel/2013.3.163'], ['Core']),
            'CUDA-5.5.22-GCC-4.8.2.eb': ('CUDA/5.5.22', 'Compiler/GCC/4.8.2', ['Compiler/GCC-CUDA/4.8.2-5.5.22'],
                             ['Compiler/GCC-CUDA/4.8.2-5.5.22'], ['Core']),
            impi_ec: ('impi/4.1.3.049', 'Compiler/intel/%s' % iccver, ['MPI/intel/%s/impi/4.1.3.049' % iccver],
                             ['MPI/intel/%s/impi/4.1.3.049' % iccver], ['Core']),
            imkl_ec: ('imkl/11.1.2.144', 'MPI/intel/%s/impi/4.1.3.049' % iccver, [],
                             [], ['Core']),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals)

        # impi with dummy toolchain, which doesn't make sense in a hierarchical context
        ec = EasyConfig(os.path.join(ecs_dir, 'impi-4.1.3.049.eb'))
        self.assertErrorRegex(EasyBuildError, 'No compiler available.*MPI lib', ActiveMNS().det_modpath_extensions, ec)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'CategorizedHMNS'
        init_config(build_options=build_options)

        # format: easyconfig_file: (short_mod_name, mod_subdir, modpath_exts, user_modpath_exts)
        test_ecs = {
            'GCC-4.7.2.eb': ('GCC/4.7.2', 'Core/compiler',
                             ['Compiler/GCC/4.7.2/%s' % c for c in moduleclasses],
                             ['Compiler/GCC/4.7.2']),
            'OpenMPI-1.6.4-GCC-4.7.2.eb': ('OpenMPI/1.6.4', 'Compiler/GCC/4.7.2/mpi',
                             ['MPI/GCC/4.7.2/OpenMPI/1.6.4/%s' % c for c in moduleclasses],
                             ['MPI/GCC/4.7.2/OpenMPI/1.6.4']),
            'gzip-1.5-goolf-1.4.10.eb': ('gzip/1.5', 'MPI/GCC/4.7.2/OpenMPI/1.6.4/tools',
                             [], []),
            'goolf-1.4.10.eb': ('goolf/1.4.10', 'Core/toolchain',
                             [], []),
            'icc-2013.5.192-GCC-4.8.3.eb': ('icc/%s' % iccver, 'Core/compiler',
                             ['Compiler/intel/%s/%s' % (iccver, c) for c in moduleclasses],
                             ['Compiler/intel/%s' % iccver]),
            'ifort-2013.3.163.eb': ('ifort/2013.3.163', 'Core/compiler',
                             ['Compiler/intel/2013.3.163/%s' % c for c in moduleclasses],
                             ['Compiler/intel/2013.3.163']),
            'CUDA-5.5.22-GCC-4.8.2.eb': ('CUDA/5.5.22', 'Compiler/GCC/4.8.2/system',
                             ['Compiler/GCC-CUDA/4.8.2-5.5.22/%s' % c for c in moduleclasses],
                             ['Compiler/GCC-CUDA/4.8.2-5.5.22']),
            impi_ec: ('impi/4.1.3.049', 'Compiler/intel/%s/mpi' % iccver,
                             ['MPI/intel/%s/impi/4.1.3.049/%s' % (iccver, c) for c in moduleclasses],
                             ['MPI/intel/%s/impi/4.1.3.049' % iccver]),
            imkl_ec: ('imkl/11.1.2.144', 'MPI/intel/%s/impi/4.1.3.049/numlib' % iccver,
                             [], []),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals, init_modpaths = ['Core/%s' % c for c in moduleclasses])

        # impi with dummy toolchain, which doesn't make sense in a hierarchical context
        ec = EasyConfig(os.path.join(ecs_dir, 'impi-4.1.3.049.eb'))
        self.assertErrorRegex(EasyBuildError, 'No compiler available.*MPI lib', ActiveMNS().det_modpath_extensions, ec)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'CategorizedModuleNamingScheme'
        init_config(build_options=build_options)

        test_ecs = {
            'GCC-4.7.2.eb':               ('compiler/GCC/4.7.2',          '', [], [], []),
            'OpenMPI-1.6.4-GCC-4.7.2.eb': ('mpi/OpenMPI/1.6.4-GCC-4.7.2', '', [], [], []),
            'gzip-1.5-goolf-1.4.10.eb':   ('tools/gzip/1.5-goolf-1.4.10', '', [], [], []),
            'goolf-1.4.10.eb':            ('toolchain/goolf/1.4.10',      '', [], [], []),
            'impi-4.1.3.049.eb':          ('mpi/impi/4.1.3.049',          '', [], [], []),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = self.orig_module_naming_scheme
        init_config(build_options=build_options)

        test_ecs = {
            'GCC-4.7.2.eb': ('GCC/4.7.2', '', [], [], []),
            'OpenMPI-1.6.4-GCC-4.7.2.eb': ('OpenMPI/1.6.4-GCC-4.7.2', '', [], [], []),
            'gzip-1.5-goolf-1.4.10.eb': ('gzip/1.5-goolf-1.4.10', '', [], [], []),
            'goolf-1.4.10.eb': ('goolf/1.4.10', '', [], [], []),
            'impi-4.1.3.049.eb': ('impi/4.1.3.049', '', [], [], []),
        }
        for ecfile, mns_vals in test_ecs.items():
            test_ec(ecfile, *mns_vals)


class TclModuleGeneratorTest(ModuleGeneratorTest):
    """Test for module_generator module for Tcl syntax."""
    MODULE_GENERATOR_CLASS = ModuleGeneratorTcl


class LuaModuleGeneratorTest(ModuleGeneratorTest):
    """Test for module_generator module for Tcl syntax."""
    MODULE_GENERATOR_CLASS = ModuleGeneratorLua


def suite():
    """ returns all the testcases in this module """
    suite = TestSuite()
    suite.addTests(TestLoader().loadTestsFromTestCase(TclModuleGeneratorTest))
    suite.addTests(TestLoader().loadTestsFromTestCase(LuaModuleGeneratorTest))
    return suite


if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    TextTestRunner().run(suite())
