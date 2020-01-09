##
# Copyright 2015-2019 Ghent University
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
Implementation of the EasyBuild packaging naming scheme

:author: Robert Schmidt (Ottawa Hospital Research Institute)
:author: Kenneth Hoste (Ghent University)
"""
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.package.package_naming_scheme.pns import PackageNamingScheme
from datetime import datetime

class EasyBuildPNS(PackageNamingScheme):
    """Class implmenting the default EasyBuild packaging naming scheme."""

    def name(self, ec):
        """Determine package name"""
        self.log.debug("Easyconfig dict passed to name() looks like: %s ", ec)
        return '%s-%s' % (ec['name'], det_full_ec_version(ec))

    def version(self, ec):
        """Determine package version: Date used while build & install."""
        date_stamp = datetime.today().strftime('%Y%m%d')
        return '%s' % date_stamp
