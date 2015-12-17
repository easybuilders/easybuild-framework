##
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
EasyBuild support for xlmpich compiler toolchain (includes IBM XL compilers (xlc, xlf) and MPICH).

@author: Jack Perdue <j-perdue@tamu.edu> - TAMU HPRC - http://sc.tamu.edu
"""
from easybuild.toolchains.compiler.ibmxl import IBMXL
from easybuild.toolchains.mpi.mvapich2 import Mvapich2


class Xlompi(IBMXL, Mvapich2):
    """
    Compiler toolchain with IBM XL compilers (xlc/xlf) and MPICH.
    """
    NAME = 'xlmvapich2'
