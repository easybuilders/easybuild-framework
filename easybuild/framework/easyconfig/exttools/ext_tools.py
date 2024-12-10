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

import os
from easybuild.framework.easyconfig.exttools.extensions.r_extension import RExtension
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.tools.build_log import EasyBuildError


class ExtTools():
    """Class for extension tools"""

    def __init__(self, ec_path):
        """
        Initialize the extension tools.

        :param ec_path: the path to the EasyConfig file
        """

        if not ec_path:
            raise EasyBuildError("EasyConfig path not provided to initialize the extension tools")
        
        if not os.path.exists(ec_path):
            raise EasyBuildError(f"EasyConfig path does not exist: {ec_path}")
            
        self.ec_path = ec_path
        self.ec_parsed = EasyConfigParser(self.ec_path)
        self.ec_dict = self.ec_parsed.get_config_dict()

        self.exts_list = self.ec_dict.get('exts_list', [])
        self.exts_list_updated = []

        # TODO: add support for EasyConfigs with multiple extensions class
        self.exts_list_class = self._get_exts_list_class(self.ec_dict)

    def _get_exts_list_class(self, ec_dict):
        """
        Get the extension list class.

        :param ec_dict: the EasyConfig dictionary

        :return: the extension list class
        """

        if not ec_dict:
            raise EasyBuildError("EasyConfig dictionary not provided to get the extension list class")

        # get the extension list class from the EasyConfig parameters
        exts_list_class = ec_dict.get('exts_defaultclass')

        if not exts_list_class:

            # get EasyConfig name
            name = ec_dict.get('name')

            # try deduce the extension list class from the EasyConfig parameters
            if name and ((name == 'R') or (name.startswith('R-'))):
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
        count = 0

        # update the extension list
        for ext in self.exts_list:

            count += 1
            print(f"\rExtensions updated: {count}", end='')

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
        print()
        for ext in self.exts_list_updated:
            print(ext)
        print()
