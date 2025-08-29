# #
# Copyright 2013-2025 Ghent University
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
import re
import sys
import tempfile
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
        super().setUp()
        self.orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        # easystack files are an experimental feature
        easybuild.tools.build_log.EXPERIMENTAL = True

    def tearDown(self):
        """Clean up after test."""
        easybuild.tools.build_log.EXPERIMENTAL = self.orig_experimental
        super().tearDown()

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

    def test_easystack_restore_env_after_each_build(self):
        """Test that the build environment and tmpdir is reset for each easystack item"""

        orig_tmpdir_tempfile = tempfile.gettempdir()
        orig_tmpdir_env = os.getenv('TMPDIR')
        orig_tmpdir_tempfile_len = len(orig_tmpdir_env.split(os.path.sep))
        orig_tmpdir_env_len = len(orig_tmpdir_env.split(os.path.sep))

        test_es_txt = '\n'.join([
            "easyconfigs:",
            "  - toy-0.0-gompi-2018a.eb:",
            "  - libtoy-0.0.eb:",
            # also include a couple of easyconfigs for which a module is already available in test environment,
            # see test/framework/modules
            "  - GCC-7.3.0-2.30",
            "  - FFTW-3.3.7-gompi-2018a",
            "  - foss-2018a",
        ])
        test_es_path = os.path.join(self.test_prefix, 'test.yml')
        write_file(test_es_path, test_es_txt)

        args = [
            '--experimental',
            '--easystack',
            test_es_path
        ]
        self.mock_stdout(True)
        stdout = self.eb_main(args, do_build=True, raise_error=True)
        stdout = self.eb_main(args, do_build=True, raise_error=True, reset_env=False, redo_init_config=False)
        self.mock_stdout(False)
        regex = re.compile(r"WARNING Loaded modules detected: \[.*gompi/2018.*\]\n")
        self.assertFalse(regex.search(stdout), "Pattern '%s' should not be found in: %s" % (regex.pattern, stdout))

        # temporary directory after run should be exactly 2 levels deeper than original one:
        # - 1 level added by setting up configuration in EasyBuild main function
        # - 1 extra level added by first re-configuration for easystack item
        #   (because $TMPDIR set by configuration done in main function is retained)
        tmpdir_tempfile = tempfile.gettempdir()
        tmpdir_env = os.getenv('TMPDIR')
        tmpdir_tempfile_len = len(tmpdir_tempfile.split(os.path.sep))
        tmpdir_env_len = len(tmpdir_env.split(os.path.sep))

        self.assertEqual(tmpdir_tempfile_len, orig_tmpdir_tempfile_len + 2)
        self.assertEqual(tmpdir_env_len, orig_tmpdir_env_len + 2)
        self.assertTrue(tmpdir_tempfile.startswith(orig_tmpdir_tempfile))
        self.assertTrue(tmpdir_env.startswith(orig_tmpdir_env))

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


def suite(loader=None):
    """ returns all the testcases in this module """
    if loader:
        return loader.loadTestsFromTestCase(EasyStackTest)
    else:
        return TestLoaderFiltered().loadTestsFromTestCase(EasyStackTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
