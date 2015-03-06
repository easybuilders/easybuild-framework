# #
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
# #
"""
Unit tests for parallelbuild.py

@author: Kenneth Hoste (Ghent University)
"""
import os
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.tools import config, parallelbuild
from easybuild.tools.parallelbuild import PbsJob, build_easyconfigs_in_parallel
from easybuild.tools.robot import resolve_dependencies


def mock(*args, **kwargs):
    """Function used for mocking several functions imported in parallelbuild module."""
    return 1


class MockPbsJob(object):
    """Mocking class for PbsJob."""
    def __init__(self, *args, **kwargs):
        self.deps = []
        self.jobid = None
        self.clean_conn = None

    def add_dependencies(self, *args, **kwargs):
        pass

    def cleanup(self, *args, **kwargs):
        pass

    def has_holds(self, *args, **kwargs):
        pass

    def submit(self, *args, **kwargs):
        pass


class ParallelBuildTest(EnhancedTestCase):
    """ Testcase for run module """

    def setUp(self):
        """Set up testcase."""
        super(ParallelBuildTest, self).setUp()
        build_options = {
            'robot_path': os.path.join(os.path.dirname(__file__), 'easyconfigs'),
            'valid_module_classes': config.module_classes(),
            'validate': False,
        }
        init_config(build_options=build_options)

        # put mocked functions in place
        parallelbuild.connect_to_server = mock
        parallelbuild.disconnect_from_server = mock
        parallelbuild.get_ppn = mock
        parallelbuild.PbsJob = MockPbsJob

    def test_build_easyconfigs_in_parallel(self):
        """Basic test for build_easyconfigs_in_parallel function."""
        easyconfig_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.5-goolf-1.4.10.eb')
        easyconfigs = process_easyconfig(easyconfig_file)
        ordered_ecs = resolve_dependencies(easyconfigs)
        jobs = build_easyconfigs_in_parallel("echo %(spec)s", ordered_ecs, prepare_first=False)
        self.assertEqual(len(jobs), 8)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ParallelBuildTest)

if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    main()
