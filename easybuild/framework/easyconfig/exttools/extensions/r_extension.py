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
R extension class for EasyBuild EasyConfig extension tools.

Authors:

* Victor Machado (Do IT Now)
* Danilo Gonzalez (Do IT Now)
"""

import requests

from easybuild.tools.build_log import EasyBuildError, print_warning
from .base_extension import BaseExtension

CRANDB_URL = "https://crandb.r-pkg.org"


class RExtension(BaseExtension):

    def __init__(self, ext):
        """
        Initialize the R package extension.

        :param ext: the R package extension
        """

        super(RExtension, self).__init__(ext)

    def _get_metadata(self, version=None):
        """
        Get the metadata for the R package.

        :param version: the version of the R package. If None, get the latest version

        :return: the metadata for the R package
        """

        # init variables
        metadata = None

        # build the url to get the package's metadata
        url = f"{CRANDB_URL}/{self.name}"
        if version:
            url += f"/{version}"

        # get the package's metadata from the database
        try:
            response = requests.get(url)
            if response.status_code == 200:
                metadata = response.json()

        except Exception as err:
            print_warning(f"Exception while getting metadata for extension {self.name}: {err}")

        return metadata

    def _parse_metadata(self, metadata):
        """
        Parse the metadata for the R package.

        :param metadata: the metadata for the R package

        :return: the parsed metadata for the R package
        """

        if not metadata:
            raise EasyBuildError("No package metadata provided to parse")

        name = metadata.get('Package')
        version = metadata.get('Version')
        checksum = metadata.get('MD5sum')

        return (name, version, checksum)

    def get_latest_version(self):
        """
        Get the name, version and checksum for latest version of the R package extension.

        :return: name, version and checksum for the latest version of the R package extension
        """

        # init variables
        name, version, checksum = None, None, None

        # get the metadata for the R package
        metadata = self._get_metadata()

        if metadata:
            name, version, checksum = self._parse_metadata(metadata)

            if name and version and not checksum:
                # TODO: download the package and calculate the checksum
                checksum = ""
                pass

        return (name, version, checksum)
