##
# Copyright 2012 Stijn De Weirdt
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
from distutils.version import LooseVersion
from easybuild.tools.toolchain.toolchain import Toolchain

class FFT(Toolchain):
    """General FFT-like class
        To provide FFT tools
    """

    FFT_MODULE_NAME = None
    FFT_LIB = None
    FFT_LIB_GROUP = False
    FFT_LIB_STATIC = False
    FFT_LIB_DIR = ['lib']
    FFT_INCLUDE_DIR = ['include']

    def __init__(self, *args, **kwargs):
        Toolchain.base_init(self)

        super(FFT, self).__init__(*args, **kwargs)

    def _set_fft_variables(self):
        """Set FFT variables"""
        root = self.get_software_root(self.FFT_MODULE_NAME[0]) ## TODO: deal with multiple modules properly


        fft_libs = self.variables.nappend('LIBFFT', self.FFT_LIB)
        self.variables.add_begin_end_linkerflags(fft_libs, toggle_startstopgroup=self.FFT_LIB_GROUP,
                                                 toggle_staticdynamic=self.FFT_LIB_STATIC)

        self.variables.append_exists('FFT_LIB_DIR', root, self.FFT_LIB_DIR)
        self.variables.append_exists('FFT_INC_DIR', root, self.FFT_INCLUDE_DIR)
        self.variables.join('FFT_STATIC_LIBS', 'LIBFFT')

        self._add_dependency_variables(self.FFT_MODULE_NAME)

    def set_variables(self):
        """Set the variables"""
        ## TODO is link order fully preserved with this order ?
        self._set_fft_variables()

        self.log.debug('set_variables: FFT variables %s' % self.variables)

        super(FFT, self).set_variables()

class FFTW(FFT):
    """FFTW FFT library"""
    FFT_MODULE_NAME = ['FFTW']

    def _set_fftw_variables(self):

        suffix = ''
        version = self.get_software_version(self.FFT_MODULE_NAME[0])
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

        super(FFTW, self)._set_fft_variables()

        ## TODO can these be replaced with the FFT ones?
        self.variables.join('FFTW_INC_DIR', 'FFT_INC_DIR')
        self.variables.join('FFTW_LIB_DIR', 'FFT_LIB_DIR')
        self.variables.join('FFTW_STATIC_LIBS', 'FFT_STATIC_LIBS')


class IntelFFTW(FFTW):
    """FFTW wrapperfunctionality of Intel MKL"""
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

if __name__ == '__main__':
    from vsc.fancylogger import setLogLevelDebug
    setLogLevelDebug()
    import os, sys
    from easybuild.tools.toolchain.compiler import IntelIccIfort, GNUCompilerCollection
    from easybuild.tools.toolchain.mpi import IntelMPI, OpenMPI
    from easybuild.tools.toolchain.scalapack import IntelMKL, ScaATLAS
    class ITC(IntelIccIfort, IntelMPI, IntelMKL, IntelFFTW):
        NAME = 'ITC'
        VERSION = '1.0.0'

    os.environ.setdefault('EBROOTICC', '/x/y/z/icc')
    os.environ.setdefault('EBROOTIFORT', '/x/y/z/ifort')
    os.environ.setdefault('EBROOTIMPI', '/x/y/z/impi')
    os.environ.setdefault('EBROOTIMKL', '/x/y/z/imkl')
    os.environ.setdefault('EBVERSIONICC', '2012.0.0.0')
    os.environ.setdefault('EBVERSIONIFORT', '2012.0.0.0')
    os.environ.setdefault('EBVERSIONIMPI', '4.1.0.0')
    os.environ.setdefault('EBVERSIONIMKL', '10.1.0.0')
    itc = ITC()
    itc.options['usempi'] = True
    itc.options['packed-linker-options'] = True
    itc.set_variables()
    itc.generate_vars()
#    print 'ITC', 'options', itc.options
#    print 'ITC', 'variables', itc.variables
#    print 'ITC', "vars", itc.show_variables(offset=" "*4, verbose=True)
    itc.show_variables(offset=" "*4, verbose=True)

    ## module load goalf
    class GMTC(GNUCompilerCollection, OpenMPI, ScaATLAS, FFTW):
        NAME = 'GMTC'
        VERSION = '1.0.0'
    gmtc = GMTC()
    gmtc.options['cstd'] = 'CVERYVERYSPECIAL'
    gmtc.options['pic'] = True
    gmtc.set_variables()
    gmtc.generate_vars()
#    print 'GMTC', 'options', gmtc.options
#    print 'GMTC', 'variables', gmtc.variables
#    print 'GMTC', "vars"
#    print gmtc.show_variables(offset=" "*4, verbose=True)
    gmtc.show_variables(offset=" "*4, verbose=True)



    itc.show_variables(offset=" "*4, verbose=False)
    gmtc.show_variables(offset=" "*4, verbose=False)

    """
    TODO
    LIBSCALAPACK=-Wl,--start-group -Wl,-Bstatic -lmkl_scalapack_lp64 -lmkl_solver_lp64_sequential -Wl,--end-group -Wl,-Bdynamic -lmkl_blacs_intelmpi_\
lp64 -Wl,--start-group -Wl,-Bstatic -lmkl_intel_lp64 -lmkl_sequential -lmkl_core -Wl,--end-group -Wl,-Bdynamic
    """
