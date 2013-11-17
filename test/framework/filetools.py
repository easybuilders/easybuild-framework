# #
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

    def test_run_cmd(self):
        """Basic test for run_cmd function."""
        (out, ec) = ft.run_cmd("echo hello")
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

    def test_run_cmd_bis(self):
        """More 'complex' test for run_cmd function."""
        # a more 'complex' command to run, make sure all required output is there
        (out, ec) = ft.run_cmd("for j in `seq 1 3`; do for i in `seq 1 100`; do echo hello; done; sleep 1.4; done")
        self.assertTrue(out.startswith('hello\nhello\n'))
        self.assertEqual(len(out), len("hello\n"*300))
        self.assertEqual(ec, 0)

    def test_run_cmd_qa(self):
        """Basic test for run_cmd_qa function."""
        (out, ec) = ft.run_cmd_qa("echo question; read x; echo $x", {"question": "answer"})
        self.assertEqual(out, "question\nanswer\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

    def test_run_cmd_simple(self):
        """Test return value for run_cmd in 'simple' mode."""
        self.assertEqual(True, ft.run_cmd("echo hello", simple=True))
        self.assertEqual(False, ft.run_cmd("exit 1", simple=True, log_all=False, log_ok=False))

    def test_convert_name(self):
        """Test convert_name function."""
        name = ft.convert_name("test+test-test")
        self.assertEqual(name, "testplustestmintest")
        name = ft.convert_name("test+test-test", True)
        self.assertEqual(name, "TESTPLUSTESTMINTEST")

    def test_parse_log_error(self):
        """Test basic parse_log_for_error functionality."""
        errors = ft.parse_log_for_error("error failed", True)
        self.assertEqual(len(errors), 1)

        # I expect tests to be run from the base easybuild directory
        self.assertEqual(os.getcwd(), ft.find_base_dir())

    def test_run_cmd_suse(self):
        """Test run_cmd on SuSE systems, which have $PROFILEREAD set."""
        # avoid warning messages
        ft_log_level = ft._log.getEffectiveLevel()
        ft._log.setLevel('ERROR')

        # run_cmd should also work if $PROFILEREAD is set (very relevant for SuSE systems)
        profileread = os.environ.get('PROFILEREAD', None)
        os.environ['PROFILEREAD'] = 'profilereadxxx'
        try:
            (out, ec) = ft.run_cmd("echo hello")
        except Exception, err:
            out, ec = "ERROR: %s" % err, 1

        # make sure it's restored again before we can fail the test
        if profileread is not None:
            os.environ['PROFILEREAD'] = profileread
        else:
            del os.environ['PROFILEREAD']

        self.assertEqual(out, "hello\n")
        self.assertEqual(ec, 0)
        ft._log.setLevel(ft_log_level)

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
        self.assertTrue(len(txt.split('\n')) == len(perl_lines)+4)
        self.assertTrue(txt.startswith(perl_lines[0]+"\n\nuse IO::Handle qw();\nSTDOUT->autoflush(1);"))
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


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(FileToolsTest)

if __name__ == '__main__':
    main()
