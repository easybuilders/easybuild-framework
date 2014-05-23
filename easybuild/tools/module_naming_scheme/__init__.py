##
# Copyright 2011-2014 Ghent University
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
Declares easybuild.tools.module_naming_scheme namespace, in an extendable way.

@author: Jens Timmerman (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
from pkgutil import extend_path
from vsc.utils import fancylogger

# we're not the only ones in this namespace
__path__ = extend_path(__path__, __name__)  #@ReservedAssignment


class ModuleNamingScheme(object):
    """Abstract class for a module naming scheme implementation."""

    def __init__(self, *args, **kwargs):
        """Initialize logger."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to module naming scheme.

        @param ec: dict-like object with easyconfig parameter values; for now only the 'name',
                   'version', 'versionsuffix' and 'toolchain' parameters are guaranteed to be available

        @return: string with full module name, e.g.: '<name>/<compiler>/<mpi_lib>/<version>'
        """
        return NotImplementedError
