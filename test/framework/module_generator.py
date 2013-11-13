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
Unit tests for module_generator.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import shutil
import sys
import tempfile
from unittest import TestCase, TestLoader, main
from vsc.utils.missing import get_subclasses

import easybuild.tools.options as eboptions
import easybuild.tools.module_generator
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools import config
from easybuild.tools.module_generator import ModuleGenerator, det_full_module_name, is_valid_module_name
from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.build_log import EasyBuildError
from test.framework.utilities import find_full_path


class ModuleGeneratorTest(TestCase):
    """ testcase for ModuleGenerator """

    # initialize configuration so config.get_modules_tool function works
    eb_go = eboptions.parse_options()
    config.init(eb_go.options, eb_go.get_options_by_section('config'))
    del eb_go

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def setUp(self):
        """ initialize ModuleGenerator with test Application """

        # find .eb file
        eb_path = os.path.join(os.path.join(os.path.dirname(__file__), 'easyconfigs'), 'gzip-1.4.eb')
        eb_full_path = find_full_path(eb_path)
        self.assertTrue(eb_full_path)

        self.eb = EasyBlock(eb_full_path)
        self.modgen = ModuleGenerator(self.eb)
        self.modgen.app.installdir = tempfile.mkdtemp(prefix='easybuild-modgen-test-')
        self.cwd = os.getcwd()

    def tearDown(self):
        """cleanup"""
        os.remove(self.eb.logfile)
        os.chdir(self.cwd)
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
            "module-whatis {%s}" % gzip_txt,
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
        expected = """
if { ![is-loaded mod_name] } {
    module load mod_name
}
"""
        self.assertEqual(expected, self.modgen.load_module("mod_name"))

    def test_unload(self):
        """Test unload part in generated module file."""
        expected = """
if { [is-loaded mod_name] } {
    module unload mod_name
}
"""
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
        ecs_dir = os.path.join(os.path.dirname(__file__), 'easyconfigs')
        ec_files = [os.path.join(subdir, fil) for (subdir, _, files) in os.walk(ecs_dir) for fil in files]
        ec_files = [fil for fil in ec_files if not "v2.0" in fil]  # TODO FIXME: drop this once 2.0 support works

        def test_default():
            """Test default module naming scheme."""
            # test default naming scheme
            for ec_file in ec_files:
                ec_path = os.path.abspath(ec_file)
                ec = EasyConfig(ec_path, validate=False, valid_stops=all_stops)
                # derive module name directly from easyconfig file name
                ec_name = '.'.join(ec_file.split(os.path.sep)[-1].split('.')[:-1])  # cut off '.eb' end
                mod_name = ec_name.split('-')[0]  # get module name (assuming no '-' is in software name)
                mod_version = '-'.join(ec_name.split('-')[1:])  # get module version
                self.assertEqual(os.path.join(mod_name, mod_version), det_full_module_name(ec))

        test_default()

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
        self.assertEqual('foo/1.2.3-t00ls-6.6.6-bar', det_full_module_name(non_parsed))

        # install custom module naming scheme dynamically
        test_mns_parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox')
        sys.path.append(test_mns_parent_dir)
        reload(easybuild)
        reload(easybuild.tools)
        reload(easybuild.tools.module_naming_scheme)
        orig_module_naming_scheme = config.get_module_naming_scheme()
        config.variables['module_naming_scheme'] = 'TestModuleNamingScheme'
        mns_path = "easybuild.tools.module_naming_scheme.test_module_naming_scheme"
        mns_mod = __import__(mns_path, globals(), locals(), [''])
        test_mnss = dict([(x.__name__, x) for x in get_subclasses(mns_mod.ModuleNamingScheme)])
        easybuild.tools.module_naming_scheme.AVAIL_MODULE_NAMING_SCHEMES.update(test_mnss)


        ec2mod_map = {
            'GCC-4.6.3': 'GCC/4.6.3',
            'gzip-1.4': 'gzip/1.4',
            'gzip-1.4-GCC-4.6.3': 'gnu/gzip/1.4',
            'gzip-1.5-goolf-1.4.10': 'gnu/openmpi/gzip/1.5',
            'gzip-1.5-ictce-4.1.13': 'intel/intelmpi/gzip/1.5',
            'toy-0.0': 'toy/0.0',
            'toy-0.0-multiple': 'toy/0.0',  # test module naming scheme ignores version suffixes
        }

        # test custom naming scheme
        for ec_file in ec_files:
            ec_path = os.path.abspath(ec_file)
            ec = EasyConfig(ec_path, validate=False, valid_stops=all_stops)
            # derive module name directly from easyconfig file name
            ec_name = '.'.join(ec_file.split(os.path.sep)[-1].split('.')[:-1])  # cut off '.eb' end
            self.assertEqual(ec2mod_map[ec_name], det_full_module_name(ec))

        # generating module name from non-parsed easyconfig does not work (and shouldn't)
        error_msg = "Can not ensure correct module name generation for non-parsed easyconfig specifications."
        self.assertErrorRegex(EasyBuildError, error_msg, det_full_module_name, non_parsed)

        # restore default module naming scheme, and retest
        config.variables['module_naming_scheme'] = orig_module_naming_scheme
        test_default()

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
    main()
