##
# Copyright 2009-2014 Ghent University
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
Utility functions for implementating module naming schemes.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Fotis Georgatos (Uni.Lu)
"""

from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME


def det_full_ec_version(ec):
    """
    Determine exact install version, based on supplied easyconfig.
    e.g. 1.2.3-goalf-1.1.0-no-OFED or 1.2.3 (for dummy toolchains)
    """

    ecver = None

    # determine main install version based on toolchain
    if ec['toolchain']['name'] == DUMMY_TOOLCHAIN_NAME:
        ecver = ec['version']
    else:
        ecver = "%s-%s-%s" % (ec['version'], ec['toolchain']['name'], ec['toolchain']['version'])

    # prepend/append version prefix/suffix
    ecver = ''.join([x for x in [ec.get('versionprefix', ''), ecver, ec['versionsuffix']] if x])

    return ecver
