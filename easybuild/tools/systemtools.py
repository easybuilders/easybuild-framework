##
# Copyright 2011-2015 Ghent University
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
import fcntl
import grp  # @UnresolvedImport
import os
import platform
import pwd
import re
import struct
import sys
import termios
from socket import gethostname
from vsc.utils import fancylogger
from vsc.utils.affinity import sched_getaffinity

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file, which
from easybuild.tools.run import run_cmd


_log = fancylogger.getLogger('systemtools', fname=False)

# constants
AMD = 'AMD'
ARM = 'ARM'
IBM = 'IBM'
INTEL = 'Intel'
POWER = 'POWER'

LINUX = 'Linux'
DARWIN = 'Darwin'

UNKNOWN = 'UNKNOWN'

MAX_FREQ_FP = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq'
PROC_CPUINFO_FP = '/proc/cpuinfo'

CPU_FAMILIES = [ARM, AMD, INTEL, POWER]
VENDORS = {
    'ARM': ARM,
    'AuthenticAMD': AMD,
    'GenuineIntel': INTEL,
    'IBM': IBM,
}


class SystemToolsException(Exception):
    """raised when systemtools fails"""


def get_avail_core_count():
    """
    Returns the number of available CPUs, according to cgroups and taskssets limits
    """
    core_cnt = None
    os_type = get_os_type()

    if os_type == LINUX:
        # simple use available sched_getaffinity() function (yields a long, so cast it down to int)
        core_cnt = int(sum(sched_getaffinity().cpus))
    else:
        # BSD-type systems
        out, _ = run_cmd('sysctl -n hw.ncpu', force_in_dry_run=True)
        try:
            if int(out) > 0:
                core_cnt = int(out)
        except ValueError:
            pass

    if core_cnt is None:
        raise SystemToolsException('Can not determine number of cores on this system')
    else:
        return core_cnt


def get_core_count():
    """NO LONGER SUPPORTED: use get_avail_core_count() instead"""
    _log.nosupport("get_core_count() is replaced by get_avail_core_count()", '2.0')


def get_cpu_vendor():
    """
    Try to detect the CPU vendor

    @return: a value from the VENDORS dict
    """
    vendor = None
    os_type = get_os_type()

    if os_type == LINUX and os.path.exists(PROC_CPUINFO_FP):
        txt = read_file(PROC_CPUINFO_FP)
        arch = UNKNOWN

        vendor_regex = re.compile(r"(vendor_id.*?)?\s*:\s*(?P<vendor>(?(1)\S+|(?:IBM|ARM)))")
        res = vendor_regex.search(txt)
        if res:
            arch = res.group('vendor')
        if arch in VENDORS:
            vendor = VENDORS[arch]
            _log.debug("Determined CPU vendor on Linux as being '%s' via regex '%s' in %s",
                       vendor, vendor_regex.pattern, PROC_CPUINFO_FP)

    elif os_type == DARWIN:
        cmd = "sysctl -n machdep.cpu.vendor"
        out, ec = run_cmd(cmd, force_in_dry_run=True)
        out = out.strip()
        if ec == 0 and out in VENDORS:
            vendor = VENDORS[out]
            _log.debug("Determined CPU vendor on DARWIN as being '%s' via cmd '%s" % (vendor, cmd))

    if vendor is None:
        vendor = UNKNOWN
        _log.warning("Could not determine CPU vendor on %s, returning %s" % (os_type, vendor))

    return vendor


def get_cpu_family():
    """
    Determine CPU family.
    @return: a value from the CPU_FAMILIES list
    """
    family = None
    vendor = get_cpu_vendor()
    if vendor in CPU_FAMILIES:
        family = vendor
        _log.debug("Using vendor as CPU family: %s" % family)

    else:
        # POWER family needs to be determined indirectly via 'cpu' in /proc/cpuinfo
        if os.path.exists(PROC_CPUINFO_FP):
            cpuinfo_txt = read_file(PROC_CPUINFO_FP)
            power_regex = re.compile(r"^cpu\s+:\s*POWER.*", re.M)
            if power_regex.search(cpuinfo_txt):
                family = POWER
                _log.debug("Determined CPU family using regex '%s' in %s: %s",
                           power_regex.pattern, PROC_CPUINFO_FP, family)

    if family is None:
        family = UNKNOWN
        _log.warning("Failed to determine CPU family, returning %s" % family)

    return family


def get_cpu_model():
    """
    Determine CPU model, e.g., Intel(R) Core(TM) i5-2540M CPU @ 2.60GHz
    """
    model = None
    os_type = get_os_type()

    if os_type == LINUX and os.path.exists(PROC_CPUINFO_FP):
        # we need 'model name' on Linux/x86, but 'model' is there first with different info
        # 'model name' is not there for Linux/POWER, but 'model' has the right info
        model_regex = re.compile(r"^model(?:\s+name)?\s+:\s*(?P<model>.*[A-Za-z].+)\s*$", re.M)
        txt = read_file(PROC_CPUINFO_FP)
        res = model_regex.search(txt)
        if res is not None:
            model = res.group('model').strip()
            _log.debug("Determined CPU model on Linux using regex '%s' in %s: %s",
                       model_regex.pattern, PROC_CPUINFO_FP, model)

    elif os_type == DARWIN:
        cmd = "sysctl -n machdep.cpu.brand_string"
        out, ec = run_cmd(cmd, force_in_dry_run=True)
        if ec == 0:
            model = out.strip()
            _log.debug("Determined CPU model on Darwin using cmd '%s': %s" % (cmd, model))

    if model is None:
        model = UNKNOWN
        _log.warning("Failed to determine CPU model, returning %s" % model)

    return model


def get_cpu_speed():
    """
    Returns the (maximum) cpu speed in MHz, as a float value.
    In case of throttling, the highest cpu speed is returns.
    """
    cpu_freq = None
    os_type = get_os_type()

    if os_type == LINUX:
        # Linux with cpu scaling
        if os.path.exists(MAX_FREQ_FP):
            _log.debug("Trying to determine CPU frequency on Linux via %s" % MAX_FREQ_FP)
            txt = read_file(MAX_FREQ_FP)
            cpu_freq = float(txt)/1000

        # Linux without cpu scaling
        elif os.path.exists(PROC_CPUINFO_FP):
            _log.debug("Trying to determine CPU frequency on Linux via %s" % PROC_CPUINFO_FP)
            cpuinfo_txt = read_file(PROC_CPUINFO_FP)
            # 'cpu MHz' on Linux/x86 (& more), 'clock' on Linux/POWER
            cpu_freq_regex = re.compile(r"^(?:cpu MHz|clock)\s*:\s*(?P<cpu_freq>\d+(?:\.\d+)?)", re.M)
            res = cpu_freq_regex.search(cpuinfo_txt)
            if res:
                cpu_freq = float(res.group('cpu_freq'))
                _log.debug("Found CPU frequency using regex '%s': %s" % (cpu_freq_regex.pattern, cpu_freq))
            else:
                _log.debug("Failed to determine CPU frequency from %s", PROC_CPUINFO_FP)
        else:
            _log.debug("%s not found to determine max. CPU clock frequency without CPU scaling: %s" % PROC_CPUINFO_FP)

    elif os_type == DARWIN:
        cmd = "sysctl -n hw.cpufrequency_max"
        _log.debug("Trying to determine CPU frequency on Darwin via cmd '%s'" % cmd)
        out, ec = run_cmd(cmd, force_in_dry_run=True)
        if ec == 0:
            # returns clock frequency in cycles/sec, but we want MHz
            cpu_freq = float(out.strip())/(1000**2)

    else:
        raise SystemToolsException("Could not determine CPU clock frequency (OS: %s)." % os_type)

    return cpu_freq


def get_kernel_name():
    """NO LONGER SUPPORTED: use get_os_type() instead"""
    _log.nosupport("get_kernel_name() is replaced by get_os_type()", '2.0')


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
    # platform.linux_distribution is more useful, but only available since Python 2.6
    # this allows to differentiate between Fedora, CentOS, RHEL and Scientific Linux (Rocks is just CentOS)
    os_name = platform.linux_distribution()[0].strip().lower()

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
                raise EasyBuildError("Don't know how to determine subversions for SLES %s", os_version)

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
    found = None
    cmd = None
    if which('rpm'):
        cmd = "rpm -q %s" % dep
        found = run_cmd(cmd, simple=True, log_all=False, log_ok=False, force_in_dry_run=True)

    if not found and which('dpkg'):
        cmd = "dpkg -s %s" % dep
        found = run_cmd(cmd, simple=True, log_all=False, log_ok=False, force_in_dry_run=True)

    if cmd is None:
        # fallback for when os-dependency is a binary/library
        found = which(dep)

        # try locate if it's available
        if not found and which('locate'):
            cmd = 'locate --regexp "/%s$"' % dep
            found = run_cmd(cmd, simple=True, log_all=False, log_ok=False, force_in_dry_run=True)

    return found


def get_tool_version(tool, version_option='--version'):
    """
    Get output of running version option for specific command line tool.
    Output is returned as a single-line string (newlines are replaced by '; ').
    """
    out, ec = run_cmd(' '.join([tool, version_option]), simple=False, log_ok=False, force_in_dry_run=True)
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
            raise EasyBuildError("Failed to determine glibc version from '%s' using pattern '%s'.",
                                 glibc_ver_str, glibc_ver_regex.pattern)
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
        'os_name': get_os_name(),
        'os_type': get_os_type(),
        'os_version': get_os_version(),
        'platform_name': get_platform_name(),
        'python_version': python_version,
        'system_python_path': which('python'),
        'system_gcc_path': which('gcc'),
    }


def use_group(group_name):
    """Use group with specified name."""
    try:
        group_id = grp.getgrnam(group_name).gr_gid
    except KeyError, err:
        raise EasyBuildError("Failed to get group ID for '%s', group does not exist (err: %s)", group_name, err)

    group = (group_name, group_id)
    try:
        os.setgid(group_id)
    except OSError, err:
        err_msg = "Failed to use group %s: %s; " % (group, err)
        user = pwd.getpwuid(os.getuid()).pw_name
        grp_members = grp.getgrgid(group_id).gr_mem
        if user in grp_members:
            err_msg += "change the primary group before using EasyBuild, using 'newgrp %s'." % group_name
        else:
            err_msg += "current user '%s' is not in group %s (members: %s)" % (user, group, grp_members)
        raise EasyBuildError(err_msg)
    _log.info("Using group '%s' (gid: %s)" % group)

    return group


def det_parallelism(par=None, maxpar=None):
    """
    Determine level of parallelism that should be used.
    Default: educated guess based on # cores and 'ulimit -u' setting: min(# cores, ((ulimit -u) - 15) / 6)
    """
    if par is not None:
        if not isinstance(par, int):
            try:
                par = int(par)
            except ValueError, err:
                raise EasyBuildError("Specified level of parallelism '%s' is not an integer value: %s", par, err)
    else:
        par = get_avail_core_count()
        # check ulimit -u
        out, ec = run_cmd('ulimit -u', force_in_dry_run=True)
        try:
            if out.startswith("unlimited"):
                out = 2 ** 32 - 1
            maxuserproc = int(out)
            # assume 6 processes per build thread + 15 overhead
            par_guess = int((maxuserproc - 15) / 6)
            if par_guess < par:
                par = par_guess
                _log.info("Limit parallel builds to %s because max user processes is %s" % (par, out))
        except ValueError, err:
            raise EasyBuildError("Failed to determine max user processes (%s, %s): %s", ec, out, err)

    if maxpar is not None and maxpar < par:
        _log.info("Limiting parallellism from %s to %s" % (par, maxpar))
        par = min(par, maxpar)

    return par


def det_terminal_size():
    """
    Determine the current size of the terminal window.
    @return: tuple with terminal width and height
    """
    # see http://stackoverflow.com/questions/566746/how-to-get-console-window-width-in-python
    try:
        height, width, _, _ = struct.unpack('HHHH', fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0)))
    except Exception as err:
        _log.warning("First attempt to determine terminal size failed: %s", err)
        try:
            height, width = [int(x) for x in os.popen("stty size").read().strip().split()]
        except Exception as err:
            _log.warning("Second attempt to determine terminal size failed, going to return defaults: %s", err)
            height, width = 25, 80

    return height, width
