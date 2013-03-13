##
# Copyright 2012-2013 Ghent University
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
Support for Intel FFTW as toolchain FFT library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.toolchains.fft.fftw import Fftw


class IntelFFTW(Fftw):
    """FFTW wrapper functionality of Intel MKL"""

    FFT_MODULE_NAME = ['imkl']

    FFT_LIB_GROUP = True
    FFT_LIB_STATIC = True

    def _set_fftw_variables(self):
        if not hasattr(self, 'BLAS_LIB_DIR'):
            self.log.raiseException("_set_fftw_variables: IntelFFT based on IntelMKL (no BLAS_LIB_DIR found)")

        fftwsuff = ""
        if self.options.get('pic', None):
            fftwsuff = "_pic"
        fftw_libs = ["fftw3xc_intel%s" % fftwsuff]
        if self.options['usempi']:
            fftw_libs.append("fftw3x_cdft%s" % fftwsuff) ## add cluster interface
            fftw_libs.append("mkl_cdft_core") ## add cluster dft
            fftw_libs.extend(self.variables['LIBBLACS'].flatten()) ## add BLACS; use flatten because ListOfList

        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())
        fftw_libs.extend(self.variables['LIBBLAS'].flatten()) ## add core (contains dft) ; use flatten because ListOfList
        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())


        self.FFT_LIB = fftw_libs

        self.FFT_LIB_DIR = self.BLAS_LIB_DIR
        self.FFT_INCLUDE_DIR = self.BLAS_INCLUDE_DIR
