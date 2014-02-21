##
# Copyright 2014 Ghent University
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
Unit tests for extract.py

@author: Jens Timmerman (Ghent University)
"""
import os
import tempfile
import shutil
from unittest import TestCase, TestLoader, main

import easybuild.tools.extract as ex
from vsc.utils import fancylogger


class ExtractTest(TestCase):
    """ Testcase for filetools module """

    def setUp(self):
        self.cwd = os.getcwd()
        self.log = fancylogger.getLogger()
        self.tmpdir = tempfile.mkdtemp()

        # go to the data subdir to find all archives
        abspath = os.path.abspath(__file__)
        dname = os.path.dirname(abspath)
        dname = os.path.join(dname, 'data')
        os.chdir(dname)

    def tearDown(self):
        """cleanup"""
        shutil.rmtree(self.tmpdir)
        os.chdir(self.cwd)

    def test_extract_tar(self):
        """Test the extraction of a tar file"""
        out = ex.extract_archive('test.tar', self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extract_gziped_tar(self):
        """Test the extraction of a gzipped tar file"""
        out = ex.extract_archive('test.tar.gz', self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)
        out = ex.extract_archive('test.tgz', self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extracted_bzipped_tar(self):
        """Test the extraction of a bzipped tar file"""
        out = ex.extract_archive('test.tar.bz2', self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')
        os.remove(out_file)
        out = ex.extract_archive('test.tbz', self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extract_zip(self):
        """Test the extraction of a zip file"""
        out = ex.extract_archive('test.zip', self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extract_bzip2(self):
        """Test the extraction of a bzip2 file"""
        out_file = ex.extract_archive('test.txt.bz2', self.tmpdir)
        self.assertEqual(out_file, os.path.join(self.tmpdir, 'test.txt'))
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extract_gzip(self):
        """Test the extraction of a gzip file"""
        out_file = ex.extract_archive('test.txt.gz', self.tmpdir)
        self.assertEqual(out_file, os.path.join(self.tmpdir, 'test.txt'))
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extract_xzed_tar(self):
        """Test the extraction of a xz'ed tarfile"""
        out = ex.extract_archive('test.tar.xz', self.tmpdir)
        self.assertEqual(out, self.tmpdir)
        out_file = os.path.join(out, 'test.txt')
        self.assertEqual(open(out_file).read(), 'test ok\n')

    def test_extract_xz(self):
        """Test the extraction of a xz'ed file"""
        out = ex.extract_archive('test.txt.xz', self.tmpdir)
        self.assertEqual(out, os.path.join(self.tmpdir, 'test.txt'))
        self.assertEqual(open(out).read(), 'test ok\n')

#TODO: deb, rpm, iso


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ExtractTest)

if __name__ == '__main__':
    main()
