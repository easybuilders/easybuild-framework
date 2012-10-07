##
# Copyright 2012 Stijn De Weirdt
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
The toolchain module with the abstract Toolchain class and
a set of derived, predefined and tested toolchains.

Creating a new toolchain should be as simple as possible.
"""


from vsc.fancylogger import getLogger



class Toolchain(object):
    """General toolchain class"""
    NAME = None
    VERSION = None
    def __init__(self, name=None, version=None):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        if name is None:
            name = self.NAME
        if name is None:
            self.log.raiseException("init: no name provided")
        self.name = name


        if version is None:
            version = self.VERSION
        if version is None:
            self.log.raiseException("init: no version provided")
        self.version = version

        self.opts = None
        self.vars = None

    def set_variables(self):
        """Do nothing? Everything should have been set by others
            Needs to be defined for super() relations
        """
        self.log.debug("set_variables: toolchain variables. Do nothing.")

    def generate_vars(self):
        """Convert the variables in simple vars"""
        self.vars = {}
        for k, v in self.variables.items():
            self.vars[k] = str(v)
