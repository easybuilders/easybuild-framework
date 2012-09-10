##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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
import copy
import os
from distutils.version import LooseVersion

import easybuild.tools.environment as env
from easybuild.tools import systemtools
from easybuild.tools.build_log import getLog
from easybuild.tools.modules import Modules, get_software_root, get_software_version

class LinearAlgebra(object):
    """General LinearAlgebra-like class
        To provide the BLAS/LAPACK/ScaLAPACK tools
    """
    {'packed-groups':False}
    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLog(self.__class__.__name__)

class IntelMKL(LinearAlgebra):
    """Interface to Intel MKL"""
