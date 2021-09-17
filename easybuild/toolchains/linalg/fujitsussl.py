##
# Copyright 2014-2021 Ghent University
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
Support for Fujitsu's SSL library, which provides BLAS/LAPACK support.

:author: Miguel Dias Costa (National University of Singapore)
"""
import os

from easybuild.toolchains.compiler.fujitsu import TC_CONSTANT_MODULE_NAME, TC_CONSTANT_MODULE_VAR
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.constants import COMPILER_FLAGS
from easybuild.tools.toolchain.linalg import LinAlg

FUJITSU_SSL_MODULE_NAME = None
TC_CONSTANT_FUJITSU_SSL = 'FujitsuSSL'


class FujitsuSSL(LinAlg):
    """Support for Fujitsu's SSL library, which provides BLAS/LAPACK support."""
    # BLAS/LAPACK support
    # via lang/tcsds module
    BLAS_MODULE_NAME = [TC_CONSTANT_MODULE_NAME]

    # no need to specify libraries nor includes, only the compiler flags below
    BLAS_LIB = ['']
    BLAS_LIB_MT = ['']
    BLAS_INCLUDE_DIR = ['']
    BLAS_FAMILY = TC_CONSTANT_FUJITSU_SSL

    LAPACK_MODULE_NAME = None
    LAPACK_IS_BLAS = True
    LAPACK_LIB = ['']
    LAPACK_LIB_MT = ['']
    LAPACK_INCLUDE_DIR = ['']
    LAPACK_FAMILY = TC_CONSTANT_FUJITSU_SSL

    BLACS_MODULE_NAME = None
    BLACS_LIB = ['']
    BLACS_LIB_MT = ['']
    BLACS_INCLUDE_DIR = ['']

    SCALAPACK_MODULE_NAME = BLAS_MODULE_NAME
    SCALAPACK_LIB = ['']
    SCALAPACK_LIB_MT = ['']
    SCALAPACK_INCLUDE_DIR = ['']
    SCALAPACK_FAMILY = TC_CONSTANT_FUJITSU_SSL

    def _get_software_root(self, name, required=True):
        """Get install prefix for specified software name; special treatment for Fujitsu modules."""
        if name == TC_CONSTANT_MODULE_NAME:
            env_var = TC_CONSTANT_MODULE_VAR
            root = os.getenv(env_var)
            if root is None:
                raise EasyBuildError("Failed to determine install prefix for %s via $%s", name, env_var)
            else:
                self.log.debug("Obtained install prefix for %s via $%s: %s", name, env_var, root)
        else:
            root = super(FujitsuSSL, self)._get_software_root(name, required=required)

        return root

    def _set_blas_variables(self):
        """Setting FujitsuSSL specific BLAS related variables"""
        super(FujitsuSSL, self)._set_blas_variables()
        if self.options.get('openmp', None):
            for flags_var, _ in COMPILER_FLAGS:
                self.variables.nappend(flags_var, ['SSL2BLAMP'])
        else:
            for flags_var, _ in COMPILER_FLAGS:
                self.variables.nappend(flags_var, ['SSL2'])

    def _set_scalapack_variables(self):
        """Setting FujitsuSSL specific SCALAPACK related variables"""
        super(FujitsuSSL, self)._set_scalapack_variables()
        for flags_var, _ in COMPILER_FLAGS:
            self.variables.nappend(flags_var, ['SCALAPACK'])

    def definition(self):
        """
        Filter BLAS module from toolchain definition.
        The SSL2 module is loaded indirectly (and versionless) via the lang module,
        and thus is not a direct toolchain component.
        """
        tc_def = super(FujitsuSSL, self).definition()
        tc_def['BLAS'] = []
        tc_def['LAPACK'] = []
        tc_def['SCALAPACK'] = []
        return tc_def

    def set_variables(self):
        """Set the variables"""
        self._set_blas_variables()
        self._set_lapack_variables()
        self._set_scalapack_variables()

        self.log.devel('set_variables: LinAlg variables %s', self.variables)

        super(FujitsuSSL, self).set_variables()
