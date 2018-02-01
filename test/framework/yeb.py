# #
# Copyright 2015-2018 Ghent University
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
Unit tests for .yeb easyconfig format

@author: Caroline De Brouwer (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.build_log
from easybuild.framework.easyconfig.easyconfig import ActiveMNS, EasyConfig
from easybuild.framework.easyconfig.format.yeb import is_yeb_format
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.filetools import read_file, write_file


try:
    import yaml
except ImportError:
    pass


class YebTest(EnhancedTestCase):
    """ Testcase for run module """

    def setUp(self):
        """Test setup."""
        super(YebTest, self).setUp()
        self.orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

    def tearDown(self):
        """Test cleanup."""
        super(YebTest, self).tearDown()
        easybuild.tools.build_log.EXPERIMENTAL = self.orig_experimental

    def test_parse_yeb(self):
        """Test parsing of .yeb easyconfigs."""
        if 'yaml' not in sys.modules:
            print "Skipping test_parse_yeb (no PyYAML available)"
            return

        build_options = {
            'check_osdeps': False,
            'external_modules_metadata': {},
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        easybuild.tools.build_log.EXPERIMENTAL = True

        testdir = os.path.dirname(os.path.abspath(__file__))
        test_easyconfigs = os.path.join(testdir, 'easyconfigs')
        test_yeb_easyconfigs = os.path.join(testdir, 'easyconfigs', 'yeb')

        # test parsing
        test_files = [
            'bzip2-1.0.6-GCC-4.9.2',
            'gzip-1.6-GCC-4.9.2',
            'goolf-1.4.10',
            'ictce-4.1.13',
            'SQLite-3.8.10.2-goolf-1.4.10',
            'Python-2.7.10-ictce-4.1.13',
            'CrayCCE-5.1.29',
            'toy-0.0',
        ]

        for filename in test_files:
            ec_yeb = EasyConfig(os.path.join(test_yeb_easyconfigs, '%s.yeb' % filename))
            # compare with parsed result of .eb easyconfig
            ec_file = glob.glob(os.path.join(test_easyconfigs, 'test_ecs', '*', '*', '%s.eb' % filename))[0]
            ec_eb = EasyConfig(ec_file)

            no_match = False
            for key in sorted(ec_yeb.asdict()):
                eb_val = ec_eb[key]
                yeb_val = ec_yeb[key]
                if key == 'description':
                    # multi-line string is always terminated with '\n' in YAML, so strip it off
                    yeb_val = yeb_val.strip()

                self.assertEqual(yeb_val, eb_val)

    def test_is_yeb_format(self):
        """ Test is_yeb_format function """
        testdir = os.path.dirname(os.path.abspath(__file__))
        test_yeb = os.path.join(testdir, 'easyconfigs', 'yeb', 'bzip2-1.0.6-GCC-4.9.2.yeb')
        raw_yeb = read_file(test_yeb)

        self.assertTrue(is_yeb_format(test_yeb, None))
        self.assertTrue(is_yeb_format(None, raw_yeb))

        test_eb = os.path.join(testdir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb')
        raw_eb = read_file(test_eb)

        self.assertFalse(is_yeb_format(test_eb, None))
        self.assertFalse(is_yeb_format(None, raw_eb))


    def test_join(self):
        """ Test yaml_join function """
        # skip test if yaml module was not loaded
        if 'yaml' not in sys.modules:
            print "Skipping test_join (no PyYAML available)"
            return

        stream = [
            "variables:",
            "   - &f foo",
            "   - &b bar",
            "",
            "fb1: !join [foo, bar]",
            "fb2: !join [*f, bar]",
            "fb3: !join [*f, *b]",
        ]

        # import here for testing yaml_join separately
        from easybuild.framework.easyconfig.format.yeb import yaml_join
        loaded = yaml.load('\n'.join(stream))
        for key in ['fb1', 'fb2', 'fb3']:
            self.assertEqual(loaded.get(key), 'foobar')


    def test_bad_toolchain_format(self):
        """ Test alternate toolchain format name,version """
        if 'yaml' not in sys.modules:
            print "Skipping test_parse_yeb (no PyYAML available)"
            return

        # only test bad cases - the right ones are tested with the test files in test_parse_yeb
        testdir = os.path.dirname(os.path.abspath(__file__))
        test_easyconfigs = os.path.join(testdir, 'easyconfigs', 'yeb')
        expected = r'Can not convert list .* to toolchain dict. Expected 2 or 3 elements'
        self.assertErrorRegex(EasyBuildError, expected, EasyConfig, os.path.join(test_easyconfigs, 'bzip-bad-toolchain.yeb'))

    def test_external_module_toolchain(self):
        """Test specifying external (build) dependencies in yaml format."""
        if 'yaml' not in sys.modules:
            print "Skipping test_external_module_toolchain (no PyYAML available)"
            return

        ecpath = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'yeb', 'CrayCCE-5.1.29.yeb')
        metadata = {
            'name': ['foo', 'bar'],
            'version': ['1.2.3', '3.2.1'],
            'prefix': '/foo/bar',
        }
        build_options = {
            'external_modules_metadata': {'fftw/3.3.4.0': metadata},
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        easybuild.tools.build_log.EXPERIMENTAL = True

        ec = EasyConfig(ecpath)

        self.assertEqual(ec.dependencies()[1]['full_mod_name'], 'fftw/3.3.4.0')
        self.assertEqual(ec.dependencies()[1]['external_module_metadata'], metadata)

def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(YebTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
