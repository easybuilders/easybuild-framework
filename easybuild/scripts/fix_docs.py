# #
# Copyright 2016-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
Overhaul all @param and @author tags for rst API documentation
(@param x --> :param x: and @author --> :author:)

:author: Caroline De Brouwer (Ghent University)
"""

import os
import re
import sys

from easybuild.tools.build_log import EasyBuildError
from vsc.utils.generaloption import simple_option

if not len(sys.argv) > 1:
    raise EasyBuildError("Please include path to easybuild folder")

if not os.path.isdir(sys.argv[1]):
    raise EasyBuildError("%s is not a directory" % sys.argv[1])

path = sys.argv[1]

py_files = []

for basename, _, filenames in os.walk(path):
    for fn in filenames:
        if os.path.splitext(fn)[1] == '.py':
            py_files.append(os.path.join(basename, fn))

for tmp in py_files:
    print "Processing %s" % tmp
    # exclude self
    if os.path.basename(tmp) == os.path.basename(__file__):
        continue
    with open(tmp) as f:
        temp = "tmp_file.py"
        out = open(temp, 'w')
        for line in f:
            if "@author" in line:
                out.write(re.sub(r"@author: (.*)", r":author: \1", line))
            elif "@param" in line:
                out.write(re.sub(r"@param ([^:]*):", r":param \1:", line))
            else:
                out.write(line)
        out.close()
        os.rename(temp, tmp)
