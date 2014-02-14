# #
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
# #
"""
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import tempfile
from unittest import TestCase, TestLoader, main
from vsc import fancylogger

import easybuild.tools.config as config
import easybuild.tools.filetools as ft
from test.framework.utilities import find_full_path


class FileToolsTest(TestCase):
    """ Testcase for filetools module """

    class_names = [
        ('GCC', 'EB_GCC'),
        ('7zip', 'EB_7zip'),
        ('Charm++', 'EB_Charm_plus__plus_'),
        ('DL_POLY_Classic', 'EB_DL_underscore_POLY_underscore_Classic'),
        ('0_foo+0x0x#-$__', 'EB_0_underscore_foo_plus_0x0x_hash__minus__dollar__underscore__underscore_'),
    ]

    def setUp(self):
        self.log = fancylogger.getLogger(self.__class__.__name__)
        self.legacySetUp()

    def legacySetUp(self):
        self.log.deprecated("legacySetUp", "2.0")
        cfg_path = os.path.join('easybuild', 'easybuild_config.py')
        cfg_full_path = find_full_path(cfg_path)
        self.assertTrue(cfg_full_path)

        config.oldstyle_init(cfg_full_path)
        self.cwd = os.getcwd()

    def tearDown(self):
        """cleanup"""
        os.chdir(self.cwd)

    def test_extract_cmd(self):
        """Test various extract commands."""
        tests = [
            ('test.zip', "unzip -qq test.zip"),
            ('/some/path/test.tar', "tar xf /some/path/test.tar"),
            ('test.tar.gz', "tar xzf test.tar.gz"),
            ('test.tgz', "tar xzf test.tgz"),
            ('test.gtgz', "tar xzf test.gtgz"),
            ('test.bz2', "bunzip2 test.bz2"),
            ('test.tbz', "tar xjf test.tbz"),
            ('test.tbz2', "tar xjf test.tbz2"),
            ('test.tb2', "tar xjf test.tb2"),
            ('test.tar.bz2', "tar xjf test.tar.bz2"),
        ]
        for (fn, expected_cmd) in tests:
            cmd = ft.extract_cmd(fn)
            self.assertEqual(expected_cmd, cmd)

    def test_convert_name(self):
        """Test convert_name function."""
        name = ft.convert_name("test+test-test")
        self.assertEqual(name, "testplustestmintest")
        name = ft.convert_name("test+test-test", True)
        self.assertEqual(name, "TESTPLUSTESTMINTEST")

    def test_cwd(self):
        """tests should be run from the base easybuild directory"""
        # used to be part of test_parse_log_error
        self.assertEqual(os.getcwd(), ft.find_base_dir())

    def test_encode_class_name(self):
        """Test encoding of class names."""
        for (class_name, encoded_class_name) in self.class_names:
            self.assertEqual(ft.encode_class_name(class_name), encoded_class_name)
            self.assertEqual(ft.encode_class_name(ft.decode_class_name(encoded_class_name)), encoded_class_name)

    def test_decode_class_name(self):
        """Test decoding of class names."""
        for (class_name, encoded_class_name) in self.class_names:
            self.assertEqual(ft.decode_class_name(encoded_class_name), class_name)
            self.assertEqual(ft.decode_class_name(ft.encode_class_name(class_name)), class_name)

    def test_patch_perl_script_autoflush(self):
        """Test patching Perl script for autoflush."""

        fh, fp = tempfile.mkstemp()
        os.close(fh)
        perl_lines = [
            "$!/usr/bin/perl",
            "use strict;",
            "print hello",
            "",
            "print hello again",
        ]
        perltxt = '\n'.join(perl_lines)
        ft.write_file(fp, perltxt)
        ft.patch_perl_script_autoflush(fp)
        txt = ft.read_file(fp)
        self.assertTrue(len(txt.split('\n')) == len(perl_lines) + 4)
        self.assertTrue(txt.startswith(perl_lines[0] + "\n\nuse IO::Handle qw();\nSTDOUT->autoflush(1);"))
        for line in perl_lines[1:]:
            self.assertTrue(line in txt)
        os.remove(fp)
        os.remove("%s.eb.orig" % fp)

    def test_which(self):
        """Test which function for locating commands."""
        python = ft.which('python')
        self.assertTrue(python and os.path.exists(python) and os.path.isabs(python))

        path = ft.which('i_really_do_not_expect_a_command_with_a_name_like_this_to_be_available')
        self.assertTrue(path is None)


    def test_checksums(self):
        """Test checksum functionality."""
        fh, fp = tempfile.mkstemp()
        os.close(fh)
        ft.write_file(fp, "easybuild\n")
        known_checksums = {
            'adler32': '0x379257805',
            'crc32': '0x1457143216',
            'md5': '7167b64b1ca062b9674ffef46f9325db',
            'sha1': 'db05b79e09a4cc67e9dd30b313b5488813db3190',
        }

        # make sure checksums computation/verification is correct
        for checksum_type, checksum in known_checksums.items():
            self.assertEqual(ft.compute_checksum(fp, checksum_type=checksum_type), checksum)
            self.assertTrue(ft.verify_checksum(fp, (checksum_type, checksum)))
        # md5 is default
        self.assertEqual(ft.compute_checksum(fp), known_checksums['md5'])
        self.assertTrue(ft.verify_checksum(fp, known_checksums['md5']))

        # make sure faulty checksums are reported
        broken_checksums = dict([(typ, val + 'foo') for (typ, val) in known_checksums.items()])
        for checksum_type, checksum in broken_checksums.items():
            self.assertFalse(ft.compute_checksum(fp, checksum_type=checksum_type) == checksum)
            self.assertFalse(ft.verify_checksum(fp, (checksum_type, checksum)))
        # md5 is default
        self.assertFalse(ft.compute_checksum(fp) == broken_checksums['md5'])
        self.assertFalse(ft.verify_checksum(fp, broken_checksums['md5']))

        # cleanup
        os.remove(fp)

    def test_common_path_prefix(self):
        """Test get common path prefix for a list of paths."""
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar/foo', '/foo/bar/baz', '/foo/bar/bar']), '/foo/bar')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar/', '/foo/bar/baz', '/foo/bar']), '/foo/bar')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar', '/foo']), '/foo')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar/']), '/foo/bar')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar', '/bar', '/foo']), None)
        self.assertEqual(ft.det_common_path_prefix(['foo', 'bar']), None)
        self.assertEqual(ft.det_common_path_prefix(['foo']), None)
        self.assertEqual(ft.det_common_path_prefix([]), None)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(FileToolsTest)

if __name__ == '__main__':
    main()
