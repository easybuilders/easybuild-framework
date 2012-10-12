##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
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
EasyBuild support for Python packages that are configured with CMake, implemented as an easyblock
"""
from easybuild.easyblocks.generic.cmakemake import CMakeMake
from easybuild.easyblocks.generic.pythonpackage import PythonPackage


class CMakePythonPackage(CMakeMake, PythonPackage):
    """Build a Python package and module with cmake.

    Some packages use cmake to first build and install C Python packages
    and then put the Python package in lib/pythonX.Y/site-packages.

    We install this in a seperate location and generate a module file 
    which sets the PYTHONPATH.

    We use the default CMake implementation, and use make_module_extra from PythonPackage.
    """

    def __init__(self, *args, **kwargs):
        """Initialize with PythonPackage."""
        PythonPackage.__init__(self, *args, **kwargs)

    def configure_step(self, *args, **kwargs):
        """Main configuration using cmake"""

        PythonPackage.configure_step(self, *args, **kwargs)

        return CMakeMake.configure_step(self, *args, **kwargs)

    def build_step(self, *args, **kwargs):
        """Build Python package with cmake"""
        return CMakeMake.build_step(self, *args, **kwargs)

    def install_step(self):
        """Install with cmake install"""
        return CMakeMake.install_step(self)

    def make_module_extra(self):
        """Add extra Python package module parameters"""
        return PythonPackage.make_module_extra(self)
