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
Support for Intel FFTW as toolchain FFT library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import os
from distutils.version import LooseVersion

from easybuild.toolchains.fft.fftw import Fftw
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.utilities import all, any

class IntelFFTW(Fftw):
    """FFTW wrapper functionality of Intel MKL"""

    FFT_MODULE_NAME = ['imkl']

    FFT_LIB_GROUP = True
    FFT_LIB_STATIC = True

    def _set_fftw_variables(self):
        if not hasattr(self, 'BLAS_LIB_DIR'):
            self.log.raiseException("_set_fftw_variables: IntelFFT based on IntelMKL (no BLAS_LIB_DIR found)")

        imklver = get_software_version(self.FFT_MODULE_NAME[0])

        fftwsuff = ""
        if self.options.get('pic', None):
            fftwsuff = "_pic"
        fftw_libs = ["fftw3xc_intel%s" % fftwsuff]
        if self.options['usempi']:
            # add cluster interface
            if LooseVersion(imklver) < LooseVersion("11.1"):
                if LooseVersion(imklver) >= LooseVersion("11.0"):
                    fftw_libs.append("fftw3x_cdft_lp64%s" % fftwsuff)
                elif LooseVersion(imklver) >= LooseVersion("10.3"):
                    fftw_libs.append("fftw3x_cdft%s" % fftwsuff)
                fftw_libs.append("mkl_cdft_core")  # add cluster dft
                fftw_libs.extend(self.variables['LIBBLACS'].flatten()) ## add BLACS; use flatten because ListOfList

        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())
        fftw_libs.extend(self.variables['LIBBLAS'].flatten()) ## add core (contains dft) ; use flatten because ListOfList
        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())

        self.FFT_LIB_DIR = self.BLAS_LIB_DIR
        self.FFT_INCLUDE_DIR = self.BLAS_INCLUDE_DIR

        # building the FFTW interfaces is optional,
        # so make sure libraries are there before FFT_LIB is set
        imklroot = get_software_root(self.FFT_MODULE_NAME[0])
        fft_lib_dirs = [os.path.join(imklroot, d) for d in self.FFT_LIB_DIR]
        if all([any([os.path.exists(os.path.join(d, "lib%s.a" % lib)) for d in fft_lib_dirs]) for lib in fftw_libs]):
            self.FFT_LIB = fftw_libs
        else:
            msg = "Not all FFTW interface libraries %s are found in %s, can't set FFT_LIB." % (fftw_libs, fft_lib_dirs)
            self.log.error(msg)
