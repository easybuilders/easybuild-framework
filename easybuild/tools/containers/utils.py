# #
# Copyright 2009-2023 Ghent University
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
Authors:

* Shahzeb Siddiqui (Pfizer)
* Kenneth Hoste (HPC-UGent)
* Mohamed Abidi (Bright Computing)
"""
import operator
import re
from functools import reduce

from easybuild.tools import LooseVersion
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.filetools import which
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.run import run_cmd


def det_os_deps(easyconfigs):
    """
    Using an easyconfigs object, this utility function will return a list
    of operating system dependencies that are required to build one or more
    easybuilds modules.
    """
    res = set()
    os_deps = reduce(operator.add, [obj['ec']['osdependencies'] for obj in easyconfigs], [])
    for os_dep in os_deps:
        if isinstance(os_dep, string_type):
            res.add(os_dep)
        elif isinstance(os_dep, tuple):
            res.update(os_dep)
    return res


def check_tool(tool_name, min_tool_version=None):
    """
    This function is a predicate check for the existence of tool_name on the system PATH.
    If min_tool_version is not None, it will check that the version has an equal or higher value.
    """
    if tool_name == 'sudo':
        # disable checking of permissions for 'sudo' command,
        # since read permissions may not be available for 'sudo' executable (e.g. on CentOS)
        tool_path = which(tool_name, check_perms=False)
    else:
        tool_path = which(tool_name)

    if not tool_path:
        return False

    print_msg("{0} tool found at {1}".format(tool_name, tool_path))

    if not min_tool_version:
        return True

    version_cmd = "{0} --version".format(tool_name)
    out, ec = run_cmd(version_cmd, simple=False, trace=False, force_in_dry_run=True)
    if ec:
        raise EasyBuildError("Error running '{0}' for tool {1} with output: {2}".format(version_cmd, tool_name, out))
    res = re.search(r"\d+\.\d+(\.\d+)?", out.strip())
    if not res:
        raise EasyBuildError("Error parsing version for tool {0}".format(tool_name))
    tool_version = res.group(0)
    version_ok = LooseVersion(str(min_tool_version)) <= LooseVersion(tool_version)
    if version_ok:
        print_msg("{0} version '{1}' is {2} or higher ... OK".format(tool_name, tool_version, min_tool_version))
    return version_ok
