
"""
Support for IBM compilers (xlc, xlf) as toolchain compilers.

@author: Jack Perdue (Texas A & M University)

"""

from distutils.version import LooseVersion

import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_IBMCOMP = "IBMXL"


class IBMXL(Compiler):

    COMPILER_MODULE_NAME = ['xlc', 'xlf']

    COMPILER_FAMILY = TC_CONSTANT_IBMCOMP
    COMPILER_UNIQUE_OPTS = {
        'ibm-static': (False, "Link IBM XL provided libraries statically"),
#        'no-icc': (False, "Don't set Intel specific macros"),
        'error-unknown-option': (False, "Error instead of warning for unknown options"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
#        'i8': '',
#        'r8': '',
        #'optarch': ['qtune=auto', 'cpu=Power7'],  # IBM XL - later
        #'optarch': 'qtune=auto',  # IBM XL - later
        'optarch': 'mcpu=native',  # IBM XL - later
#        'optarch': '',
        'openmp': 'qsmp=osmp',    # IBM XL - later
#        'openmp': '',
        'strict': ['', ''],
        'precise': [''],
        #'defaultprec': ['ftz', 'fp-speculation=safe', 'fp-model source'],
        'defaultprec': ['', '', ''],
        'loose': [''],
        'veryloose': [''],
        'ibm-static': 'qstaticlink=xllibs',  # IBM XL - later
        #'ibm-static': '',
#        'no-icc': 'no-icc',
        'error-unknown-option': 'we10006',  # error at warning #10006: ignoring unknown option
        'pic': 'qpic',  # override?
        'shared': 'qmkshrobj',  # override?
    }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        systemtools.POWER : ['qtune=auto', 'qmaxmem=-1'],
    }

    COMPILER_CC = 'xlc'
    COMPILER_CXX = 'xlC'
    #COMPILER_C_UNIQUE_FLAGS = ['ibm-static', 'no-icc']
    #COMPILER_C_UNIQUE_FLAGS = ['ibm-static']
    #COMPILER_C_UNIQUE_FLAGS = ['q64']  # controlled by "export OBJECT_MODE=64" for now

    COMPILER_FC = 'xlf'
    COMPILER_F77 = 'xlf'
    COMPILER_F90 = 'xlf90'
    #COMPILER_F_UNIQUE_FLAGS = ['ibm-static']
    #COMPILER_F_UNIQUE_FLAGS = ['q64']  # controlled by "export OBJECT_MODE=64" for now

    LINKER_TOGGLE_STATIC_DYNAMIC = {
        'static': '-Bstatic',
        'dynamic': '-Bdynamic',
    }

    LIB_MULTITHREAD = ['xlsmp', 'pthread']  # iomp5 is OpenMP related

    def _set_compiler_vars(self):
        """IBM XL compilers-specific adjustments after setting compiler variables."""
        super(IBMXL, self)._set_compiler_vars()

        if not ('xlc' in self.COMPILER_MODULE_NAME and 'xlf' in self.COMPILER_MODULE_NAME):
            self.log.raiseException("_set_compiler_vars: missing xlc and/or xlf from COMPILER_MODULE_NAME %s" % self.COMPILER_MODULE_NAME)

        xlc_root, _ = self.get_software_root(self.COMPILER_MODULE_NAME)
        xlc_version, xlf_version = self.get_software_version(self.COMPILER_MODULE_NAME)

        #if not xlf_version == xlc_version:
        #    msg = "_set_compiler_vars: mismatch between xlc version %s and xlf version %s"
        #    self.log.raiseException(msg % (xlc_version, xlf_version))

        #if LooseVersion(xlc_version) < LooseVersion('2011'):
        #    self.LIB_MULTITHREAD.insert(1, "guide")

        libpaths = ['FIXME']
        if self.options.get('32bit', None):
            libpaths.append('FIXME32')
        libpaths = ['lib/%s' % x for x in libpaths]
        if LooseVersion(xlc_version) > LooseVersion('2011.4') and LooseVersion(xlf_version) < LooseVersion('2013_sp1'):
            libpaths = ['compiler/%s' % x for x in libpaths]

        self.variables.append_subdirs("LDFLAGS", xlc_root, subdirs=libpaths)

# EOF
