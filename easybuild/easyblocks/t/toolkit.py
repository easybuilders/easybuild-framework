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
EasyBuild support for installing compiler toolkits, implemented as an easyblock
"""

from easybuild.framework.application import Application


class EB_Toolkit(Application):
    """
    Compiler toolkit: generate module file only, nothing to make/install
    """
    def build(self):
        """
        Do almost nothing
        - just create an install directory?
        """
        self.gen_installdir()
        self.make_installdir()

    def configure(self):
        """ Do nothing """
        pass

    def make(self):
        """ Do nothing """
        pass

    def make_install(self):
        """ Do nothing """
        pass

    def make_module_req(self):
        return ''

    def sanitycheck(self):
        """
        As a toolkit doens't install anything really, this is always true
        """
        self.sanityCheckOK = True
