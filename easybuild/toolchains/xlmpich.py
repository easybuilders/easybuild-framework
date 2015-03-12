##
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
EasyBuild support for xlmpich compiler toolchain (includes IBM XL compilers (xlc, xlf) and OpenMPI.

@author: Jack Perdue (Texas A&M University)
"""

from easybuild.toolchains.compiler.ibmxl import IBMXL
from easybuild.toolchains.mpi.mpich import Mpich

class Xlompi(IBMXL, Mpich):
    """
    Compiler toolchain with IBM XL compilers (xlc/xlf) and MPICH.
    """
    NAME = 'xlmpich'
# EOF
