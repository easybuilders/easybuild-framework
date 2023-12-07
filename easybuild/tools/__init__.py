##
# Copyright 2009-2023 Ghent University
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
This declares the namespace for the tools submodule of EasyBuild,
which contains support utilities.

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
"""
__path__ = __import__('pkgutil').extend_path(__path__, __name__)


import distutils.version
import warnings
from easybuild.tools.loose_version import LooseVersion  # noqa(F401)


class StrictVersion(distutils.version.StrictVersion):
    """Temporary wrapper over distuitls StrictVersion that silences the deprecation warning"""
    def __init__(self, *args, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=DeprecationWarning)
            distutils.version.StrictVersion.__init__(self, *args, **kwargs)
