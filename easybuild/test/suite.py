#!/usr/bin/python
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
This script is a collection of all the testcases.
Usage: "python -m easybuild.test.suite.py" or "./easybuild/test/suite.py"

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
import tempfile
import unittest
from vsc import fancylogger

# toolkit should be first to allow hacks to work
import easybuild.test.asyncprocess as a
import easybuild.test.easyconfig as e
import easybuild.test.modulegenerator as mg
import easybuild.test.modules as m
import easybuild.test.filetools as f
import easybuild.test.repository as r
import easybuild.test.robot as robot
import easybuild.test.easyblock as b
import easybuild.test.variables as v
import easybuild.test.github as g
import easybuild.test.toolchainvariables as tcv
import easybuild.test.toolchain as tc
import easybuild.test.options as o


# initialize logger for all the unit tests
fd, log_fn = tempfile.mkstemp(prefix='easybuild-tests-', suffix='.log')
os.close(fd)
fancylogger.logToFile(log_fn)
log = fancylogger.getLogger()
log.setLevelName('DEBUG')

# call suite() for each module and then run them all
SUITE = unittest.TestSuite([x.suite() for x in [r, e, mg, m, f, a, robot, b, v, g, tcv, tc, o]])

# uses XMLTestRunner if possible, so we can output an XML file that can be supplied to Jenkins
xml_msg = ""
try:
    import xmlrunner  # requires unittest-xml-reporting package
    xml_dir = 'test-reports'
    res = xmlrunner.XMLTestRunner(output=xml_dir, verbosity=1).run(SUITE)
    xml_msg = ", XML output of tests available in %s directory" % xml_dir
except ImportError, err:
    sys.stderr.write("WARNING: xmlrunner module not available, falling back to using unittest...\n\n")
    res = unittest.TextTestRunner().run(SUITE)

fancylogger.logToFile(log_fn, enable=False)

if not res.wasSuccessful():
    sys.stderr.write("ERROR: Not all tests were successful.\n")
    print "Log available at %s" % log_fn, xml_msg
    sys.exit(2)
else:
    os.remove(log_fn)
