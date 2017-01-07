##
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
Support for IBM compilers (xlc, xlf) as toolchain compilers.

:author: Jack Perdue <j-perdue@tamu.edu> - TAMU HPRC - http://sc.tamu.edu
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
        'error-unknown-option': (False, "Error instead of warning for unknown options"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'optarch': 'qtune=auto',
        'openmp': 'qsmp=omp',
        'strict': ['', ''],
        'precise': [''],
        'defaultprec': ['', '', ''],
        'loose': [''],
        'veryloose': [''],
        'ibm-static': 'qstaticlink=xllibs',
        'pic': 'qpic',
        'shared': 'qmkshrobj',
    }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        (systemtools.POWER, systemtools.POWER): ['qtune=auto', 'qmaxmem=-1'],
        (systemtools.POWER, systemtools.POWER_LE): ['qtune=auto', 'qmaxmem=-1'],
    }

    COMPILER_CC = 'xlc'
    COMPILER_CXX = 'xlC'

    COMPILER_FC = 'xlf'
    COMPILER_F77 = 'xlf'
    COMPILER_F90 = 'xlf90'

    LINKER_TOGGLE_STATIC_DYNAMIC = {
        'static': '-Bstatic',
        'dynamic': '-Bdynamic',
    }

    LIB_MULTITHREAD = ['xlsmp']  # iomp5 is OpenMP related
