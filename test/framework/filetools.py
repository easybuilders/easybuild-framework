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
from unittest import TestCase, TestLoader, main
from vsc import fancylogger

import easybuild.tools.config as config
import easybuild.tools.filetools as ft
from easybuild.test.utilities import find_full_path


class FileToolsTest(TestCase):
    """ Testcase for filetools module """

    def setUp(self):
        self.log = fancylogger.getLogger(self.__class__.__name__)
        self.legacySetUp()

        # go to the data subdir to find all archives
        abspath = os.path.abspath(__file__)
        dname = os.path.dirname(abspath)
        dname = os.path.join(dname, 'data')
        os.chdir(dname)

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

    def runTest(self):
        """
        verify all the possible extract commands
        also run_cmd should work with some basic echo/exit combos
        """

        (out, ec) = ft.run_cmd("echo hello")
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

        (out, ec) = ft.run_cmd_qa("echo question", {"question": "answer"})
        self.assertEqual(out, "question\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

        self.assertEqual(True, ft.run_cmd("echo hello", simple=True))
        self.assertEqual(False, ft.run_cmd("exit 1", simple=True, log_all=False, log_ok=False))

        name = ft.convert_name("test+test-test")
        self.assertEqual(name, "testplustestmintest")
        name = ft.convert_name("test+test-test", True)
        self.assertEqual(name, "TESTPLUSTESTMINTEST")

        errors = ft.parse_log_for_error("error failed", True)
        self.assertEqual(len(errors), 1)

        # I expect tests to be run from the base easybuild directory
        self.assertEqual(os.getcwd(), ft.find_base_dir())

    def test_extract_tar(self):
        """Test the extraction of a tar file"""
        out = ft.extract_archive('test.tar', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)

    def test_extract_gziped_tar(self):
        """Test the extraction of a gzipped tar file"""
        out = ft.extract_archive('test.tar.gz', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)
        out = ft.extract_archive('test.tgz', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)

    def test_extracted_bzipped_tar(self):
        """Test the extraction of a bzipped tar file"""
        out = ft.extract_archive('test.tar.bz2', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)
        out = ft.extract_archive('test.tbz', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)


    def test_extract_zip(self):
        """Test the extraction of a zip file"""
        out = ft.extract_archive('test.zip', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)

    def test_extract_bzip2(self):
        """Test the extraction of a bzip2 file"""
        out = ft.extract_archive('test.txt.bz2', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)

    def test_extract_gzip(self):
        """Test the extraction of a gzip file"""
        out = ft.extract_archive('test.txt.gz', '.')
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)

#TODO: xz


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(FileToolsTest)

if __name__ == '__main__':
    main()
