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
Support for the Cray Programming Environment Wrappers (aka cc, CC, ftn).
The Cray compiler wrappers are actually way more than just a compiler drivers.

The basic concept is that the compiler driver knows how to invoke the true underlying
compiler with the compiler's specific options tuned to Cray systems.

That means that certain defaults are set that are specific to Cray's computers.

The compiler wrappers are quite similar to EB toolchains as they include
linker and compiler directives to use the Cray libraries for their MPI (and network drivers)
Cray's LibSci (BLAS/LAPACK et al), FFT library, etc.


@author: Petar Forai (IMP/IMBA, Austria)
@author: Kenneth Hoste (Ghent University)
"""
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.toolchain.compiler import Compiler
from easybuild.toolchains.compiler.gcc import Gcc
from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort


TC_CONSTANT_CRAYPEWRAPPER = "CRAYPEWRAPPER"


class CrayPEWrapper(Compiler):
    """Generic support for using Cray compiler wrappers"""

    # no toolchain components, so no modules to list here (empty toolchain definition w.r.t. components)
    # the PrgEnv and craype are loaded, but are not considered actual toolchain components
    COMPILER_MODULE_NAME = []
    COMPILER_FAMILY = TC_CONSTANT_CRAYPEWRAPPER

    COMPILER_UNIQUE_OPTS = {
        # FIXME: (kehoste) how is this different from the existing 'shared' toolchain option? just map 'shared' to '-dynamic'? (already done)
        'dynamic': (True, "Generate dynamically linked executables and libraries."),
        'mpich-mt': (False, "Directs the driver to link in an alternate version of the Cray-MPICH library which \
                             provides fine-grained multi-threading support to applications that perform \
                             MPI operations within threaded regions."),
        'usewrappedcompiler': (False, "Use the embedded compiler instead of the wrapper"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'pic': 'shared',
        'shared': 'dynamic',
        'static': 'static',
        'verbose': 'craype-verbose',
        'mpich-mt': 'craympich-mt',
    }

    COMPILER_CC = 'cc'
    COMPILER_CXX = 'CC'

    COMPILER_F77 = 'ftn'
    COMPILER_F90 = 'ftn'

    # FIXME (kehoste) hmmmm, really? then how do you control optimisation, precision when using the Cray wrappers?
    COMPILER_FLAGS = []  # we dont have this for the wrappers
    COMPILER_OPT_FLAGS = []  # or those
    COMPILER_PREC_FLAGS = []  # and those for sure not !

    # template and name suffix for PrgEnv module that matches this toolchain
    # e.g. 'gnu' => 'PrgEnv-gnu/<version>'
    PRGENV_MODULE_NAME_TEMPLATE = 'PrgEnv-%(suffix)s/%(version)s'
    PRGENV_MODULE_NAME_SUFFIX = None

    # template for craype module (determines code generator backend of Cray compiler wrappers)
    CRAYPE_MODULE_NAME_TEMPLATE = 'craype-%(optarch)s'

    def _pre_preprare(self):
        """Load PrgEnv module."""
        prgenv_mod_name = self.PRGENV_MODULE_NAME_TEMPLATE % {
            'suffix': self.PRGENV_MODULE_NAME_SUFFIX,
            'version': self.version,
        }
        self.log.info("Loading PrgEnv module '%s' for Cray toolchain %s" % (prgenv_mod_name, self.mod_short_name))
        self.modules_tool.load([prgenv_mod_name])

    def _set_optimal_architecture(self):
        """Load craype module specified via 'optarch' build option."""
        optarch = build_option('optarch')
        if optarch is None:
            raise EasyBuildError("Don't know which 'craype' module to load, 'optarch' build option is unspecified.")
        else:
            self.modules_tool.load([self.CRAYPE_MODULE_NAME_TEMPLATE % {'optarch': optarch}])

    # FIXME: (kehoste) is it really needed to customise this?
    # this looks like a workaround for setting the COMPILER_*_FLAGS lists empty?
    def _set_compiler_flags(self):
        """Collect the flags set, and add them as variables too"""

        flags = [self.options.option(x) for x in self.COMPILER_FLAGS if self.options.get(x, False)]
        cflags = [self.options.option(x) for x in self.COMPILER_C_FLAGS + self.COMPILER_C_UNIQUE_FLAGS \
                  if self.options.get(x, False)]
        fflags = [self.options.option(x) for x in self.COMPILER_F_FLAGS + self.COMPILER_F_UNIQUE_FLAGS \
                  if self.options.get(x, False)]


        # precflags last
        self.variables.nappend('CFLAGS', flags)
        self.variables.nappend('CFLAGS', cflags)

        self.variables.nappend('CXXFLAGS', flags)
        self.variables.nappend('CXXFLAGS', cflags)

        self.variables.nappend('FFLAGS', flags)
        self.variables.nappend('FFLAGS', fflags)

        self.variables.nappend('F90FLAGS', flags)
        self.variables.nappend('F90FLAGS', fflags)


# Gcc's base is Compiler
class CrayPEWrapperGNU(CrayPEWrapper):
    """Support for using the Cray GNU compiler wrappers."""
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_GNU'

    PRGENV_MODULE_NAME_SUFFIX = 'gnu'  # PrgEnv-gnu

    def _set_compiler_vars(self):
        """Set compiler variables, either for the compiler wrapper, or the underlying compiler."""
        if self.options.option('usewrappedcompiler'):
            self.log.info("Using underlying compiler, as specified by the %s class" % Gcc)

            comp_attrs = ['UNIQUE_OPTS', 'UNIQUE_OPTION_MAP', 'CC', 'CXX', 'C_UNIQUE_FLAGS',
                          'F77', 'F90', 'F_UNIQUE_FLAGS']
            for attr_name in ['COMPILER_%s' % a for a in comp_attrs]:
                setattr(self, attr_name, getattr(Gcc, attr_name))

        super(CrayPEWrapperGNU,self)._set_compiler_vars()


class CrayPEWrapperIntel(CrayPEWrapper):
    """Support for using the Cray Intel compiler wrappers."""
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_INTEL'

    PRGENV_MODULE_NAME_SUFFIX = 'intel'  # PrgEnv-intel

    def _set_compiler_flags(self):
        """Set compiler variables, either for the compiler wrapper, or the underlying compiler."""
        if self.options.option("usewrappedcompiler"):
            self.log.info("Using underlying compiler, as specified by the %s class" % IntelIccIfort)

            comp_attrs = ['UNIQUE_OPTS', 'UNIQUE_OPTION_MAP', 'CC', 'CXX', 'C_UNIQUE_FLAGS',
                          'F77', 'F90', 'F_UNIQUE_FLAGS']
            for attr_name in ['COMPILER_%s' % a for a in comp_attrs] + ['LINKER_TOGGLE_STATIC_DYNAMIC']:
                setattr(self, attr_name, getattr(IntelIccIfort, attr_name))

        super(CrayPEWrapperIntel, self).set_compiler_flags()


class CrayPEWrapperCray(CrayPEWrapper):
    """Support for using the Cray CCE compiler wrappers."""
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_CRAY'

    PRGENV_MODULE_NAME_SUFFIX = 'cray'  # PrgEnv-cray
