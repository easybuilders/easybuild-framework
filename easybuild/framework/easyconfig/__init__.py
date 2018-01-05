# #
# Copyright 2009-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
"""The easyconfig package provides the EasyConfig class and all constants and functions involved with it"""

# for 1.X.Y compatibility reasons, following is defined
# TODO cleanup to be evaluated for 2.0 release

# is used (esp CUSTOM) in some easyblocks
from easybuild.framework.easyconfig.default import ALL_CATEGORIES
globals().update(ALL_CATEGORIES)

# subdirectory (of 'easybuild' dir) in which easyconfig files are located in a package
EASYCONFIGS_PKG_SUBDIR = 'easyconfigs'

# is used in some tools
from easybuild.framework.easyconfig.easyconfig import EasyConfig
