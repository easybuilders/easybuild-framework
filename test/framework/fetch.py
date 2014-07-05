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
import shutil
import stat
import tempfile
from test.framework.utilities import EnhancedTestCase, find_full_path
from unittest import TestLoader, main

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.fetch import det_common_path_prefix, download_file


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

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(FetchTest)

if __name__ == '__main__':
    main()
