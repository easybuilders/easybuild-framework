##
# Copyright 2011-2017 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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

:author: Jens Timmerman (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import pkg_resources

# required for backward compatibility
from easybuild.tools.module_naming_scheme.mns import ModuleNamingScheme

pkg_resources.declare_namespace(__name__)

# suffix for devel module filename
DEVEL_MODULE_SUFFIX = '-easybuild-devel'

# general module class
GENERAL_CLASS = 'all'
