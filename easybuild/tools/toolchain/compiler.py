# #
# Copyright 2012-2025 Ghent University
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
# #
"""
Toolchain compiler module, provides abstract class for compilers.

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
* Damian Alvarez (Forschungszentrum Juelich GmbH)
"""
from easybuild.tools import systemtools
from easybuild.tools.build_log import EasyBuildError, print_warning
from easybuild.tools.config import build_option
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES
from easybuild.tools.toolchain.toolchain import Toolchain

# default optimization 'level' (see COMPILER_SHARED_OPTION_MAP/COMPILER_OPT_OPTIONS)
DEFAULT_OPT_LEVEL = 'defaultopt'

# 'GENERIC' can  be used to enable generic compilation instead of optimized compilation (which is the default)
# by doing eb --optarch=GENERIC
OPTARCH_GENERIC = 'GENERIC'

# Characters that separate compilers and flags in --optarch
OPTARCH_SEP = ';'
OPTARCH_MAP_CHAR = ':'


def mk_infix(prefix):
    """Create an infix based on the given prefix."""
    infix = ''
    if prefix is not None:
        infix = '%s_' % prefix
    return infix


class Compiler(Toolchain):
    """General compiler-like class
        can't be used without creating new class C(Compiler,Toolchain)
    """

    COMPILER_MODULE_NAME = None

    COMPILER_FAMILY = None

    COMPILER_UNIQUE_OPTS = None
    COMPILER_SHARED_OPTS = {
        'cciscxx': (False, "Use CC as CXX"),  # also MPI
        'pic': (False, "Use PIC"),  # also FFTW
        'ieee': (False, "Adhere to IEEE-754 rules"),
        'noopt': (False, "Disable compiler optimizations"),
        'lowopt': (False, "Low compiler optimizations"),
        DEFAULT_OPT_LEVEL: (False, "Default compiler optimizations"),  # not set, but default
        'opt': (False, "High compiler optimizations"),
        'optarch': (True, "Enable architecture optimizations"),
        'strict': (False, "Strict (highest) precision"),
        'precise': (False, "High precision"),
        'defaultprec': (False, "Default precision"),  # not set, but default
        'loose': (False, "Loose precision"),
        'veryloose': (False, "Very loose precision"),
        'verbose': (False, "Verbose output"),
        'debug': (None, "Keep debug symbols"),  # default value set by build option keep-debug-symbols
        'i8': (False, "Integers are 8 byte integers"),  # fortran only -> no: MKL and icc give -DMKL_ILP64
        'r8': (False, "Real is 8 byte real"),  # fortran only
        'unroll': (False, "Unroll loops"),
        'cstd': (None, "Specify C standard"),
        'shared': (False, "Build shared library"),
        'static': (False, "Build static library"),
        'openmp': (False, "Enable OpenMP"),
        'vectorize': (None, "Enable compiler auto-vectorization, default except for noopt and lowopt"),
        'packed-linker-options': (False, "Pack the linker options as comma separated list"),  # ScaLAPACK mainly
        'rpath': (True, "Use RPATH wrappers when --rpath is enabled in EasyBuild configuration"),
        'search-path-cpp-headers': (None, "Search path used at build time for include directories"),
        'search-path-linker': (None, "Search path used at build time by the linker for libraries"),
        'extra_cflags': (None, "Specify extra CFLAGS options."),
        'extra_cxxflags': (None, "Specify extra CXXFLAGS options."),
        'extra_fflags': (None, "Specify extra FFLAGS options."),
        'extra_fcflags': (None, "Specify extra FCFLAGS options."),
        'extra_f90flags': (None, "Specify extra F90FLAGS options."),
    }

    COMPILER_UNIQUE_OPTION_MAP = None
    COMPILER_SHARED_OPTION_MAP = {
        DEFAULT_OPT_LEVEL: '-O2',
        'cstd': '-std=%(value)s',
        'debug': '-g',
        'lowopt': '-O1',
        'noopt': '-O0',
        'openmp': '-fopenmp',
        'opt': '-O3',
        'pic': '-fPIC',
        'shared': '-shared',
        'static': '-static',
        'unroll': '-unroll',
        'verbose': '-v',
        'extra_cflags': '%(value)s',
        'extra_cxxflags': '%(value)s',
        'extra_fflags': '%(value)s',
        'extra_fcflags': '%(value)s',
        'extra_f90flags': '%(value)s',
    }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = None
    COMPILER_GENERIC_OPTION = None

    COMPILER_OPTIONS = ['debug', 'ieee', 'openmp', 'pic', 'shared', 'static', 'unroll', 'verbose']  # any compiler
    COMPILER_OPT_OPTIONS = ['noopt', 'lowopt', DEFAULT_OPT_LEVEL, 'opt']  # optimisation args, ordered !
    COMPILER_PREC_OPTIONS = ['strict', 'precise', 'defaultprec', 'loose', 'veryloose']  # precision flags, ordered !

    COMPILER_CC = None
    COMPILER_CXX = None
    COMPILER_C_OPTIONS = ['cstd']
    COMPILER_C_UNIQUE_OPTIONS = []

    COMPILER_F77 = None
    COMPILER_F90 = None
    COMPILER_FC = None
    COMPILER_F_OPTIONS = ['i8', 'r8']
    COMPILER_F_UNIQUE_OPTIONS = []

    LINKER_TOGGLE_STATIC_DYNAMIC = None
    LINKER_TOGGLE_START_STOP_GROUP = {
        'start': '--start-group',
        'stop': '--end-group',
    }

    LIB_MULTITHREAD = None
    LIB_MATH = None
    LIB_RUNTIME = None

    def __init__(self, *args, **kwargs):
        """Compiler constructor."""
        Toolchain.base_init(self)
        self.arch = systemtools.get_cpu_architecture()
        self.cpu_family = systemtools.get_cpu_family()
        # list of compiler prefixes
        self.prefixes = []
        super().__init__(*args, **kwargs)

    def set_options(self, options):
        """Process compiler toolchain options."""
        self._set_compiler_toolchainoptions()
        self.log.devel('_compiler_set_options: compiler toolchain options %s', self.options)
        super().set_options(options)

    def set_variables(self):
        """Set the variables"""
        self._set_compiler_vars()
        self._set_optimal_architecture()
        self._set_compiler_flags()

        self.log.devel('set_variables: compiler variables %s', self.variables)
        super().set_variables()

    def _set_compiler_toolchainoptions(self):
        """Set the compiler related toolchain options"""
        # Initialize default value of debug symbols based on global build option
        if self.COMPILER_SHARED_OPTS and 'debug' in self.COMPILER_SHARED_OPTS:
            _, desc = self.COMPILER_SHARED_OPTS['debug']
            self.COMPILER_SHARED_OPTS['debug'] = (build_option('keep_debug_symbols'), desc)
        self.options.add_options(self.COMPILER_SHARED_OPTS, self.COMPILER_SHARED_OPTION_MAP)

        # always include empty infix first for non-prefixed compilers (e.g., GCC, Intel, ...)
        for infix in [''] + [mk_infix(prefix) for prefix in self.prefixes]:
            # overwrite/add unique compiler specific toolchainoptions
            self.options.add_options(
                getattr(self, 'COMPILER_%sUNIQUE_OPTS' % infix, None),
                getattr(self, 'COMPILER_%sUNIQUE_OPTION_MAP' % infix, None),
            )

    def _set_compiler_vars(self):
        """Set the compiler variables"""
        comp_var_tmpl_dict = {}

        # always include empty infix first for non-prefixed compilers (e.g., GCC, Intel, ...)
        for infix in [''] + [mk_infix(prefix) for prefix in self.prefixes]:

            for var_tuple in COMPILER_VARIABLES:
                var = var_tuple[0]  # [1] is the description

                # determine actual value for compiler variable
                compvar = 'COMPILER_%s%s' % (infix, var.upper())
                pref_var = infix + var
                value = getattr(self, compvar, None)

                if value is None:
                    if infix is None:
                        raise EasyBuildError("_set_compiler_vars: compiler variable %s undefined", var)
                    else:
                        # only warn if infix is set, not all languages may be supported (e.g., no Fortran for CUDA)
                        self.log.warning("_set_compiler_vars: %s compiler variable %s undefined", infix, var)

                self.variables[pref_var] = value

                # update dictionary to complete compiler variable template
                # to produce e.g. 'nvcc -ccbin=icpc' from 'nvcc -ccbin=%(CXX_base)'
                comp_var_tmpl_dict.update({
                    pref_var: str(self.variables[pref_var]),
                    '%s_base' % pref_var: str(self.variables[pref_var].get_first()),
                })

            # complete compiler templates for (prefixed) compiler, e.g. CUDA_CC="nvcc -ccbin=%(CXX_base)s"
            for var_tuple in COMPILER_VARIABLES:
                var = var_tuple[0]  # [1] is the description

                # determine actual value for compiler variable
                pref_var = infix + var
                val = self.options.option('_opt_%s' % pref_var, templatedict=comp_var_tmpl_dict)
                self.variables.nappend_el(pref_var, val)

            for (var, pos) in [('MULTITHREAD', 10), ('MATH', None), ('RUNTIME', None)]:
                lib = getattr(self, 'LIB_%s%s' % (infix, var), None)
                if lib is not None:
                    self.variables.nappend('LIBS', lib, position=pos)

        if self.options.get('cciscxx', None):
            self.log.debug("_set_compiler_vars: cciscxx set: switching CXX %s for CC value %s" %
                           (self.variables['CXX'], self.variables['CC']))
            self.variables['CXX'] = self.variables['CC']

    def _set_compiler_flags(self):
        """Collect the flags set, and add them as variables too"""
        variants = ['', '_F', '_F_UNIQUE', '_C', '_C_UNIQUE', '_OPT', '_PREC']
        for variant in variants:
            old_var = getattr(self, f'COMPILER{variant}_FLAGS', None)
            if old_var is not None:
                self.log.deprecated(f'COMPILER{variant}_FLAGS has been renamed to COMPILER{variant}_OPTIONS.', '6.0')
                setattr(self, f'COMPILER{variant}_OPTIONS', old_var)

        flags = [self.options.option(x) for x in self.COMPILER_OPTIONS if self.options.get(x, False)]
        cflags = [self.options.option(x) for x in self.COMPILER_C_OPTIONS + self.COMPILER_C_UNIQUE_OPTIONS
                  if self.options.get(x, False)]
        fflags = [self.options.option(x) for x in self.COMPILER_F_OPTIONS + self.COMPILER_F_UNIQUE_OPTIONS
                  if self.options.get(x, False)]

        # Allow a user-defined default optimisation
        default_opt_level = build_option('default_opt_level')
        if default_opt_level not in self.COMPILER_OPT_OPTIONS:
            raise EasyBuildError("Unknown value for default optimisation: %s (possibilities are %s)" %
                                 (default_opt_level, self.COMPILER_OPT_OPTIONS))

        # 1st one is the one to use. add default at the end so len is at least 1
        optflags = ([self.options.option(x) for x in self.COMPILER_OPT_OPTIONS if self.options.get(x, False)] +
                    [self.options.option(default_opt_level)])[:1]

        # Normal compiler flags need to include "-" starting with EB 5.0, check the first as a sanity check.
        # Avoiding all flags as there may be legitimate use for flags that lack -
        if optflags and optflags[0] and not optflags[0][0].startswith('-'):
            print_warning(f'Compiler flag "{optflags[0][0]}" does not start with a dash. See changes in EasyBuild 5.')

        # only apply if the vectorize toolchainopt is explicitly set
        # otherwise the individual compiler toolchain file should make sure that
        # vectorization is disabled for noopt and lowopt, and enabled otherwise.
        if self.options.get('vectorize') is not None:
            vectoptions = self.options.option('vectorize')
            vectflags = vectoptions[self.options['vectorize']]
            # avoid double use of such flags, or e.g. -fno-tree-vectorize followed by -ftree-vectorize
            if isinstance(optflags[0], list):
                optflags[0] = [flag for flag in optflags[0] if flag not in vectoptions.values()]
            optflags.append(vectflags)

        optarchflags = []
        if build_option('optarch') == OPTARCH_GENERIC:
            # don't take 'optarch' toolchain option into account when --optarch=GENERIC is used,
            # *always* include the flags that correspond to generic compilation (which are listed in 'optarch' option)
            optarchflags.append(self.options.option('optarch'))
        elif self.options.get('optarch', False):
            optarchflags.append(self.options.option('optarch'))

        precflags = [self.options.option(x) for x in self.COMPILER_PREC_OPTIONS if self.options.get(x, False)] + \
                    [self.options.option('defaultprec')]

        self.variables.nextend('OPTFLAGS', optflags + optarchflags)
        self.variables.nextend('PRECFLAGS', precflags[:1])

        # precflags last
        for var in ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']:
            self.variables.join(var, 'OPTFLAGS', 'PRECFLAGS')
            self.variables.nextend(var, flags)
            if var.startswith('C'):
                self.variables.nextend(var, cflags)
            else:
                self.variables.nextend(var, fflags)
            extra = 'extra_' + var.lower()
            if self.options.get(extra):
                extraflags = self.options.option(extra)
                if not extraflags or extraflags[0] != '-':
                    raise EasyBuildError("toolchainopts %s: '%s' must start with a '-'." % (extra, extraflags))
                self.variables.nappend_el(var, extraflags)

    def _set_optimal_architecture(self, default_optarch=None):
        """
        Get options for the current architecture

        :param default_optarch: default value to use for optarch, rather than using default value based on architecture
                                (--optarch and --optarch=GENERIC still override this value)
        """
        ec_optarch = self.options.get('optarch', False)
        if isinstance(ec_optarch, str):
            if OPTARCH_MAP_CHAR in ec_optarch:
                error_msg = "When setting optarch in the easyconfig (found %s), " % ec_optarch
                error_msg += "the <compiler%sflags> syntax is not allowed. " % OPTARCH_MAP_CHAR
                error_msg += "Use <flags> (omitting the first dash) for the specific compiler."
                raise EasyBuildError(error_msg)
            else:
                optarch = ec_optarch
        else:
            optarch = build_option('optarch')

        # --optarch is specified with flags to use
        if isinstance(optarch, dict):
            # optarch has been validated as complex string with multiple compilers and converted to a dictionary
            # first try module names, then the family in optarch
            current_compiler_names = (getattr(self, 'COMPILER_MODULE_NAME', []) +
                                      [getattr(self, 'COMPILER_FAMILY', None)])
            for current_compiler in current_compiler_names:
                if current_compiler in optarch:
                    optarch = optarch[current_compiler]
                    break
            # still a dict: no option for this compiler
            if isinstance(optarch, dict):
                optarch = None
                self.log.info("_set_optimal_architecture: no optarch found for compiler %s. Ignoring option.",
                              current_compiler)

        if isinstance(optarch, str):
            use_generic = (optarch == OPTARCH_GENERIC)
        elif optarch is None:
            use_generic = False
        else:
            raise EasyBuildError("optarch is neither an string or a dict %s. This should never happen", optarch)

        if use_generic:
            if (self.arch, self.cpu_family) in (self.COMPILER_GENERIC_OPTION or []):
                optarch = self.COMPILER_GENERIC_OPTION[(self.arch, self.cpu_family)]
            else:
                optarch = None
        # Specified optarch default value
        elif default_optarch and optarch is None:
            optarch = default_optarch
        # no --optarch specified, no option found for the current compiler, and no default optarch
        elif optarch is None and (self.arch, self.cpu_family) in (self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION or []):
            optarch = self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[(self.arch, self.cpu_family)]

        if optarch is not None:
            if optarch and not optarch.startswith('-'):
                self.log.deprecated(f'Specifying optarch "{optarch}" without initial dash is deprecated.', '6.0')
                # Add flags for backwards compatibility
                optarch = '-' + optarch

            optarch_log_str = optarch or 'no flags'
            self.log.info("_set_optimal_architecture: using %s as optarch for %s/%s.",
                          optarch_log_str, self.arch, self.cpu_family)
            self.options.options_map['optarch'] = optarch
        elif self.options.options_map.get('optarch', None) is None:
            optarch_flags_str = "%soptarch flags" % ('', 'generic ')[use_generic]
            error_msg = "Don't know how to set %s for %s/%s! " % (optarch_flags_str, self.arch, self.cpu_family)
            error_msg += "Use --optarch='<flags>' to override (see "
            error_msg += "https://docs.easybuild.io/controlling-compiler-optimization-flags/ "
            error_msg += "for details) and consider contributing your settings back (see "
            error_msg += "https://docs.easybuild.io/contributing/)."
            raise EasyBuildError(error_msg)

    def comp_family(self, prefix=None):
        """
        Return compiler family used in this toolchain.
        @prefix: Prefix for compiler (e.g. 'CUDA_').
        """
        infix = mk_infix(prefix)

        comp_family = getattr(self, 'COMPILER_%sFAMILY' % infix, None)
        if comp_family:
            return comp_family
        else:
            raise EasyBuildError("comp_family: COMPILER_%sFAMILY is undefined", infix)
