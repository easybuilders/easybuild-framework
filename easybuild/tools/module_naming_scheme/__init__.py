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
import os
from pkgutil import extend_path
from vsc.utils import fancylogger

# we're not the only ones in this namespace
__path__ = extend_path(__path__, __name__)  #@ReservedAssignment


class ModuleNamingScheme(object):
    """Abstract class for a module naming scheme implementation."""

    REQUIRED_KEYS = None

    def __init__(self, *args, **kwargs):
        """Initialize logger."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def is_sufficient(self, keys):
        """Determine whether specified list of easyconfig parameters is sufficient for this module naming scheme."""
        if self.REQUIRED_KEYS is not None:
            return set(keys).issuperset(set(self.REQUIRED_KEYS))
        else:
            self.log.error("Constant REQUIRED_KEYS is not defined, should specify required easyconfig parameters.")

    def requires_toolchain_details(self):
        """
        Determine whether toolchain details are required by this module naming scheme,
        e.g. whether one of det_toolchain_* functions are relied upon.
        """
        return False

    def det_full_module_name(self, ec):
        """
        Determine full module name, relative to the top of the module path.

        @param ec: dict-like object with easyconfig parameter values; for now only the 'name',
                   'version', 'versionsuffix' and 'toolchain' parameters are guaranteed to be available

        @return: string with full module name, e.g.: '<compiler>/<mpi_lib>/<name>/<version>'
        """
        raise NotImplementedError

    def det_short_module_name(self, ec):
        """
        Determine short module name, i.e. the name under which modules will be exposed to users.

        @param ec: dict-like object with easyconfig parameter values; for now only the 'name',
                   'version', 'versionsuffix' and 'toolchain' parameters are guaranteed to be available
        @return: string with module name, e.g. '<name>/<version>'
        """
        # by default: full module name doesn't include a $MODULEPATH subdir
        return self.det_full_module_name(ec)

    def det_module_subdir(self, ec):
        """
        Determine subdirectory for module file in $MODULEPATH.
        This determines the separation between module names exposed to users, and what's part of the $MODULEPATH.

        @param ec: dict-like object with easyconfig parameter values; for now only the 'name',
                   'version', 'versionsuffix' and 'toolchain' parameters are guaranteed to be available
        @return: string with subdir path (relative to $MODULEPATH), e.g. '<compiler>/<mpi_lib>'
        """
        # by default: no subdirectory
        return ''

    def det_modpath_extensions(self, ec):
        """
        Determine list of subdirectories for which to extend $MODULEPATH with when this module is loaded (if any).

        @param ec: dict-like object with easyconfig parameter values; for now only the 'name',
                   'version', 'versionsuffix' and 'toolchain' parameters are guaranteed to be available
        @return: A list of $MODULEPATH subdirectories.
        """
        # by default: an empty list of subdirectories to extend $MODULEPATH with
        return []

    def det_init_modulepaths(self, ec):
        """
        Determine initial module paths, where the modules that are top of the hierarchy (if any) live.
        """
        return []

    def expand_toolchain_load(self):
        """
        Determine whether load statements for a toolchain should be expanded to load statements for its dependencies.
        This is useful when toolchains are not exposed to users.
        """
        # by default: just include a load statement for the toolchain
        return False
