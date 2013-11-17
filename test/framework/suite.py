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
Usage: "python -m test.framework.suite" or "python test/framework/suite.py"

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import shutil
import sys
import tempfile
import unittest
from vsc import fancylogger

# toolkit should be first to allow hacks to work
import test.framework.asyncprocess as a
import test.framework.config as c
import test.framework.easyblock as b
import test.framework.easyconfig as e
import test.framework.easyconfigparser as ep
import test.framework.easyconfigformat as ef
import test.framework.easyconfigversion as ev
import test.framework.filetools as f
import test.framework.github as g
import test.framework.license as l
import test.framework.module_generator as mg
import test.framework.modules as m
import test.framework.options as o
import test.framework.repository as r
import test.framework.robot as robot
import test.framework.systemtools as s
import test.framework.toolchain as tc
import test.framework.toolchainvariables as tcv
import test.framework.toy_build as t
import test.framework.variables as v


# make sure temporary files can be created/used
fd, fn = tempfile.mkstemp()
os.close(fd)
os.remove(fn)
testdir = tempfile.mkdtemp()
for test_fn in [fn, os.path.join(testdir, 'test')]:
    try:
        open(fn, 'w').write('test')
    except IOError, err:
        sys.stderr.write("ERROR: Can't write to temporary file %s, set $TMPDIR to a writeable directory" % (fn, msg))
        sys.exit(1)
os.remove(fn)
shutil.rmtree(testdir)

# initialize logger for all the unit tests
fd, log_fn = tempfile.mkstemp(prefix='easybuild-tests-', suffix='.log')
os.close(fd)
os.remove(log_fn)
fancylogger.logToFile(log_fn)
log = fancylogger.getLogger()
log.setLevelName('DEBUG')

# call suite() for each module and then run them all
# note: make sure the options unit tests run first, to avoid running some of them with a readily initialized config
tests = [o, r, ef, ev, ep, e, mg, m, f, a, robot, b, v, g, tcv, tc, t, c, s, l]
SUITE = unittest.TestSuite([x.suite() for x in tests])

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
    for f in glob.glob('%s*' % log_fn):
        os.remove(f)
