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
Unit tests for fetch.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import re
import shutil
import tempfile
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main

from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.fetch import det_common_path_prefix, download_file, obtain_file
from easybuild.tools.filetools import mkdir


class FetchTest(EnhancedTestCase):
    """Testcases for fetch module."""

    def test_download_file(self):
        """Test download_file function."""
        fn = 'toy-0.0.tar.gz'
        target_location = os.path.join(self.test_buildpath, 'some', 'subdir', fn)
        # provide local file path as source URL
        test_dir = os.path.abspath(os.path.dirname(__file__))
        source_url = os.path.join('file://', test_dir, 'sandbox', 'sources', 'toy', fn)
        res = download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location)

    def test_common_path_prefix(self):
        """Test get common path prefix for a list of paths."""
        self.assertEqual(det_common_path_prefix(['/foo/bar/foo', '/foo/bar/baz', '/foo/bar/bar']), '/foo/bar')
        self.assertEqual(det_common_path_prefix(['/foo/bar/', '/foo/bar/baz', '/foo/bar']), '/foo/bar')
        self.assertEqual(det_common_path_prefix(['/foo/bar', '/foo']), '/foo')
        self.assertEqual(det_common_path_prefix(['/foo/bar/']), '/foo/bar')
        self.assertEqual(det_common_path_prefix(['/foo/bar', '/bar', '/foo']), None)
        self.assertEqual(det_common_path_prefix(['foo', 'bar']), None)
        self.assertEqual(det_common_path_prefix(['foo']), None)
        self.assertEqual(det_common_path_prefix([]), None)

    def test_obtain_file(self):
        """Test obtain_file method."""
        toy_tarball = 'toy-0.0.tar.gz'
        testdir = os.path.abspath(os.path.dirname(__file__))
        sandbox_sources = os.path.join(testdir, 'sandbox', 'sources')
        toy_tarball_path = os.path.join(sandbox_sources, 'toy', toy_tarball)
        tmpdir = tempfile.mkdtemp()
        tmpdir_subdir = os.path.join(tmpdir, 'testing')
        mkdir(tmpdir_subdir, parents=True)
        del os.environ['EASYBUILD_SOURCEPATH']  # defined by setUp

        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'toy-0.0.eb'))[0]
        eb = EasyBlock(ec['ec'])

        # 'downloading' a file to (first) sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, testdir)])
        shutil.copy2(toy_tarball_path, tmpdir_subdir)
        res = obtain_file(toy_tarball, eb.name, '', eb.cfg['source_urls'], urls=[os.path.join('file://', tmpdir_subdir)])
        self.assertEqual(res, os.path.join(tmpdir, 't', 'toy', toy_tarball))

        # finding a file in sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (sandbox_sources, tmpdir)])
        res = obtain_file(toy_tarball, eb.name, '', eb.cfg['source_urls'])
        self.assertEqual(res, toy_tarball_path)

        # sourcepath has preference over downloading
        res = obtain_file(toy_tarball, eb.name, '', eb.cfg['source_urls'], urls=[os.path.join('file://', tmpdir_subdir)])
        self.assertEqual(res, toy_tarball_path)

        # obtain_file yields error for non-existing files
        fn = 'thisisclearlyanonexistingfile'
        try:
            obtain_file(fn, 'dunno', '', [], urls=[os.path.join('file://', tmpdir_subdir)])
        except EasyBuildError, err:
            fail_regex = re.compile("Couldn't find file %s anywhere, and downloading it didn't work either" % fn)
            self.assertTrue(fail_regex.search(str(err)))

        # file specifications via URL also work, are downloaded to (first) sourcepath
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, sandbox_sources)])
        file_url = "http://hpcugent.github.io/easybuild/index.html"
        fn = os.path.basename(file_url)
        try:
            res = obtain_file(file_url, 'toy', '', [])
            loc = os.path.join(tmpdir, 't', 'toy', fn)
            self.assertEqual(res, loc)
            self.assertTrue(os.path.exists(loc), "%s file is found at %s" % (fn, loc))
            txt = open(loc, 'r').read()
            eb_regex = re.compile("EasyBuild: building software with ease")
            self.assertTrue(eb_regex.search(txt))
        except EasyBuildError, err:
            # if this fails, it should be because there's no online access
            download_fail_regex = re.compile('socket error')
            self.assertTrue(download_fail_regex.search(str(err)))

        shutil.rmtree(tmpdir)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(FetchTest)

if __name__ == '__main__':
    main()
