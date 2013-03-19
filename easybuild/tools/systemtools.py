##
# Copyright 2011-2013 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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
Module with useful functions for getting system information

@author: Jens Timmerman (Ghent University)
"""
import os
import platform
import re
from vsc import fancylogger

from easybuild.tools.filetools import run_cmd


_log = fancylogger.getLogger('systemtools', fname=False)

INTEL = 'Intel'
AMD = 'AMD'


class SystemToolsException(Exception):
    """raised when systemtools fails"""

def get_core_count():
    """Try to detect the number of virtual or physical CPUs on this system.

    inspired by http://stackoverflow.com/questions/1006289/how-to-find-out-the-number-of-cpus-in-python/1006301#1006301
    """

    # Python 2.6+
    try:
        from multiprocessing import cpu_count
        return cpu_count()
    except (ImportError, NotImplementedError):
        pass

    # POSIX
    try:
        cores = int(os.sysconf('SC_NPROCESSORS_ONLN'))

        if cores > 0:
            return cores
    except (AttributeError, ValueError):
        pass

    # Linux
    try:
        res = open('/proc/cpuinfo').read().count('processor\t:')
        if res > 0:
            return res
    except IOError:
        pass

    # BSD
    try:
        out, _ = run_cmd('sysctl -n hw.ncpu')
        cores = int(out)

        if cores > 0:
            return cores
    except (ValueError):
        pass


    raise SystemToolsException('Can not determine number of cores on this system')

def get_cpu_vendor():
    """Try to detect the cpu identifier

    will return INTEL or AMD constant
    """
    regexp = re.compile(r"^vendor_id\s+:\s*(?P<vendorid>\S+)\s*$", re.M)
    VENDORS = {
        'GenuineIntel': INTEL,
        'AuthenticAMD': AMD,
    }

    # Linux
    try:
        arch = regexp.search(open("/proc/cpuinfo").read()).groupdict()['vendorid']
        if arch in VENDORS:
            return VENDORS[arch]
    except IOError:
        pass

    # Darwin (OS X)
    out, exitcode = run_cmd("sysctl -n machdep.cpu.vendor")
    out = out.strip()
    if not exitcode and out and out in VENDORS:
        return VENDORS[out]

    # BSD
    out, exitcode = run_cmd("sysctl -n hw.model")
    out = out.strip()
    if not exitcode and out:
        return out.split(' ')[0]

    raise SystemToolsException("Could not detect cpu vendor")

def get_cpu_model():
    """
    returns cpu model
    f.ex Intel(R) Core(TM) i5-2540M CPU @ 2.60GHz
    """
    #linux
    regexp = re.compile(r"^model name\s+:\s*(?P<modelname>.+)\s*$", re.M)
    try:
        return regexp.search(open("/proc/cpuinfo").read()).groupdict()['modelname'].strip()
    except IOError:
        pass
    #osX
    out, exitcode = run_cmd("sysctl -n machdep.cpu.brand_string")
    out = out.strip()
    if not exitcode:
        return out

    return 'UNKNOWN'

def get_kernel_name():
    """Try to determine kernel name

    e.g., 'Linux', 'Darwin', ...
    """
    _log.deprecated("get_kernel_name() (replaced by os_type())", "2.0")
    try:
        kernel_name = os.uname()[0]
        return kernel_name
    except OSError, err:
        raise SystemToolsException("Failed to determine kernel name: %s" % err)

def get_os_type():
    """Determine system type, e.g., 'Linux', 'Darwin', 'Java'."""
    os_type = platform.system()
    if len(os_type) > 0:
        return os_type
    else:
        raise SystemToolsException("Failed to determine system name using platform.system().")

def get_shared_lib_ext():
    """Determine extention for shared libraries

    Linux: 'so', Darwin: 'dylib'
    """
    shared_lib_exts = {
        'Linux': 'so',
        'Darwin': 'dylib'
    }

    os_type = get_os_type()
    if os_type in shared_lib_exts.keys():
        return shared_lib_exts[os_type]

    else:
        raise SystemToolsException("Unable to determine extention for shared libraries,"
                                   "unknown system name: %s" % os_type)

def get_platform_name(withversion=False):
    """Try and determine platform name
    e.g., x86_64-unknown-linux, x86_64-apple-darwin
    """
    os_type = get_os_type()
    release = platform.release()
    machine = platform.machine()

    if os_type == 'Linux':
        vendor = 'unknown'
        release = '-gnu'
    elif os_type == 'Darwin':
        vendor = 'apple'
    else:
        raise SystemToolsException("Failed to determine platform name, unknown system name: %s" % os_type)

    if withversion:
        platform_name = '%s-%s-%s%s' % (machine, vendor, os_type.lower(), release)
    else:
        platform_name = '%s-%s-%s' % (machine, vendor, os_type.lower())

    return platform_name

def get_os_name():
    """
    Determine system name, e.g., 'redhat' (generic), 'centos', 'debian', 'fedora', 'suse', 'ubuntu',
    'red hat enterprise linux server', 'SL' (Scientific Linux), 'opensuse', ...
    """
    try:
        # platform.linux_distribution is more useful, but only available since Python 2.6
        # this allows to differentiate between Fedora, CentOS, RHEL and Scientific Linux (Rocks is just CentOS)
        os_name = platform.linux_distribution()[0].strip().lower()
    except AttributeError, err:
        # platform.dist can be used as a fallback
        # CentOS, RHEL, Rocks and Scientific Linux may all appear as 'redhat' (especially if Python version is pre v2.6)
        os_name = platform.dist()[0].strip().lower()
        _log.deprecated("platform.dist as fallback for platform.linux_distribution", "2.0")

    os_name_map = {
        'red hat enterprise linux server': 'RHEL',
        'scientific linux sl': 'SL',
        'scientific linux': 'SL',
        'suse linux enterprise server': 'SLES',
    }

    if os_name:
        return os_name_map.get(os_name, os_name)
    else:
        return "UNKNOWN_SYSTEM_NAME"

def get_os_version():
    """Determine system version."""
    os_version = platform.dist()[1]
    if os_version:
        if get_os_name() in ["suse", "SLES"]:

            # SLES subversions can only be told apart based on kernel version,
            # see http://wiki.novell.com/index.php/Kernel_versions
            version_suffixes = {
                                "11": [
                                       ('2.6.27', ''),
                                       ('2.6.32', '_SP1'),
                                       ('3.0', '_SP2'),
                                      ],
                               }

            # append suitable suffix to system version
            if os_version in version_suffixes.keys():
                kernel_version = platform.uname()[2]
                known_sp = False
                for (kver, suff) in version_suffixes[os_version]:
                    if kernel_version.startswith(kver):
                        os_version += suff
                        known_sp = True
                        break
                if not known_sp:
                    suff = '_UNKNOWN_SP'
            else:
                _log.error("Don't know how to determine subversions for SLES %s" % os_version)

        return os_version
    else:
        return "UNKNOWN_SYSTEM_VERSION"

