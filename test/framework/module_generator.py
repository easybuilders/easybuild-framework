##
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
##
"""
Unit tests for module_generator.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import shutil
import sys
import tempfile
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen
from vsc.utils.missing import get_subclasses

import easybuild.tools.module_generator
from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.tools import config
from easybuild.tools.module_generator import ModuleGenerator
from easybuild.tools.module_naming_scheme.utilities import is_valid_module_name
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ActiveMNS
from easybuild.tools.build_log import EasyBuildError
from test.framework.utilities import find_full_path


class ModuleGeneratorTest(EnhancedTestCase):
    """ testcase for ModuleGenerator """

    def setUp(self):
        """ initialize ModuleGenerator with test Application """
        super(ModuleGeneratorTest, self).setUp()
        # find .eb file
        eb_path = os.path.join(os.path.join(os.path.dirname(__file__), 'easyconfigs'), 'gzip-1.4.eb')
        eb_full_path = find_full_path(eb_path)
        self.assertTrue(eb_full_path)

        ec = EasyConfig(eb_full_path)
        self.eb = EasyBlock(ec)
        self.modgen = ModuleGenerator(self.eb)
        self.modgen.app.installdir = tempfile.mkdtemp(prefix='easybuild-modgen-test-')
        
        self.orig_module_naming_scheme = config.get_module_naming_scheme()

    def tearDown(self):
        """cleanup"""
        super(ModuleGeneratorTest, self).tearDown()
        os.remove(self.eb.logfile)
        shutil.rmtree(self.modgen.app.installdir)

    def test_descr(self):
        """Test generation of module description (which includes '#%Module' header)."""
        gzip_txt = "gzip (GNU zip) is a popular data compression program as a replacement for compress "
        gzip_txt += "- Homepage: http://www.gzip.org/"
        expected = '\n'.join([
            "#%Module",
            "",
            "proc ModulesHelp { } {",
            "    puts stderr {   %s" % gzip_txt,
            "    }",
            "}",
            "",
            "module-whatis {Description: %s}" % gzip_txt,
            "",
            "set root    %s" % self.modgen.app.installdir,
            "",
            "conflict    gzip",
            "",
        ]) 

        desc = self.modgen.get_description()
        self.assertEqual(desc, expected)

    def test_load(self):
        """Test load part in generated module file."""
        expected = [
            "",
            "if { ![is-loaded mod_name] } {",
            "    module load mod_name",
            "}",
            "",
        ]
        self.assertEqual('\n'.join(expected), self.modgen.load_module("mod_name"))

        # with recursive unloading: no if is-loaded guard
        expected = [
            "",
            "module load mod_name",
            "",
        ]
        self.assertEqual('\n'.join(expected), self.modgen.load_module("mod_name", recursive_unload=True))

    def test_unload(self):
        """Test unload part in generated module file."""
        expected = '\n'.join([
            "",
            "if { [is-loaded mod_name] } {",
            "    module unload mod_name",
            "}",
            "",
        ])
        self.assertEqual(expected, self.modgen.unload_module("mod_name"))

    def test_prepend_paths(self):
        """Test generating prepend-paths statements."""
        # test prepend_paths
        expected = ''.join([
            "prepend-path\tkey\t\t$root/path1\n",
            "prepend-path\tkey\t\t$root/path2\n",
        ])
        self.assertEqual(expected, self.modgen.prepend_paths("key", ["path1", "path2"]))

        expected = "prepend-path\tbar\t\t$root/foo\n"
        self.assertEqual(expected, self.modgen.prepend_paths("bar", "foo"))

        self.assertEqual("prepend-path\tkey\t\t/abs/path\n", self.modgen.prepend_paths("key", ["/abs/path"], allow_abs=True))

        self.assertErrorRegex(EasyBuildError, "Absolute path %s/foo passed to prepend_paths " \
                                              "which only expects relative paths." % self.modgen.app.installdir,
                              self.modgen.prepend_paths, "key2", ["bar", "%s/foo" % self.modgen.app.installdir])

    def test_use(self):
        """Test generating module use statements."""
        expected = '\n'.join([
            "module use /some/path",
            "module use /foo/bar/baz",
        ])
        self.assertEqual(self.modgen.use(["/some/path", "/foo/bar/baz"]), expected)

    def test_env(self):
        """Test setting of environment variables."""
        # test set_environment
        self.assertEqual('setenv\tkey\t\t"value"\n', self.modgen.set_environment("key", "value"))
        self.assertEqual("setenv\tkey\t\t'va\"lue'\n", self.modgen.set_environment("key", 'va"lue'))
        self.assertEqual('setenv\tkey\t\t"va\'lue"\n', self.modgen.set_environment("key", "va'lue"))
        self.assertEqual('setenv\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_environment("key", """va"l'ue"""))
    
    def test_alias(self):
        """Test setting of alias in modulefiles."""
        # test set_alias
        self.assertEqual('set-alias\tkey\t\t"value"\n', self.modgen.set_alias("key", "value"))
        self.assertEqual("set-alias\tkey\t\t'va\"lue'\n", self.modgen.set_alias("key", 'va"lue'))
        self.assertEqual('set-alias\tkey\t\t"va\'lue"\n', self.modgen.set_alias("key", "va'lue"))
        self.assertEqual('set-alias\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_alias("key", """va"l'ue"""))

    def test_load_msg(self):
        """Test including a load message in the module file."""
        tcl_load_msg = '\nif [ module-info mode load ] {\n        puts stderr     "test"\n}\n'
        self.assertEqual(tcl_load_msg, self.modgen.msg_on_load('test'))

    def test_tcl_footer(self):
        """Test including a Tcl footer."""
        tcltxt = 'puts stderr "foo"'
        self.assertEqual(tcltxt, self.modgen.add_tcl_footer(tcltxt))

    def test_module_naming_scheme(self):
        """Test using default module naming scheme."""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        init_config(build_options={'valid_stops': all_stops})

        ecs_dir = os.path.join(os.path.dirname(__file__), 'easyconfigs')
        ec_files = [os.path.join(subdir, fil) for (subdir, _, files) in os.walk(ecs_dir) for fil in files]
        ec_files = [fil for fil in ec_files if not "v2.0" in fil]  # TODO FIXME: drop this once 2.0 support works

        build_options = {
            'check_osdeps': False,
            'robot_path': [ecs_dir],
            'valid_stops': all_stops,
            'validate': False,
        }
        init_config(build_options=build_options)

        def test_mns():
            """Test default module naming scheme."""
            # test default naming scheme
            for ec_file in ec_files:
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

        # install custom module naming scheme dynamically
        test_mns_parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox')
        sys.path.append(test_mns_parent_dir)
        reload(easybuild)
        reload(easybuild.tools)
        reload(easybuild.tools.module_naming_scheme)

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
        self.assertErrorRegex(KeyError, err_pattern, EasyConfig, os.path.join(ecs_dir, 'gzip-1.5-goolf-1.4.10.eb'))

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
            'gzip-1.4.eb': 'gzip/8805ec3152d2a4a08b6c06d740c23abe1a4d059f',
            'gzip-1.4-GCC-4.6.3.eb': 'gzip/863557cc81811f8c3f4426a4b45aa269fa54130b',
            'gzip-1.5-goolf-1.4.10.eb': 'gzip/b63c2b8cc518905473ccda023100b2d3cff52d55',
            'gzip-1.5-ictce-4.1.13.eb': 'gzip/3d49f0e112708a95f79ed38b91b506366c0299ab',
            'toy-0.0.eb': 'toy/44a206d9e8c14130cc9f79e061468303c6e91b53',
            'toy-0.0-multiple.eb': 'toy/44a206d9e8c14130cc9f79e061468303c6e91b53',
        }
        test_mns()

        # test determining module name for dependencies (i.e. non-parsed easyconfigs)
        # using a module naming scheme that requires all easyconfig parameters
        for dep_ec, dep_spec in [
            ('GCC-4.6.3.eb', {
                'name': 'GCC',
                'version': '4.6.3',
                'versionsuffix': '',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
            }),
            ('gzip-1.5-goolf-1.4.10.eb', {
                'name': 'gzip',
                'version': '1.5',
                'versionsuffix': '',
                'toolchain': {'name': 'goolf', 'version': '1.4.10'},
            }),
            ('toy-0.0-multiple.eb', {
                'name': 'toy',
                'version': '0.0',
                'versionsuffix': '-multiple',
                'toolchain': {'name': 'dummy', 'version': 'dummy'},
            }),
        ]:
            # determine full module name
            self.assertEqual(ActiveMNS().det_full_module_name(dep_spec), ec2mod_map[dep_ec])

        ec = EasyConfig(os.path.join(ecs_dir, 'gzip-1.5-goolf-1.4.10.eb'))
        self.assertEqual(ec.toolchain.det_short_module_name(), 'goolf/b7515d0efd346970f55e7aa8522e239a70007021')

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

    def test_hierarchical_mns(self):
        """Test hierarchical module naming scheme."""
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

        ec = EasyConfig(os.path.join(ecs_dir, 'GCC-4.7.2.eb'))
        self.assertEqual(ActiveMNS().det_full_module_name(ec), 'Core/GCC/4.7.2')
        self.assertEqual(ActiveMNS().det_short_module_name(ec), 'GCC/4.7.2')
        self.assertEqual(ActiveMNS().det_module_subdir(ec), 'Core')
        self.assertEqual(ActiveMNS().det_modpath_extensions(ec), ['Compiler/GCC/4.7.2'])
        self.assertEqual(ActiveMNS().det_init_modulepaths(ec), ['Core'])

        ec = EasyConfig(os.path.join(ecs_dir, 'OpenMPI-1.6.4-GCC-4.7.2.eb'))
        self.assertEqual(ActiveMNS().det_full_module_name(ec), 'Compiler/GCC/4.7.2/OpenMPI/1.6.4')
        self.assertEqual(ActiveMNS().det_short_module_name(ec), 'OpenMPI/1.6.4')
        self.assertEqual(ActiveMNS().det_module_subdir(ec), 'Compiler/GCC/4.7.2')
        self.assertEqual(ActiveMNS().det_modpath_extensions(ec), ['MPI/GCC/4.7.2/OpenMPI/1.6.4'])
        self.assertEqual(ActiveMNS().det_init_modulepaths(ec), ['Core'])

        ec = EasyConfig(os.path.join(ecs_dir, 'gzip-1.5-goolf-1.4.10.eb'))
        self.assertEqual(ActiveMNS().det_full_module_name(ec), 'MPI/GCC/4.7.2/OpenMPI/1.6.4/gzip/1.5')
        self.assertEqual(ActiveMNS().det_short_module_name(ec), 'gzip/1.5')
        self.assertEqual(ActiveMNS().det_module_subdir(ec), 'MPI/GCC/4.7.2/OpenMPI/1.6.4')
        self.assertEqual(ActiveMNS().det_modpath_extensions(ec), [])
        self.assertEqual(ActiveMNS().det_init_modulepaths(ec), ['Core'])

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = self.orig_module_naming_scheme
        init_config(build_options=build_options)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ModuleGeneratorTest)


if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    main()
