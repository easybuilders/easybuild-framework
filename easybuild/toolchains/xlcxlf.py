
"""
EasyBuild support for IBM XL compiler toolchain.

@author: Jack Perdue (Texas A & M University)
"""

from easybuild.toolchains.compiler.ibmxl import IBMXL

class XLCXLFToolchain(IBMXL):
    """Simple toolchain with just the IBM XL C and FORTRAN compilers."""
    NAME = 'xlcxlf'
