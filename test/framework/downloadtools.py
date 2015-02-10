##
# Copyright 2015 Ghent University
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
Unit tests for downloadtools.py
@author: Kenneth Hoste (Ghent University)
@author: Jens Timmerman (Ghent University)
"""
import os
import urllib2

from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

import easybuild.tools.downloadtools as dt


class DownloadToolsTest(EnhancedTestCase):
    """ Testcase for downloadtools module """

    def test_download_file(self):
        """Test download_file function."""
        fn = 'toy-0.0.tar.gz'
        target_location = os.path.join(self.test_buildpath, 'some', 'subdir', fn)
        # provide local file path as source URL
        test_dir = os.path.abspath(os.path.dirname(__file__))
        source_url = 'file://%s/sandbox/sources/toy/%s' % (test_dir, fn)
        res = dt.download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location, "'download' of local file works")

        # non-existing files result in None return value
        self.assertEqual(dt.download_file(fn, 'file://%s/nosuchfile' % test_dir, target_location), None)

        # install broken proxy handler for opening local files
        # this should make urllib2.urlopen use this broken proxy for downloading from a file:// URL
        proxy_handler = urllib2.ProxyHandler({'https': 'http://%s/nosuchfile' % test_dir})
        urllib2.install_opener(urllib2.build_opener(proxy_handler))

        # downloading over a broken proxy results in None return value (failed download)
        # this tests whether proxies are taken into account by download_file
        fn = "robots.txt"
        source_url = "https://jenkins1.ugent.be/"
        target_location = os.path.join(self.test_buildpath, 'some', 'subdir', fn)
        self.assertEqual(dt.download_file(fn, source_url, target_location), None, "download over broken proxy fails")

        # restore a working file handler, and retest download of local file
        urllib2.install_opener(urllib2.build_opener(urllib2.FileHandler()))
        res = dt.download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location, "'download' of local file works after removing broken proxy")


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(DownloadToolsTest)

if __name__ == '__main__':
    main()
