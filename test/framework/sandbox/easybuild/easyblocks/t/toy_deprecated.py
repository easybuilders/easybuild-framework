##
# Copyright 2009-2024 Ghent University
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
##
"""
(deprecated) EasyBuild support for building and installing toy, implemented as an easyblock

@author: Bart Oldeman (McGill University, Calcul Quebec, Digital Research Alliance of Canada)
"""

from easybuild.easyblocks.toy import EB_toy


class EB_toy_deprecated(EB_toy):
    """Support for building/installing toy with deprecated post_install step."""

    def post_install_step(self):
        """Any postprocessing for toy (deprecated)"""
        print("This step is deprecated.")
        super(EB_toy, self).post_install_step()
