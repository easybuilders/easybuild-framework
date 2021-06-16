#!/usr/bin/python
# #
# Copyright 2012-2021 Ghent University
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
This script is a collection of all the testcases.
Usage: "python -m test.framework.suite" or "python test/framework/suite.py"

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import sys
import tempfile
import unittest

# initialize EasyBuild logging, so we disable it
from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.options import set_tmpdir

import test.framework.asyncprocess as a
import test.framework.build_log as bl
import test.framework.config as c
import test.framework.containers as ct
import test.framework.easyblock as b
import test.framework.easyconfig as e
import test.framework.easyconfigparser as ep
import test.framework.easyconfigformat as ef
import test.framework.easyconfigversion as ev
import test.framework.easystack as es
import test.framework.ebconfigobj as ebco
import test.framework.environment as env
import test.framework.docs as d
import test.framework.filetools as f
import test.framework.format_convert as f_c
import test.framework.general as gen
import test.framework.github as g
import test.framework.hooks as h
import test.framework.include as i
import test.framework.lib as lib
import test.framework.license as lic
import test.framework.module_generator as mg
import test.framework.modules as m
import test.framework.modulestool as mt
import test.framework.options as o
import test.framework.parallelbuild as p
import test.framework.package as pkg
import test.framework.repository as r
import test.framework.robot as robot
import test.framework.run as run
import test.framework.style as st
import test.framework.systemtools as s
import test.framework.toolchain as tc
import test.framework.toolchainvariables as tcv
import test.framework.toy_build as t
import test.framework.type_checking as et
import test.framework.tweak as tw
import test.framework.utilities_test as u
import test.framework.variables as v
import test.framework.yeb as y

# set plain text key ring to be used,
# so a GitHub token stored in it can be obtained without having to provide a password
try:
    # with recent versions of keyring, PlaintextKeyring comes from keyrings.alt
    import keyring
    from keyrings.alt.file import PlaintextKeyring
    keyring.set_keyring(PlaintextKeyring())
except ImportError:
    try:
        # with old versions of keyring, PlaintextKeyring comes from keyring.backends
        import keyring
        from keyring.backends.file import PlaintextKeyring
        keyring.set_keyring(PlaintextKeyring())
    except ImportError:
        pass

# disable all logging to significantly speed up tests
fancylogger.disableDefaultHandlers()
fancylogger.setLogLevelError()


# make sure temporary files can be created/used
try:
    set_tmpdir(raise_error=True)
except EasyBuildError as err:
    sys.stderr.write("No execution rights on temporary files, specify another location via $TMPDIR: %s\n" % err)
    sys.exit(1)

# initialize logger for all the unit tests
fd, log_fn = tempfile.mkstemp(prefix='easybuild-tests-', suffix='.log')
os.close(fd)
os.remove(log_fn)
fancylogger.logToFile(log_fn)
log = fancylogger.getLogger()

# call suite() for each module and then run them all
# note: make sure the options unit tests run first, to avoid running some of them with a readily initialized config
tests = [gen, bl, o, r, ef, ev, ebco, ep, e, mg, m, mt, f, run, a, robot, b, v, g, tcv, tc, t, c, s, lic, f_c,
         tw, p, i, pkg, d, env, et, y, st, h, ct, lib, u, es]

SUITE = unittest.TestSuite([x.suite() for x in tests])
res = unittest.TextTestRunner().run(SUITE)

fancylogger.logToFile(log_fn, enable=False)

if not res.wasSuccessful():
    sys.stderr.write("ERROR: Not all tests were successful.\n")
    print("Log available at %s" % log_fn)
    sys.exit(2)
else:
    for fn in glob.glob('%s*' % log_fn):
        os.remove(fn)
