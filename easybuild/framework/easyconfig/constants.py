#
# Copyright 2013-2025 Ghent University
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
#

"""
Easyconfig constants module that provides all constants that can
be used within an Easyconfig file.

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""
import os
import platform

from easybuild.base import fancylogger
from easybuild.tools.build_log import print_warning
from easybuild.tools.modules import MODULE_LOAD_ENV_HEADERS
from easybuild.tools.systemtools import KNOWN_ARCH_CONSTANTS, get_os_name, get_os_type, get_os_version


_log = fancylogger.getLogger('easyconfig.constants', fname=False)


EXTERNAL_MODULE_MARKER = 'EXTERNAL_MODULE'


def _get_arch_constant():
    """
    Get value for ARCH constant.
    """
    arch = platform.uname()[4]

    # macOS on Arm produces 'arm64' rather than 'aarch64'
    if arch == 'arm64':
        arch = 'aarch64'

    if arch not in KNOWN_ARCH_CONSTANTS:
        print_warning("Using unknown value for ARCH constant: %s", arch)

    return arch


# constants that can be used in easyconfig
EASYCONFIG_CONSTANTS = {
    'ARCH': (_get_arch_constant(), "CPU architecture of current system (aarch64, x86_64, ppc64le, ...)"),
    'EXTERNAL_MODULE': (EXTERNAL_MODULE_MARKER, "External module marker"),
    'HOME': (os.path.expanduser('~'), "Home directory ($HOME)"),
    'MODULE_LOAD_ENV_HEADERS': (MODULE_LOAD_ENV_HEADERS, "Environment variables with search paths to CPP headers"),
    'OS_TYPE': (get_os_type(), "System type (e.g. 'Linux' or 'Darwin')"),
    'OS_NAME': (get_os_name(), "System name (e.g. 'fedora' or 'RHEL')"),
    'OS_VERSION': (get_os_version(), "System version"),
    'SYS_PYTHON_VERSION': (platform.python_version(), "System Python version (platform.python_version())"),
    'SYSTEM': ({'name': 'system', 'version': 'system'}, "System toolchain"),

    'OS_PKG_IBVERBS_DEV': (('libibverbs-dev', 'libibverbs-devel', 'rdma-core-devel'),
                           "OS packages providing ibverbs/infiniband development support"),
    'OS_PKG_OPENSSL_BIN': (('openssl'),
                           "OS packages providing the openSSL binary"),
    'OS_PKG_OPENSSL_LIB': (('libssl', 'libopenssl'),
                           "OS packages providing openSSL libraries"),
    'OS_PKG_OPENSSL_DEV': (('openssl-devel', 'libssl-dev', 'libopenssl-devel'),
                           "OS packages providing openSSL development support"),
    'OS_PKG_PAM_DEV': (('pam-devel', 'libpam0g-dev'),
                       "OS packages providing Pluggable Authentication Module (PAM) development support"),
}

# Add EasyConfig constants to export list
globals().update({name: value for name, (value, _) in EASYCONFIG_CONSTANTS.items()})
__all__ = ['EXTERNAL_MODULE_MARKER', 'EASYCONFIG_CONSTANTS'] + list(EASYCONFIG_CONSTANTS.keys())
