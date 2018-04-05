# #
# Copyright 2018-2018 Ghent University
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
Unit tests for easybuild/tools/containers.py

@author: Kenneth Hoste (Ghent University)
"""
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered 
from unittest import TextTestRunner

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.containers import check_container_base


class ContainersTest(EnhancedTestCase):
    """Tests for containers support"""

    def test_check_container_base(self):
        """Test check_container_base function."""

        for base_spec in [None, '']:
            self.assertErrorRegex(EasyBuildError, "--container-base must be specified", check_container_base, base_spec)

        # format of base spec must be correct: <bootstrap_agent>:<arg> or <bootstrap_agent>:<arg1>:<arg2>
        error_regex = "Invalid format for --container-base"
        for base_spec in ['foo', 'foo:bar:baz:sjee']:
            self.assertErrorRegex(EasyBuildError, error_regex, check_container_base, base_spec)

        # bootstrap agent must be known
        error_regex = "Bootstrap agent in container base spec must be one of: docker, localimage, shub"
        self.assertErrorRegex(EasyBuildError, error_regex, check_container_base, 'foo:bar')

        # check parsing of 'localimage' base spec
        expected = {'bootstrap_agent': 'localimage', 'arg1': '/path/to/base.img'}
        self.assertEqual(check_container_base('localimage:/path/to/base.img'), expected)

        # check parsing of 'docker' and 'shub' base spec (2nd argument, image tag, is optional)
        for agent in ['docker', 'shub']:
            expected = {'bootstrap_agent': agent, 'arg1': 'foo'}
            self.assertEqual(check_container_base('%s:foo' % agent), expected)
            expected.update({'arg2': 'bar'})
            self.assertEqual(check_container_base('%s:foo:bar' % agent), expected)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ContainersTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
