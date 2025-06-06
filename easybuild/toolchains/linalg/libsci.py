##
# Copyright 2014-2025 Ghent University
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
##
"""
Support for Cray's LibSci library, which provides BLAS/LAPACK support.
cfr. https://www.nersc.gov/users/software/programming-libraries/math-libraries/libsci/

Authors:

* Petar Forai (IMP/IMBA, Austria)
* Kenneth Hoste (Ghent University)
"""
import os

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.linalg import LinAlg


CRAY_LIBSCI_MODULE_NAME = 'cray-libsci'
TC_CONSTANT_CRAY_LIBSCI = 'CrayLibSci'


class LibSci(LinAlg):
    """Support for Cray's LibSci library, which provides BLAS/LAPACK support."""
    # BLAS/LAPACK support
    # via cray-libsci module, which gets loaded via the PrgEnv module
    # see https://www.nersc.gov/users/software/programming-libraries/math-libraries/libsci/
    BLAS_MODULE_NAME = [CRAY_LIBSCI_MODULE_NAME]

    # no need to specify libraries, compiler driver takes care of linking the right libraries
    # FIXME: need to revisit this, on numpy we ended up with a serial BLAS through the wrapper.
    BLAS_LIB = ['']
    BLAS_LIB_MT = ['']
    BLAS_FAMILY = TC_CONSTANT_CRAY_LIBSCI

    LAPACK_MODULE_NAME = [CRAY_LIBSCI_MODULE_NAME]
    LAPACK_IS_BLAS = True
    LAPACK_FAMILY = TC_CONSTANT_CRAY_LIBSCI

    BLACS_MODULE_NAME = []
    SCALAPACK_MODULE_NAME = []

    def _get_software_root(self, name, required=True):
        """Get install prefix for specified software name; special treatment for Cray modules."""
        if name == 'cray-libsci':
            # Cray-provided LibSci module
            root = None
            # consider both $CRAY_LIBSCI_PREFIX_DIR and $CRAY_PE_LIBSCI_PREFIX_DIR,
            # cfr. https://github.com/easybuilders/easybuild-framework/issues/4536
            env_vars = ('CRAY_LIBSCI_PREFIX_DIR', 'CRAY_PE_LIBSCI_PREFIX_DIR')
            for env_var in env_vars:
                root = os.getenv(env_var, None)
                if root is not None:
                    self.log.debug("Obtained install prefix for %s via $%s: %s", name, env_var, root)
                    break

            if root is None:
                if required:
                    env_vars_str = ', '.join('$' + e for e in env_vars)
                    raise EasyBuildError("Failed to determine install prefix for %s via $%s", name, env_vars_str)
        else:
            root = super()._get_software_root(name, required=required)

        return root

    def _set_blacs_variables(self):
        """Skip setting BLACS related variables"""
        pass

    def _set_scalapack_variables(self):
        """Skip setting ScaLAPACK related variables"""
        pass

    def definition(self):
        """
        Filter BLAS module from toolchain definition.
        The cray-libsci module is loaded indirectly (and versionless) via the PrgEnv module,
        and thus is not a direct toolchain component.
        """
        tc_def = super().definition()
        tc_def['BLAS'] = []
        tc_def['LAPACK'] = []
        return tc_def
