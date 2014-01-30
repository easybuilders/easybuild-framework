##
# Copyright 2012-2014 Ghent University
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
Support for FFTW (Fastest Fourier Transform in the West) as toolchain FFT library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from distutils.version import LooseVersion

from easybuild.tools.toolchain.fft import Fft


class Fftw(Fft):
    """FFTW FFT library"""

    FFT_MODULE_NAME = ['FFTW']

    def _set_fftw_variables(self):

        suffix = ''
        version = self.get_software_version(self.FFT_MODULE_NAME)[0]
        if LooseVersion(version) < LooseVersion('2') or LooseVersion(version) >= LooseVersion('4'):
            self.log.raiseException("_set_fft_variables: FFTW unsupported version %s (major should be 2 or 3)" % version)
        elif LooseVersion(version) > LooseVersion('2'):
            suffix = '3'

        # order matters!
        fftw_libs = ["fftw%s" % suffix]
        if self.options['usempi']:
            fftw_libs.insert(0, "fftw%s_mpi" % suffix)

        self.FFT_LIB = fftw_libs

    def _set_fft_variables(self):
        self._set_fftw_variables()

        super(Fftw, self)._set_fft_variables()

        ## TODO can these be replaced with the FFT ones?
        self.variables.join('FFTW_INC_DIR', 'FFT_INC_DIR')
        self.variables.join('FFTW_LIB_DIR', 'FFT_LIB_DIR')
        if 'FFT_STATIC_LIBS' in self.variables:
            self.variables.join('FFTW_STATIC_LIBS', 'FFT_STATIC_LIBS')
