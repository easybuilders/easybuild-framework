# #
# Copyright 2013-2021 Ghent University
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

    def test_parse_fail(self):
        """Test for clean error when easystack file fails to parse."""
        test_yml = os.path.join(self.test_prefix, 'test.yml')
        write_file(test_yml, 'software: %s')
        error_pattern = "Failed to parse .*/test.yml: while scanning for the next token"
        self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_yml)

    def test_easystack_wrong_structure(self):
        """Test for --easystack <easystack.yaml> when yaml easystack has wrong structure"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_wrong_structure.yaml')

        expected_err = r"[\S\s]*An error occurred when interpreting the data for software Bioconductor:"
        expected_err += r"( 'float' object is not subscriptable[\S\s]*"
        expected_err += r"| 'float' object is unsubscriptable"
        expected_err += r"| 'float' object has no attribute '__getitem__'[\S\s]*)"
        self.assertErrorRegex(EasyBuildError, expected_err, parse_easystack, test_easystack)

    def test_easystack_asterisk(self):
        """Test for --easystack <easystack.yaml> when yaml easystack contains asterisk (wildcard)"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_asterisk.yaml')

        expected_err = "EasyStack specifications of 'binutils' in .*/test_easystack_asterisk.yaml contain asterisk. "
        expected_err += "Wildcard feature is not supported yet."

        self.assertErrorRegex(EasyBuildError, expected_err, parse_easystack, test_easystack)

    def test_easystack_labels(self):
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_labels.yaml')

        error_msg = "EasyStack specifications of 'binutils' in .*/test_easystack_labels.yaml contain labels. "
        error_msg += "Labels aren't supported yet."
        self.assertErrorRegex(EasyBuildError, error_msg, parse_easystack, test_easystack)

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

    def test_easystack_versions(self):
        """Test handling of versions in easystack files."""

        test_easystack = os.path.join(self.test_prefix, 'test.yml')
        tmpl_easystack_txt = '\n'.join([
            "software:",
            "  foo:",
            "    toolchains:",
            "       SYSTEM:",
            "           versions:",
        ])

        # normal versions, which are not treated special by YAML: no single quotes needed
        versions = ('1.2.3', '1.2.30', '2021a', '1.2.3')
        for version in versions:
            write_file(test_easystack, tmpl_easystack_txt + ' ' + version)
            ec_fns, _ = parse_easystack(test_easystack)
            self.assertEqual(ec_fns, ['foo-%s.eb' % version])

        # multiple versions as a list
        test_easystack_txt = tmpl_easystack_txt + " [1.2.3, 3.2.1]"
        write_file(test_easystack, test_easystack_txt)
        ec_fns, _ = parse_easystack(test_easystack)
        expected = ['foo-1.2.3.eb', 'foo-3.2.1.eb']
        self.assertEqual(sorted(ec_fns), sorted(expected))

        # multiple versions listed with more info
        test_easystack_txt = '\n'.join([
            tmpl_easystack_txt,
            "             1.2.3:",
            "             2021a:",
            "             3.2.1:",
            "                 versionsuffix: -foo",
        ])
        write_file(test_easystack, test_easystack_txt)
        ec_fns, _ = parse_easystack(test_easystack)
        expected = ['foo-1.2.3.eb', 'foo-2021a.eb', 'foo-3.2.1-foo.eb']
        self.assertEqual(sorted(ec_fns), sorted(expected))

        # versions that get interpreted by YAML as float or int, single quotes required
        for version in ('1.2', '123', '3.50', '100', '2.44_01'):
            error_pattern = r"Value .* \(of type .*\) obtained for foo \(with system toolchain\) is not valid\!"

            write_file(test_easystack, tmpl_easystack_txt + ' ' + version)
            self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

            # all is fine when wrapping the value in single quotes
            write_file(test_easystack, tmpl_easystack_txt + " '" + version + "'")
            ec_fns, _ = parse_easystack(test_easystack)
            self.assertEqual(ec_fns, ['foo-%s.eb' % version])

            # one rotten apple in the basket is enough
            test_easystack_txt = tmpl_easystack_txt + " [1.2.3, %s, 3.2.1]" % version
            write_file(test_easystack, test_easystack_txt)
            self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

            test_easystack_txt = '\n'.join([
                tmpl_easystack_txt,
                "             1.2.3:",
                "             %s:" % version,
                "             3.2.1:",
                "                 versionsuffix: -foo",
            ])
            write_file(test_easystack, test_easystack_txt)
            self.assertErrorRegex(EasyBuildError, error_pattern, parse_easystack, test_easystack)

            # single quotes to the rescue!
            test_easystack_txt = '\n'.join([
                tmpl_easystack_txt,
                "             1.2.3:",
                "             '%s':" % version,
                "             3.2.1:",
                "                 versionsuffix: -foo",
            ])
            write_file(test_easystack, test_easystack_txt)
            ec_fns, _ = parse_easystack(test_easystack)
            expected = ['foo-1.2.3.eb', 'foo-%s.eb' % version, 'foo-3.2.1-foo.eb']
            self.assertEqual(sorted(ec_fns), sorted(expected))

        # also check toolchain version that could be interpreted as a non-string value...
        test_easystack_txt = '\n'.join([
            'software:',
            '  test:',
            '    toolchains:',
            '      intel-2021.03:',
            "        versions: [1.2.3, '2.3']",
        ])
        write_file(test_easystack, test_easystack_txt)
        ec_fns, _ = parse_easystack(test_easystack)
        expected = ['test-1.2.3-intel-2021.03.eb', 'test-2.3-intel-2021.03.eb']
        self.assertEqual(sorted(ec_fns), sorted(expected))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyStackTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
