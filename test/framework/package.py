# #
# Copyright 2015-2015 Ghent University
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
Unit tests for packaging support.

@author: Kenneth Hoste (Ghent University)
"""
import os
import stat

from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader
from unittest import main as unittestmain

import easybuild.tools.build_log
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import adjust_permissions, write_file
from easybuild.tools.package.utilities import avail_package_naming_schemes, check_pkg_support


class PackageTest(EnhancedTestCase):
    """Tests for packaging support."""

    def test_avail_package_naming_schemes(self):
        """Test avail_package_naming_schemes()"""
        self.assertEqual(sorted(avail_package_naming_schemes().keys()), ['EasyBuildPNS'])

    def test_check_pkg_support(self):
        """Test check_pkg_support()."""
        # hard enable experimental
        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

        # clear $PATH to make sure fpm/rpmbuild can not be found
        os.environ['PATH'] = ''

        self.assertErrorRegex(EasyBuildError, "Need both fpm and rpmbuild", check_pkg_support)

        for binary in ['fpm', 'rpmbuild']:
            binpath = os.path.join(self.test_prefix, binary)
            write_file(binpath, '#!/bin/bash')
            adjust_permissions(binpath, stat.S_IXUSR, add=True)
        os.environ['PATH'] = self.test_prefix

        check_pkg_support()

        # restore
        easybuild.tools.build_log.EXPERIMENTAL = orig_experimental


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(PackageTest)


if __name__ == '__main__':
    unittestmain()
