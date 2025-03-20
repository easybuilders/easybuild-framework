# #
# Copyright 2009-2025 Ghent University
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
from easybuild.tools.build_log import EasyBuildError, EasyBuildExit, print_msg
from easybuild.tools.filetools import which
from easybuild.tools.run import run_shell_cmd


def det_os_deps(easyconfigs):
    """
    Using an easyconfigs object, this utility function will return a list
    of operating system dependencies that are required to build one or more
    easybuilds modules.
    """
    res = set()
    os_deps = reduce(operator.add, [obj['ec']['osdependencies'] for obj in easyconfigs], [])
    for os_dep in os_deps:
        if isinstance(os_dep, str):
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

    print_msg(f"{tool_name} tool found at {tool_path}")

    if not min_tool_version:
        return True

    version_cmd = f"{tool_name} --version"
    res = run_shell_cmd(version_cmd, hidden=True, in_dry_run=True)
    if res.exit_code != EasyBuildExit.SUCCESS:
        raise EasyBuildError(f"Error running '{version_cmd}' for tool {tool_name} with output: {res.output}")

    regex_res = re.search(r"\d+\.\d+(\.\d+)?", res.output.strip())
    if not regex_res:
        raise EasyBuildError(f"Error parsing version for tool {tool_name}")

    tool_version = regex_res.group(0)
    version_ok = LooseVersion(str(min_tool_version)) <= LooseVersion(tool_version)
    if version_ok:
        print_msg(f"{tool_name} version '{tool_version}' is {min_tool_version} or higher ... OK")

    return version_ok
