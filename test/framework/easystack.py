# #
# Copyright 2013-2022 Ghent University
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
Unit tests for easystack files

@author: Denis Kristak (Inuits)
@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
from unittest import TextTestRunner

import easybuild.tools.build_log
from easybuild.framework.easystack import check_value, parse_easystack
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import write_file
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered


class EasyStackTest(EnhancedTestCase):
    """Testcases for easystack files."""

    logfile = None

    def setUp(self):
        """Set up test."""
        super(EasyStackTest, self).setUp()
        self.orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        # easystack files are an experimental feature
        easybuild.tools.build_log.EXPERIMENTAL = True

    def tearDown(self):
        """Clean up after test."""
        easybuild.tools.build_log.EXPERIMENTAL = self.orig_experimental
        super(EasyStackTest, self).tearDown()

    def test_easystack_basic(self):
        """Test for basic easystack files."""
        topdir = os.path.dirname(os.path.abspath(__file__))

        test_easystacks = [
            'test_easystack_basic.yaml',
            'test_easystack_basic_dict.yaml',
            'test_easystack_easyconfigs_with_eb_ext.yaml',
        ]
        for fn in test_easystacks:
            test_easystack = os.path.join(topdir, 'easystacks', fn)

            easystack = parse_easystack(test_easystack)
            expected = [
                'binutils-2.25-GCCcore-4.9.3.eb',
                'binutils-2.26-GCCcore-4.9.3.eb',
                'foss-2018a.eb',
                'toy-0.0-gompi-2018a-test.eb',
            ]
            self.assertEqual(sorted([x[0] for x in easystack.ec_opt_tuples]), sorted(expected))
            self.assertTrue(all(x[1] is None for x in easystack.ec_opt_tuples))

    def test_easystack_easyconfigs_dict(self):
        """Test for easystack file where easyconfigs item is parsed as a dict, because easyconfig names are not
        prefixed by dashes"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_easyconfigs_dict.yaml')

        error_pattern = r"Found dict value for 'easyconfigs' in .* should be list.\nMake sure you use '-' to create .*"
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

    def test_easystack_easyconfigs_str(self):
        """Test for easystack file where easyconfigs item is parsed as a dict, because easyconfig names are not
        prefixed by dashes"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_easyconfigs_str.yaml')

        error_pattern = r"Found str value for 'easyconfigs' in .* should be list.\nMake sure you use '-' to create .*"
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

    def test_easystack_easyconfig_opts(self):
        """Test an easystack file using the 'easyconfigs' key, with additonal options for some easyconfigs"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_easyconfigs_opts.yaml')

        easystack = parse_easystack(test_easystack)
        expected_tuples = [
            ('binutils-2.25-GCCcore-4.9.3.eb', {'debug': True, 'from-pr': 12345}),
            ('binutils-2.26-GCCcore-4.9.3.eb', None),
            ('foss-2018a.eb', {'enforce-checksums': True, 'robot': True}),
            ('toy-0.0-gompi-2018a-test.eb', None),
        ]
        self.assertEqual(easystack.ec_opt_tuples, expected_tuples)

    def test_easystack_invalid_key(self):
        """Test easystack files with invalid key at the same level as the 'options' key"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_invalid_key.yaml')

        error_pattern = r"Found one or more invalid keys for .* \(only 'options' supported\).*"
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

    def test_easystack_invalid_key2(self):
        """Test easystack files with invalid key at the same level as the key that names the easyconfig"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_invalid_key2.yaml')

        error_pattern = r"expected a dictionary with one key \(the EasyConfig name\), "
        error_pattern += r"instead found keys: .*, invalid_key"
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

    def test_missing_easyconfigs_key(self):
        """Test that EasyStack file that doesn't contain an EasyConfigs key will fail with sane error message"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_missing_easyconfigs_key.yaml')

        error_pattern = r"Top-level key 'easyconfigs' missing in easystack file %s" % test_easystack
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

    def test_parse_fail(self):
        """Test for clean error when easystack file fails to parse."""
        test_yml = os.path.join(self.test_prefix, 'test.yml')
        write_file(test_yml, 'easyconfigs: %s')
        error_pattern = "Failed to parse .*/test.yml: while scanning for the next token"
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_yml)

    def test_check_value(self):
        """Test check_value function."""
        check_value('1.2.3', None)
        check_value('1.2', None)
        check_value('3.50', None)
        check_value('100', None)

        context = "<some context>"
        for version in (1.2, 100, None):
            error_pattern = r"Value .* \(of type .*\) obtained for <some context> is not valid!"
            self.assertErrorRegex(EasyBuildError, error_pattern, check_value, version, context)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyStackTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
