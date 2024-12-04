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

from easybuild.framework.easyconfig.exttools.extensions.r_package import RPackage
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
        self.exts_list_class = self._get_exts_list_class(ec)
        self.exts_list_updated = []

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
            easyblock = ec.get('ec', {}).get('easyblock', None)

            # try deduce the extension list class from the EasyConfig parameters
            if name and (name == 'R') or (name.startswith('R-')):
                exts_list_class = 'RPackage'
            elif name and (name == 'Python') or (name.startswith('Python-')):
                exts_list_class = 'PythonPackage'
            elif easyblock and (easyblock == 'PythonBundle'):
                exts_list_class = 'PythonPackage'
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
            return RPackage(ext)
        else:
            raise EasyBuildError("exts_defaultclass %s not supported" % self.exts_list_class)

    def update_exts_list(self):
        """
        Update the extension list.
        """

        updated = []
        for ext in self.exts_list:
            pkg = self._create_extension_instance(ext)
            updated.append(pkg.update())

        self.exts_list_updated = updated
