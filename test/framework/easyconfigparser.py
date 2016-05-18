# #
# Copyright 2013-2016 Ghent University
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
Unit tests for easyconfig/parser.py

@author: Stijn De Weirdt (Ghent University)
"""
import os
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

import easybuild.tools.build_log
from easybuild.framework.easyconfig.format.format import Dependency
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_constants_dict
from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file


TESTDIRBASE = os.path.join(os.path.dirname(__file__), 'easyconfigs')


class EasyConfigParserTest(EnhancedTestCase):
    """Test the parser"""

    def test_v10(self):
        ecp = EasyConfigParser(os.path.join(TESTDIRBASE, 'v1.0', 'GCC-4.6.3.eb'))

        self.assertEqual(ecp._formatter.VERSION, EasyVersion('1.0'))

        ec = ecp.get_config_dict()

        self.assertEqual(ec['toolchain'], {'name': 'dummy', 'version': 'dummy'})
        self.assertEqual(ec['name'], 'GCC')
        self.assertEqual(ec['version'], '4.6.3')

    def test_v20(self):
        """Test parsing of easyconfig in format v2."""
        # hard enable experimental
        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

        fn = os.path.join(TESTDIRBASE, 'v2.0', 'GCC.eb')
        ecp = EasyConfigParser(fn)

        formatter = ecp._formatter
        self.assertEqual(formatter.VERSION, EasyVersion('2.0'))

        self.assertTrue('name' in formatter.pyheader_localvars)
        self.assertFalse('version' in formatter.pyheader_localvars)
        self.assertFalse('toolchain' in formatter.pyheader_localvars)

        # this should be ok: ie the default values
        ec = ecp.get_config_dict()
        self.assertEqual(ec['toolchain'], {'name': 'dummy', 'version': 'dummy'})
        self.assertEqual(ec['name'], 'GCC')
        self.assertEqual(ec['version'], '4.6.2')

        # restore
        easybuild.tools.build_log.EXPERIMENTAL = orig_experimental

    def test_v20_extra(self):
        """Test parsing of easyconfig in format v2."""
        # hard enable experimental
        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

        fn = os.path.join(TESTDIRBASE, 'v2.0', 'doesnotexist.eb')
        ecp = EasyConfigParser(fn)

        formatter = ecp._formatter
        self.assertEqual(formatter.VERSION, EasyVersion('2.0'))

        self.assertTrue('name' in formatter.pyheader_localvars)
        self.assertFalse('version' in formatter.pyheader_localvars)
        self.assertFalse('toolchain' in formatter.pyheader_localvars)

        # restore
        easybuild.tools.build_log.EXPERIMENTAL = orig_experimental

    def test_v20_deps(self):
        """Test parsing of easyconfig in format v2 that includes dependencies."""
        # hard enable experimental
        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

        fn = os.path.join(TESTDIRBASE, 'v2.0', 'libpng.eb')
        ecp = EasyConfigParser(fn)

        ec = ecp.get_config_dict()
        self.assertEqual(ec['name'], 'libpng')
        # first version/toolchain listed is default
        self.assertEqual(ec['version'], '1.5.10')
        self.assertEqual(ec['toolchain'], {'name': 'goolf', 'version': '1.4.10'})

        # dependencies should be parsed correctly
        deps = ec['dependencies']
        self.assertTrue(isinstance(deps[0], Dependency))
        self.assertEqual(deps[0].name(), 'zlib')
        self.assertEqual(deps[0].version(), '1.2.5')

        fn = os.path.join(TESTDIRBASE, 'v2.0', 'goolf.eb')
        ecp = EasyConfigParser(fn)

        ec = ecp.get_config_dict()
        self.assertEqual(ec['name'], 'goolf')
        self.assertEqual(ec['version'], '1.4.10')
        self.assertEqual(ec['toolchain'], {'name': 'dummy', 'version': 'dummy'})

        # dependencies should be parsed correctly
        deps = [
            # name, version, versionsuffix, toolchain
            ('GCC', '4.7.2', None, None),
            ('OpenMPI', '1.6.4', None, {'name': 'GCC', 'version': '4.7.2'}),
            ('OpenBLAS', '0.2.6', '-LAPACK-3.4.2', {'name': 'gompi', 'version': '1.4.10'}),
            ('FFTW', '3.3.3', None, {'name': 'gompi', 'version': '1.4.10'}),
            ('ScaLAPACK', '2.0.2', '-OpenBLAS-0.2.6-LAPACK-3.4.2', {'name': 'gompi', 'version': '1.4.10'}),
        ]
        for i, (name, version, versionsuffix, toolchain) in enumerate(deps):
            self.assertEqual(ec['dependencies'][i].name(), name)
            self.assertEqual(ec['dependencies'][i].version(), version)
            self.assertEqual(ec['dependencies'][i].versionsuffix(), versionsuffix)
            self.assertEqual(ec['dependencies'][i].toolchain(), toolchain)

        # restore
        easybuild.tools.build_log.EXPERIMENTAL = orig_experimental

    def test_raw(self):
        """Test passing of raw contents to EasyConfigParser."""
        ec_file1 = os.path.join(TESTDIRBASE, 'v1.0', 'GCC-4.6.3.eb')
        ec_txt1 = read_file(ec_file1)
        ec_file2 = os.path.join(TESTDIRBASE, 'v1.0', 'gzip-1.5-goolf-1.4.10.eb')
        ec_txt2 = read_file(ec_file2)

        ecparser = EasyConfigParser(ec_file1)
        self.assertEqual(ecparser.rawcontent, ec_txt1)

        ecparser = EasyConfigParser(rawcontent=ec_txt2)
        self.assertEqual(ecparser.rawcontent, ec_txt2)

        # rawcontent supersedes passed filepath
        ecparser = EasyConfigParser(ec_file1, rawcontent=ec_txt2)
        self.assertEqual(ecparser.rawcontent, ec_txt2)
        ec = ecparser.get_config_dict()
        self.assertEqual(ec['name'], 'gzip')
        self.assertEqual(ec['toolchain']['name'], 'goolf')

        self.assertErrorRegex(EasyBuildError, "Neither filename nor rawcontent provided", EasyConfigParser)

    def test_easyconfig_constants(self):
        """Test available easyconfig constants."""
        constants = build_easyconfig_constants_dict()
        # make sure both keys and values are only strings
        for constant_name in constants:
            self.assertTrue(isinstance(constant_name, basestring), "Constant name %s is a string" % constant_name)
            val = constants[constant_name]
            self.assertTrue(isinstance(val, basestring), "Constant value %s is a string" % val)

        # check a couple of randomly picked constant values
        self.assertEqual(constants['SOURCE_TAR_GZ'], '%(name)s-%(version)s.tar.gz')
        self.assertEqual(constants['PYPI_SOURCE'], 'https://pypi.python.org/packages/source/%(nameletter)s/%(name)s')
        self.assertEqual(constants['GPLv2'], 'LicenseGPLv2')
        self.assertEqual(constants['EXTERNAL_MODULE'], 'EXTERNAL_MODULE')

    def test_check_value_types(self):
        """Test checking of easyconfig parameter value types."""
        test_ec = os.path.join(TESTDIRBASE, 'gzip-1.4-broken.eb')
        error_msg_pattern = "Type checking of easyconfig parameter values failed: .*'version'.*"
        ecp = EasyConfigParser(test_ec, auto_convert_value_types=False)
        self.assertErrorRegex(EasyBuildError, error_msg_pattern, ecp.get_config_dict)

        # test default behaviour: auto-converting of mismatched value types
        ecp = EasyConfigParser(test_ec)
        ecdict = ecp.get_config_dict()
        self.assertEqual(ecdict['version'], '1.4')


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigParserTest)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
