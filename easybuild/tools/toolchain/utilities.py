##
# Copyright 2012 Stijn De Weirdt
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
Toolchain utility module

Easy access to actual Toolchain classes
    search_toolchain

Based on VSC-tools vsc.mympirun.mpi.mpi and vsc.mympirun.rm.sched
"""
import glob
import os
import sys

from easybuild.tools.toolchain.toolchain import Toolchain

def get_subclasses(cls):
    """
    Get all subclasses recursively
    """
    res = []
    for cl in cls.__subclasses__():
        for subcl in get_subclasses(cl)+[cl]:
            if not subcl in res:
                res.append(subcl)
    return res

def search_toolchain(name):
    """Find a toolchain with matching name
        returns toolchain (or None), found_toolchains
    """

    # import all available toolchains, so we know about them
    for path in sys.path:
        for module in glob.glob(os.path.join(path, 'easybuild', 'toolchains', '*.py')):
            if not module.endswith('__init__.py'):
                modpath = "easybuild.toolchains.%s" % module.split(os.path.sep)[-1].split('.')[0]
                __import__(modpath, globals(), locals(), [''])

    found_tcs = get_subclasses(Toolchain)

    # filter found toolchain subclasses based on whether they can be used a toolchains
    found_tcs = [tc for tc in found_tcs if tc._is_toolchain_for(None)]

    for tc in found_tcs:
        if tc._is_toolchain_for(name):
            return tc, found_tcs

    return None, found_tcs
