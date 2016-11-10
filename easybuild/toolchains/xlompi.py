##
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
EasyBuild support for xlompi compiler toolchain (includes IBM XL compilers (xlc, xlf) and OpenMPI).

:author: Jack Perdue <j-perdue@tamu.edu> - TAMU HPRC - http://sc.tamu.edu
"""
from easybuild.toolchains.compiler.ibmxl import IBMXL
from easybuild.toolchains.mpi.openmpi import OpenMPI


class Xlompi(IBMXL, OpenMPI):
    """
    Compiler toolchain with IBM XL compilers (xlc/xlf) and OpenMPI.
    """
    NAME = 'xlompi'
