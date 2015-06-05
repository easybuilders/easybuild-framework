##
# Copyright 2014-2015 Ghent University
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
Support for Cray FFTW.

@author: Petar Forai (IMP/IMBA, Austria)
@author: Kenneth Hoste (Ghent University)
"""
import os

from easybuild.toolchains.fft.fftw import Fftw
from easybuild.tools.build_log import EasyBuildError


class CrayFFTW(Fftw):
    """Support for Cray FFTW."""
    # FFT support, via Cray-provided fftw module
    FFT_MODULE_NAME = ['fftw']

    def _get_software_root(self, name):
        """Get install prefix for specified software name; special treatment for Cray modules."""
        if name == 'fftw':
            # Cray-provided fftw module
            env_var = 'FFTW_INC'
            incdir = os.getenv(env_var, None)
            if incdir is None:
                raise EasyBuildError("Failed to determine install prefix for %s via $%s", name, env_var)
            else:
                root = os.path.dirname(incdir)
                self.log.debug("Obtained install prefix for %s via $%s: %s", name, env_var, root)
        else:
            root = super(CrayFFTW, self)._get_software_root(name)

        return root

    def _get_software_version(self, name):
        """Get version for specified software name; special treatment for Cray modules."""
        if name == 'fftw':
            # Cray-provided fftw module
            env_var = 'FFTW_VERSION'
            ver = os.getenv(env_var, None)
            if ver is None:
                raise EasyBuildError("Failed to determine version for %s via $%s", name, env_var)
            else:
                self.log.debug("Obtained version for %s via $%s: %s", name, env_var, ver)
        else:
            ver = super(CrayFFTW, self)._get_software_version(name)

        return ver
