##
# Copyright 2012-2018 Ghent University
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
Support for Intel FFTW as toolchain FFT library.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import os
from distutils.version import LooseVersion

from easybuild.tools.build_log import EasyBuildError, dry_run_warning
from easybuild.tools.config import build_option
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.tools.modules import get_software_root, get_software_version


class IntelFFTW(Fftw):
    """FFTW wrapper functionality of Intel MKL"""

    FFT_MODULE_NAME = ['imkl']

    FFT_LIB_GROUP = True
    FFT_LIB_STATIC = True

    def _set_fftw_variables(self):
        if not hasattr(self, 'BLAS_LIB_DIR'):
            raise EasyBuildError("_set_fftw_variables: IntelFFT based on IntelMKL (no BLAS_LIB_DIR found)")

        imklver = get_software_version(self.FFT_MODULE_NAME[0])

        picsuff = ''
        if self.options.get('pic', None):
            picsuff = '_pic'
        bitsuff = '_lp64'
        if self.options.get('i8', None):
            bitsuff = '_ilp64'
        compsuff = '_intel'
        if get_software_root('icc') is None:
            if get_software_root('PGI'):
                compsuff = '_pgi'
            elif get_software_root('GCC'):
                compsuff = '_gnu'
            else:
                raise EasyBuildError("Not using Intel compilers, PGI nor GCC, don't know compiler suffix for FFTW libraries.")

        interface_lib = "fftw3xc%s%s" % (compsuff, picsuff)
        fftw_libs = [interface_lib]
        cluster_interface_lib = None
        if self.options.get('usempi', False):
            # add cluster interface for recent imkl versions
            if LooseVersion(imklver) >= LooseVersion('10.3'):
                suff = picsuff
                if LooseVersion(imklver) >= LooseVersion('11.0.2'):
                    suff = bitsuff + suff
                cluster_interface_lib = 'fftw3x_cdft%s' % suff
                fftw_libs.append(cluster_interface_lib)
            fftw_libs.append("mkl_cdft_core")  # add cluster dft
            fftw_libs.extend(self.variables['LIBBLACS'].flatten()) # add BLACS; use flatten because ListOfList

        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())
        fftw_libs.extend(self.variables['LIBBLAS'].flatten())  # add BLAS libs (contains dft)
        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())

        self.FFT_LIB_DIR = self.BLAS_LIB_DIR
        self.FFT_INCLUDE_DIR = [os.path.join(d, 'fftw') for d in self.BLAS_INCLUDE_DIR]

        # building the FFTW interfaces is optional,
        # so make sure libraries are there before FFT_LIB is set
        imklroot = get_software_root(self.FFT_MODULE_NAME[0])
        fft_lib_dirs = [os.path.join(imklroot, d) for d in self.FFT_LIB_DIR]
        fftw_lib_exists = lambda x: any([os.path.exists(os.path.join(d, "lib%s.a" % x)) for d in fft_lib_dirs])
        if not fftw_lib_exists(interface_lib) and LooseVersion(imklver) >= LooseVersion("10.2"):
            # interface libs can be optional:
            # MKL >= 10.2 include fftw3xc and fftw3xf interfaces in LIBBLAS=libmkl_gf/libmkl_intel
            # See https://software.intel.com/en-us/articles/intel-mkl-main-libraries-contain-fftw3-interfaces
            # The cluster interface libs (libfftw3x_cdft*) can be omitted if the toolchain does not provide MPI-FFTW
            # interfaces.
            fftw_libs = [l for l in fftw_libs if l not in [interface_lib, cluster_interface_lib]]

        # filter out libraries from list of FFTW libraries to check for if they are not provided by Intel MKL
        check_fftw_libs = [lib for lib in fftw_libs if lib not in ['dl', 'gfortran']]

        if all([fftw_lib_exists(lib) for lib in check_fftw_libs]):
            self.FFT_LIB = fftw_libs
        else:
            msg = "Not all FFTW interface libraries %s are found in %s" % (check_fftw_libs, fft_lib_dirs)
            msg += ", can't set $FFT_LIB."
            if self.dry_run:
                dry_run_warning(msg, silent=build_option('silent'))
            else:
                raise EasyBuildError(msg)
