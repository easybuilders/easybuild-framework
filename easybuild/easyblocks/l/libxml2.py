##
# Copyright 2012 Jens Timmerman
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
EasyBuild support for building and installing libxml2 with python bindings,
implemented as an easyblock.
"""
import os

from easybuild.easyblocks.generic.configuremake import ConfigureMake
from easybuild.easyblocks.generic.pythonpackage import PythonPackage


class EB_libxml2(ConfigureMake, PythonPackage):
    """Support for building and installing libxml2 with python bindings"""
    def __init__(self, *args, **kwargs):
        """
        Constructor
        init as a pythonpackage, since that is also an application
        """
        PythonPackage.__init__(self, *args, **kwargs)

    def configure_step(self):
        """
        Configure and 
        Test if python module is loaded
        """
        if not os.getenv("EBROOTPYTHON"):
            self.log.error("Python module not loaded")
       
        ConfigureMake.configure_step(self)

        try:
            os.chdir('python')
            PythonPackage.configure_step(self)
            os.chdir('..')
        except OSError, err:
            self.log.error("Failed to configure libxml2 Python bindings: %s" % err)

    def build_step(self):
        """
        Make libxml2 first, then make python bindings
        """
        ConfigureMake.build_step(self)

        try:
            os.chdir('python')
            # set cflags to point to include folder 
            os.putenv('CFLAGS', "-I../include")
            PythonPackage.build_step(self)
            os.chdir('..')
        except OSError, err:
            self.log.error("Failed to build libxml2 Python bindings: %s" % err)

    def install_step(self):
        """
        Install libxml2 and install python bindings
        """
        ConfigureMake.install_step(self)

        try:
            os.chdir('python')
            PythonPackage.install_step(self)
            os.chdir('..')
        except OSError, err:
            self.log.error("Failed to install libxml2 Python bindings: %s" % err)

    def make_module_extra(self):
        """
        Add python bindings to the pythonpath
        """
        return PythonPackage.make_module_extra(self)

    def sanity_check_step(self):
        """Custom sanity check for libxml2"""

        custom_paths = {
                        'files':["lib/libxml2.a", "lib/libxml2.so"],
                        'dirs':["bin", self.pylibdir, "include/libxml2/libxml"],
                       }

        ConfigureMake.sanity_check_step(self, custom_paths=custom_paths)
