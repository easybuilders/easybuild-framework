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
Base extension class for EasyBuild EasyConfig extension tools.

Authors:

* Victor Machado (Do IT Now)
* Danilo Gonzalez (Do IT Now)
"""

from easybuild.tools.build_log import EasyBuildError


class BaseExtension:
    def __init__(self, ext):
        self.name, self.version, self.options = self._get_ext_values(ext)

    def _get_ext_values(self, ext):
        """
        Extract the name, version, and options from an extension.

        :param ext: extension instance
        """

        if isinstance(ext, str):
            return ext, None, None
        elif isinstance(ext, (tuple, list)):
            if len(ext) == 1:
                return ext[0], None, None
            elif len(ext) == 2:
                return ext[0], ext[1], None
            elif len(ext) == 3:
                return ext[0], ext[1], ext[2]
            else:
                raise EasyBuildError("Invalid number of elements in extension tuple or list")
        elif isinstance(ext, dict):
            return (ext.get('name'), ext.get('version'), ext.get('options'))
        else:
            raise EasyBuildError("Invalid extension format")

    def update(self):
        """
        Update the package extension.
        """
        raise NotImplementedError("Subclasses should implement this!")
