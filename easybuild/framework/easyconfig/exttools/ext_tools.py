# Copyright 2024 Ghent University
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
#

"""
Easyconfig module that provides tools for extensions for EasyBuild easyconfigs.

Authors:

* Victor Machado (Do IT Now)
* Danilo Gonzalez (Do IT Now)
"""

from easybuild.framework.easyconfig.exttools.extensions.r_extension import RExtension
from easybuild.tools.build_log import EasyBuildError


class ExtTools():
    """Class for extension tools"""

    def __init__(self, ec):
        """
        Initialize the extension tools.

        :param ec: a parsed easyconfig file
        """

        self.ec = ec
        self.exts_list = ec.get('ec', {}).get('exts_list', [])
        self.exts_list_updated = []

        # TODO: Get ext class directly from the extension using source_urls, therefore supporting EasyConfigs with multiple extensions class
        self.exts_list_class = self._get_exts_list_class(ec)

    def _get_exts_list_class(self, ec):
        """
        Get the extension list class.

        :param ec: a parsed easyconfig file (EasyConfig instance)

        :return: the extension list class
        """

        if not ec:
            raise EasyBuildError("EasyConfig not provided to get the extension list class")

        # get the extension list class from the EasyConfig parameters
        exts_list_class = ec.get('ec', {}).get('exts_defaultclass', None)

        if not exts_list_class:

            # get EasyConfig parameters
            name = ec.get('ec', {}).get('name', None)

            # try deduce the extension list class from the EasyConfig parameters
            if name and (name == 'R') or (name.startswith('R-')):
                exts_list_class = 'RPackage'
            else:
                raise EasyBuildError("exts_defaultclass only supports RPackage and PythonPackage")

        return exts_list_class

    def _create_extension_instance(self, ext):
        """
        Create an instance of the extension class.

        :param ext: the extension to get the instance of

        :return: the extension instance
        """

        if not ext:
            raise EasyBuildError("Extension not provided to create the extension instance")

        if self.exts_list_class == 'RPackage':
            return RExtension(ext)
        else:
            raise EasyBuildError("exts_defaultclass %s not supported" % self.exts_list_class)

    def update_exts_list(self):
        """
        Update the extension list.
        """

        # init variables
        self.exts_list_updated = []

        # update the extension list
        for ext in self.exts_list:

            # if the extension is a string, store it as is and cskip further processing
            if isinstance(ext, str):
                self.exts_list_updated.append(ext)
                continue

            # create the extension instance
            pkg = self._create_extension_instance(ext)

            # get the latest version of the package
            name, version, checksum = pkg.get_latest_version()

            # update the extension list only if all the values are available
            if name and version and checksum:
                options = ext[2] if len(ext) == 3 else {}
                options['checksums'] = checksum
                self.exts_list_updated.append((name, version, options))
            else:
                self.exts_list_updated.append(ext)

        # TODO: print for testing purposes. To be deleted.
        for ext in self.exts_list_updated:
            print(ext)
