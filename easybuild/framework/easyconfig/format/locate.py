# #
# Copyright 2013-2013 Ghent University
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
Simple module to help locate supported formats
This could been done in __init__ as well, but it's apparently bad style.

@author: Stijn De Weirdt (Ghent University)
"""

from vsc.utils.missing import get_subclasses
from easybuild.framework.easyconfig.format.format import EasyConfigFormat
from easybuild.framework.easyconfig.format.one import FormatOneZero
from easybuild.framework.easyconfig.format.two import FormatTwoZero


def get_format_version_classes(version=None):
    """Return the (1st) subclass from EasyConfigFormat that has matching version"""
    all_classes = get_subclasses(EasyConfigFormat)
    if version is None:
        return all_classes
    else:
        return [x for x in all_classes if x.VERSION == version ]
