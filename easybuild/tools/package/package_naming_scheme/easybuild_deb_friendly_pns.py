# -*- coding: utf-8 -*- vim: set fileencoding=utf-8
##
# Copyright 2015-2022 Ghent University
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
Implementation of the EasyBuild deb friendly packaging naming scheme

:author: Robert Schmidt (Ottawa Hospital Research Institute)
:author: Kenneth Hoste (Ghent University)
:author: Martin Budsjö (VolvoCars)
"""
from easybuild.tools.package.package_naming_scheme.easybuild_pns import EasyBuildPNS
from easybuild.tools.version import VERSION as EASYBUILD_VERSION


class EasyBuildDebFriendlyPNS(EasyBuildPNS):
    """Class implmenting the Deb friendly EasyBuild packaging naming scheme."""

    def version(self, ec):
        """Determine package version: EasyBuild version used to build & install."""
        ebver = str(EASYBUILD_VERSION)
        if ebver.endswith('dev'):
            # try and make sure that 'dev' EasyBuild version is not considered newer just because it's longer
            # (e.g., 2.2.0 vs 2.2.0dev)
            # cfr. http://rpm.org/ticket/56,
            # https://debian-handbook.info/browse/stable/sect.manipulating-packages-with-dpkg.html (see box in 5.4.3)
            ebver.replace('dev', '~dev')

        # Make sure to add a `0` to the ebver if it doesn't start with a number
        if not ebver[0].isdigit():
            ebver = '0'+ebver

        #
        # Postfix `-eb` to ebver instead of prefixing it to comply with
        # https://www.debian.org/doc/debian-policy/ch-controlfields.html#version
        return '%s-eb' % ebver
