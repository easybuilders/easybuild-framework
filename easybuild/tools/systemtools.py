##
# Copyright 2011-2014 Ghent University
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
@auther: Ward Poelmans (Ghent University)
"""
import os
import platform
import re
import sys
from socket import gethostname
from vsc.utils import fancylogger
try:
    # this import fails with Python 2.4 because it requires the ctypes module (only in Python 2.5+)
    from vsc.utils.affinity import sched_getaffinity
except ImportError:
    pass

from easybuild.tools.filetools import read_file, which
from easybuild.tools.run import run_cmd


_log = fancylogger.getLogger('systemtools', fname=False)

# constants
AMD = 'AMD'
ARM = 'ARM'
INTEL = 'Intel'

LINUX = 'Linux'
DARWIN = 'Darwin'

UNKNOWN = 'UNKNOWN'


class SystemToolsException(Exception):
    """raised when systemtools fails"""


def get_avail_core_count():
    """
    Returns the number of available CPUs, according to cgroups and taskssets limits
    """
    # tiny inner function to help figure out number of available cores in a cpuset
    def count_bits(n):
        """Count the number of set bits for a given integer."""
        bit_cnt = 0
        while n > 0:
            n &= n - 1
            bit_cnt += 1
        return bit_cnt

    os_type = get_os_type()
    if os_type == LINUX:
        try:
            # the preferred approach is via sched_getaffinity (yields a long, so cast it down to int)
            num_cores = int(sum(sched_getaffinity().cpus))
            return num_cores
        except NameError:
            pass

        # in case sched_getaffinity isn't available, fall back to relying on /proc/cpuinfo

        # determine total number of cores via /proc/cpuinfo
        try:
            txt = read_file('/proc/cpuinfo', log_error=False)
            # sometimes this is uppercase
            max_num_cores = txt.lower().count('processor\t:')
        except IOError, err:
            raise SystemToolsException("An error occured while determining total core count: %s" % err)

        # determine cpuset we're in (if any)
        mypid = os.getpid()
        try:
            f = open("/proc/%s/status" % mypid, 'r')
            txt = f.read()
            f.close()
            cpuset = re.search("^Cpus_allowed:\s*([0-9,a-f]+)", txt, re.M | re.I)
        except IOError:
            cpuset = None

        if cpuset is not None:
            # use cpuset mask to determine actual number of available cores
            mask_as_int = long(cpuset.group(1).replace(',', ''), 16)
            num_cores_in_cpuset = count_bits((2**max_num_cores - 1) & mask_as_int)
            _log.info("In cpuset with %s CPUs" % num_cores_in_cpuset)
            return num_cores_in_cpuset
        else:
            _log.debug("No list of allowed CPUs found, not in a cpuset.")
            return max_num_cores
    else:
        # BSD
        try:
            out, _ = run_cmd('sysctl -n hw.ncpu')
            num_cores = int(out)
            if num_cores > 0:
                return num_cores
        except ValueError:
            pass

    raise SystemToolsException('Can not determine number of cores on this system')


def get_core_count():
    """
    Try to detect the number of virtual or physical CPUs on this system
    (DEPRECATED, use get_avail_core_count instead)
    """
    _log.deprecated("get_core_count() is deprecated, use get_avail_core_count() instead", '2.0')
    return get_avail_core_count()


def get_cpu_vendor():
    """Try to detect the cpu identifier

    will return INTEL, ARM or AMD constant
    """
    regexp = re.compile(r"^vendor_id\s+:\s*(?P<vendorid>\S+)\s*$", re.M)
    VENDORS = {
        'GenuineIntel': INTEL,
        'AuthenticAMD': AMD,
    }
    os_type = get_os_type()

    if os_type == LINUX:
        try:
            txt = read_file('/proc/cpuinfo', log_error=False)
            arch = UNKNOWN
            # vendor_id might not be in the /proc/cpuinfo, so this might fail
            res = regexp.search(txt)
            if res:
                arch = res.groupdict().get('vendorid', UNKNOWN)
            if arch in VENDORS:
                return VENDORS[arch]

            # some embeded linux on arm behaves differently (e.g. raspbian)
            regexp = re.compile(r"^Processor\s+:\s*(?P<vendorid>ARM\S+)\s*", re.M)
            res = regexp.search(txt)
            if res:
                arch = res.groupdict().get('vendorid', UNKNOWN)
            if ARM in arch:
                return ARM
        except IOError, err:
            raise SystemToolsException("An error occured while determining CPU vendor since: %s" % err)

    elif os_type == DARWIN:
        out, exitcode = run_cmd("sysctl -n machdep.cpu.vendor")
        out = out.strip()
        if not exitcode and out and out in VENDORS:
            return VENDORS[out]

    else:
        # BSD
        out, exitcode = run_cmd("sysctl -n hw.model")
        out = out.strip()
        if not exitcode and out:
            return out.split(' ')[0]

    return UNKNOWN


def get_cpu_model():
    """
    returns cpu model
    f.ex Intel(R) Core(TM) i5-2540M CPU @ 2.60GHz
    """
    os_type = get_os_type()
    if os_type == LINUX:
        regexp = re.compile(r"^model name\s+:\s*(?P<modelname>.+)\s*$", re.M)
        try:
            txt = read_file('/proc/cpuinfo', log_error=False)
            if txt is not None:
                return regexp.search(txt).groupdict()['modelname'].strip()
        except IOError, err:
            raise SystemToolsException("An error occured when determining CPU model: %s" % err)

    elif os_type == DARWIN:
        out, exitcode = run_cmd("sysctl -n machdep.cpu.brand_string")
        out = out.strip()
        if not exitcode:
            return out

    return UNKNOWN


def get_cpu_speed():
    """
    Returns the (maximum) cpu speed in MHz, as a float value.
    In case of throttling, the highest cpu speed is returns.
    """
    os_type = get_os_type()
    if os_type == LINUX:
        try:
            # Linux with cpu scaling
            max_freq_fp = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq'
            try:
                f = open(max_freq_fp, 'r')
                cpu_freq = float(f.read())/1000
                f.close()
                return cpu_freq
            except IOError, err:
                _log.warning("Failed to read %s to determine max. CPU clock frequency with CPU scaling: %s" % (max_freq_fp, err))

            # Linux without cpu scaling
            cpuinfo_fp = '/proc/cpuinfo'
            try:
                cpu_freq = None
                f = open(cpuinfo_fp, 'r')
                for line in f:
                    cpu_freq = re.match("^cpu MHz\s*:\s*([0-9.]+)", line)
                    if cpu_freq is not None:
                        break
                f.close()
                if cpu_freq is None:
                    raise SystemToolsException("Failed to determine CPU frequency from %s" % cpuinfo_fp)
                else:
                    return float(cpu_freq.group(1))
            except IOError, err:
                _log.warning("Failed to read %s to determine CPU clock frequency: %s" % (cpuinfo_fp, err))

        except (IOError, OSError), err:
            raise SystemToolsException("Determining CPU speed failed, exception occured: %s" % err)

    elif os_type == DARWIN:
        # OS X
        out, ec = run_cmd("sysctl -n hw.cpufrequency_max")
        # returns clock frequency in cycles/sec, but we want MHz
        mhz = float(out.strip())/(1000**2)
        if ec == 0:
            return mhz

    raise SystemToolsException("Could not determine CPU clock frequency (OS: %s)." % os_type)


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
        LINUX: 'so',
        DARWIN: 'dylib'
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

    if os_type == LINUX:
        vendor = 'unknown'
        release = '-gnu'
    elif os_type == DARWIN:
        vendor = 'apple'
    else:
        raise SystemToolsException("Failed to determine platform name, unknown system name: %s" % os_type)

    platform_name = '%s-%s-%s' % (machine, vendor, os_type.lower())
    if withversion:
        platform_name += release

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
    except AttributeError:
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
        return UNKNOWN


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
        return UNKNOWN


def check_os_dependency(dep):
    """
    Check if dependency is available from OS.
    """
    # - uses rpm -q and dpkg -s --> can be run as non-root!!
    # - fallback on which
    # - should be extended to files later?
    cmd = None
    if get_os_name() in ['debian', 'ubuntu']:
        if which('dpkg'):
            cmd = "dpkg -s %s" % dep
    else:
        # OK for get_os_name() == redhat, fedora, RHEL, SL, centos
        if which('rpm'):
            cmd = "rpm -q %s" % dep

    found = None
    if cmd is not None:
        found = run_cmd(cmd, simple=True, log_all=False, log_ok=False)

    if found is None:
        # fallback for when os-dependency is a binary/library
        found = which(dep)

    # try locate if it's available
    if found is None and which('locate'):
        cmd = 'locate --regexp "/%s$"' % dep
        found = run_cmd(cmd, simple=True, log_all=False, log_ok=False)

    return found


def get_tool_version(tool, version_option='--version'):
    """
    Get output of running version option for specific command line tool.
    Output is returned as a single-line string (newlines are replaced by '; ').
    """
    out, ec = run_cmd(' '.join([tool, version_option]), simple=False, log_ok=False)
    if ec:
        _log.warning("Failed to determine version of %s using '%s %s': %s" % (tool, tool, version_option, out))
        return UNKNOWN
    else:
        return '; '.join(out.split('\n'))


def get_glibc_version():
    """
    Find the version of glibc used on this system
    """
    os_type = get_os_type()

    if os_type == LINUX:
        glibc_ver_str = get_tool_version('ldd')
        glibc_ver_regex = re.compile(r"^ldd \([^)]*\) (\d[\d.]*).*$")
        res = glibc_ver_regex.search(glibc_ver_str)

        if res is not None:
            glibc_version = res.group(1)
            _log.debug("Found glibc version %s" % glibc_version)
            return glibc_version
        else:
            tup = (glibc_ver_str, glibc_ver_regex.pattern)
            _log.error("Failed to determine version from '%s' using pattern '%s'." % tup)
    else:
        # no glibc on OS X standard
        _log.debug("No glibc on a non-Linux system, so can't determine version.")
        return UNKNOWN


def get_system_info():
    """Return a dictionary with system information."""
    python_version = '; '.join(sys.version.split('\n'))
    return {
        'core_count': get_avail_core_count(),
        'cpu_model': get_cpu_model(),
        'cpu_speed': get_cpu_speed(),
        'cpu_vendor': get_cpu_vendor(),
        'gcc_version': get_tool_version('gcc', version_option='-v'),
        'hostname': gethostname(),
        'glibc_version': get_glibc_version(),
        'kernel_name': get_kernel_name(),
        'os_name': get_os_name(),
        'os_type': get_os_type(),
        'os_version': get_os_version(),
        'platform_name': get_platform_name(),
        'python_version': python_version,
        'system_python_path': which('python'),
        'system_gcc_path': which('gcc'),
    }
