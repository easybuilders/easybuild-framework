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
from easybuild.tools.module_generator import ModuleGenerator, is_valid_module_name
from easybuild.tools.module_generator import det_full_module_name as det_full_module_name_mg
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import det_full_module_name as det_full_module_name_ec
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


    def test_env(self):
        """Test setting of environment variables."""
        # test set_environment
        self.assertEqual('setenv\tkey\t\t"value"\n', self.modgen.set_environment("key", "value"))
        self.assertEqual("setenv\tkey\t\t'va\"lue'\n", self.modgen.set_environment("key", 'va"lue'))
        self.assertEqual('setenv\tkey\t\t"va\'lue"\n', self.modgen.set_environment("key", "va'lue"))
        self.assertEqual('setenv\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_environment("key", """va"l'ue"""))

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
                    self.assertEqual(ec2mod_map[ec_fn], det_full_module_name_mg(ecs[0]['ec']))

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
        self.assertEqual('foo/1.2.3-t00ls-6.6.6-bar', det_full_module_name_ec(non_parsed))

        # install custom module naming scheme dynamically
        test_mns_parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox')
        sys.path.append(test_mns_parent_dir)
        reload(easybuild)
        reload(easybuild.tools)
        reload(easybuild.tools.module_naming_scheme)

        # make sure test module naming schemes are available
        for test_mns_mod in ['test_module_naming_scheme', 'test_module_naming_scheme_all']:
            mns_path = "easybuild.tools.module_naming_scheme.%s" % test_mns_mod
            mns_mod = __import__(mns_path, globals(), locals(), [''])
            test_mnss = dict([(x.__name__, x) for x in get_subclasses(mns_mod.ModuleNamingScheme)])
            easybuild.tools.module_naming_scheme.AVAIL_MODULE_NAMING_SCHEMES.update(test_mnss)
        init_config(build_options=build_options)

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

        # test module naming scheme using all available easyconfig parameters
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'TestModuleNamingSchemeAll'
        init_config(build_options=build_options)
        # note: these checksums will change if another easyconfig parameter is added
        ec2mod_map = {
            'GCC-4.6.3.eb': 'GCC/698cacc77167c6824f597f0b6371cad5e6749922',
            'gzip-1.4.eb': 'gzip/d240a51c643ec42e709d405d958c7b26f5a25d5a',
            'gzip-1.4-GCC-4.6.3.eb': 'gzip/cea02d332af7044ae5faf762cea2ef6ffed014d2',
            'gzip-1.5-goolf-1.4.10.eb': 'gzip/f1dbb38c4518a15fc8bb1fbf797ceda02f0cacd0',
            'gzip-1.5-ictce-4.1.13.eb': 'gzip/3ef9ac73b468c989f5a47b30098d340e92c3d0da',
            'toy-0.0.eb': 'toy/778417f0e140ebbaebd60d0f98c8b2411f980edf',
            'toy-0.0-multiple.eb': 'toy/2d45f3cde87dedf30662f4a005023d56d2532bf0',
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
            self.assertEqual(det_full_module_name_ec(dep_spec), ec2mod_map[dep_ec])

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


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ModuleGeneratorTest)


if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    main()
