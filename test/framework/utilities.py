##
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
##
"""
Various test utility functions.

@author: Kenneth Hoste (Ghent University)
"""

import os
import sys


def find_full_path(base_path, trim=(lambda x: x)):
    """
    Determine full path for given base path by looking in sys.path and PYTHONPATH.
    trim: a function that takes a path and returns a trimmed version of that path
    """

    full_path = None

    pythonpath = os.getenv('PYTHONPATH')
    if pythonpath:
        pythonpath = pythonpath.split(':')
    else:
        pythonpath = []
    for path in sys.path + pythonpath:
        tmp_path = os.path.join(trim(path), base_path)
        if os.path.exists(tmp_path):
            full_path = tmp_path
            break

    return full_path
