##
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
EasyBuild support for IBM XL compiler toolchain.

:author: Jack Perdue <j-perdue@tamu.edu> - TAMU HPRC - http://sc.tamu.edu
"""
from easybuild.toolchains.compiler.ibmxl import IBMXL

TC_CONSTANT_XLCXLF = "xlcxlf"


class XLCXLFToolchain(IBMXL):
    """Simple toolchain with just the IBM XL C and FORTRAN compilers."""
    NAME = 'xlcxlf'
    COMPILER_MODULE_NAME = ['xlc', 'xlf']
    COMPILER_FAMILY = TC_CONSTANT_XLCXLF
