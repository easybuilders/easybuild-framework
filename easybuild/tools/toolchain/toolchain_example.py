##
# Copyright 2012 Stijn De Weirdt
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
Some simple examples of using toolchain

    requires 'module load goalf' environment
"""
from easybuild.tools.toolchain.utilities import search_toolchain

def basic_goalf():
    """Simple example of using toochain interface"""
    tc_class, all_tcs = search_toolchain('goalf')

    print ",".join([x.__name__ for x in all_tcs])

    tc = tc_class(version='1.0.0')
    tc.options['cstd'] = 'CVERYVERYSPECIAL'
    tc.options['pic'] = True
    tc.set_variables()
    tc.generate_vars()
    tc.show_variables(offset=" "*4, verbose=True)

def full_fft_test():
    """Full manual toolchain test
        For actual usage of toolchain, look at basic_goalf
    """
    import os
    from easybuild.tools.toolchain.compiler import IntelIccIfort, GNUCompilerCollection
    from easybuild.tools.toolchain.mpi import IntelMPI, OpenMPI
    from easybuild.tools.toolchain.scalapack import IntelMKL, ScaATLAS
    from easybuild.tools.toolchain.fft import IntelFFTW, FFTW
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

if __name__ == '__main__':
    from vsc.fancylogger import setLogLevelDebug
    setLogLevelDebug()

    basic_goalf()
    full_fft_test()
