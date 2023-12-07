##
# Copyright 2012-2023 Ghent University
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

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""
import os

from easybuild.tools import LooseVersion
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

        imklroot = get_software_root(self.FFT_MODULE_NAME[0])
        imklver = get_software_version(self.FFT_MODULE_NAME[0])
        self.FFT_LIB_DIR = self.BLAS_LIB_DIR
        self.FFT_INCLUDE_DIR = [os.path.join(d, 'fftw') for d in self.BLAS_INCLUDE_DIR]

        picsuff = ''
        if self.options.get('pic', None):
            picsuff = '_pic'
        bitsuff = '_lp64'
        if self.options.get('i8', None):
            bitsuff = '_ilp64'

        if get_software_root('icc') or get_software_root('intel-compilers'):
            compsuff = '_intel'
        elif get_software_root('PGI'):
            compsuff = '_pgi'
        elif get_software_root('GCC') or get_software_root('GCCcore'):
            compsuff = '_gnu'
        else:
            error_msg = "Not using Intel compilers, PGI nor GCC, don't know compiler suffix for FFTW libraries."
            raise EasyBuildError(error_msg)

        interface_lib = "fftw3xc%s%s" % (compsuff, picsuff)
        fft_lib_dirs = [os.path.join(imklroot, d) for d in self.FFT_LIB_DIR]

        def fftw_lib_exists(libname):
            """Helper function to check whether FFTW library with specified name exists."""
            return any(os.path.exists(os.path.join(d, "lib%s.a" % libname)) for d in fft_lib_dirs)

        # interface libs can be optional:
        # MKL >= 10.2 include fftw3xc and fftw3xf interfaces in LIBBLAS=libmkl_gf/libmkl_intel
        # See https://software.intel.com/en-us/articles/intel-mkl-main-libraries-contain-fftw3-interfaces
        # The cluster interface libs (libfftw3x_cdft*) can be omitted if the toolchain does not provide MPI-FFTW
        # interfaces.
        fftw_libs = []
        if fftw_lib_exists(interface_lib) or LooseVersion(imklver) < LooseVersion("10.2"):
            fftw_libs = [interface_lib]

        if self.options.get('usempi', False):
            # add cluster interface for recent imkl versions
            # only get cluster_interface_lib from seperate module imkl-FFTW, rest via libmkl_gf/libmkl_intel
            imklfftwroot = get_software_root('imkl-FFTW')
            if LooseVersion(imklver) >= LooseVersion('10.3') and (fftw_libs or imklfftwroot):
                suff = picsuff
                if LooseVersion(imklver) >= LooseVersion('11.0.2'):
                    suff = bitsuff + suff
                cluster_interface_lib = 'fftw3x_cdft%s' % suff
                fftw_libs.append(cluster_interface_lib)
            fftw_libs.append("mkl_cdft_core")  # add cluster dft
            fftw_libs.extend(self.variables['LIBBLACS'].flatten())  # add BLACS; use flatten because ListOfList
            if imklfftwroot:
                fft_lib_dirs += [os.path.join(imklfftwroot, 'lib')]
                self.FFT_LIB_DIR = [os.path.join(imklfftwroot, 'lib')]

        fftw_mt_libs = fftw_libs + [x % self.BLAS_LIB_MAP for x in self.BLAS_LIB_MT]

        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())
        fftw_libs.extend(self.variables['LIBBLAS'].flatten())  # add BLAS libs (contains dft)
        self.log.debug('fftw_libs %s' % fftw_libs.__repr__())

        # building the FFTW interfaces is optional,
        # so make sure libraries are there before FFT_LIB is set
        # filter out libraries from list of FFTW libraries to check for if they are not provided by Intel MKL
        check_fftw_libs = [lib for lib in fftw_libs + fftw_mt_libs if lib not in ['dl', 'gfortran']]

        missing_fftw_libs = [lib for lib in check_fftw_libs if not fftw_lib_exists(lib)]
        if missing_fftw_libs:
            msg = "Not all FFTW interface libraries %s are found in %s" % (check_fftw_libs, fft_lib_dirs)
            msg += ", can't set $FFT_LIB. Missing: %s" % (missing_fftw_libs)
            if self.dry_run:
                dry_run_warning(msg, silent=build_option('silent'))
            else:
                raise EasyBuildError(msg)
        else:
            self.FFT_LIB = fftw_libs
            self.FFT_LIB_MT = fftw_mt_libs
