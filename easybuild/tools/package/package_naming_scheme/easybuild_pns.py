##
# Copyright 2015-2015 Ghent University
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
Implementation of the EasyBuild packaging naming scheme

@author: Robert Schmidt (Ottawa Hospital Research Institute)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.package.package_naming_scheme.pns import PackageNamingScheme


class EasyBuildPNS(PackageNamingScheme):
    """Class implmenting the default EasyBuild packaging naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain']

    def name(self, ec):
        """Determine package name"""
        self.log.debug("easyconfig dict for name looks like %s " % ec )
        name_template = "eb%(eb_ver)s-%(name)s-%(version)s-%(toolchain)s"
        pkg_name = name_template % {
            'toolchain' : self._toolchain(ec),
            'version': '-'.join([x for x in [ec.get('versionprefix', ''), ec['version'], ec['versionsuffix'].lstrip('-')] if x]),
            'name' : ec['name'],
            'eb_ver': self.eb_ver,
        }
        return pkg_name

    def _toolchain(self, ec):
        """Determine toolchain"""
        toolchain_template = "%(toolchain_name)s-%(toolchain_version)s"
        pkg_toolchain = toolchain_template % {
            'toolchain_name': ec['toolchain']['name'],
            'toolchain_version': ec['toolchain']['version'],
        }
        return pkg_toolchain
