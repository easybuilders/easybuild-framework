# #
# Copyright 2009-2018 Ghent University
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
:author: Shahzeb Siddiqui (Pfizer)
:author: Kenneth Hoste (HPC-UGent)
:author: Mohamed Abidi (Bright Computing)
"""
import operator
from distutils.version import LooseVersion
from easyconfigs.tools.filetools import which
from easybuild.tools.build_log import print_msg
from easybuild.tools.run import run_cmd


def det_os_deps(easyconfigs):
    res = set()
    _os_deps = reduce(operator.add, [obj['ec']['osdependencies'] for obj in easyconfigs], [])
    for os_dep in _os_deps:
        if isinstance(os_dep, basestring):
            res.add(os_dep)
        elif isinstance(os_dep, tuple):
            res.update(os_dep)
    return res


def check_tool(tool_name, min_tool_version=None):
    tool_path = which(tool_name)
    if tool_path:
        print_msg("tool {0!r} found at {1!r}".format(tool_name, tool_path))

    min_tool_version = min_tool_version or '0.0'

    out, ec = run_cmd("{0} --version".format(tool_name), simple=False, trace=False, force_in_dry_run=True)
    if ec:
        return False
    tool_version = out.strip()
    return LooseVersion(str(min_tool_version)) <= LooseVersion(tool_version)
