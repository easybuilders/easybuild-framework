##
# Copyright 2011-2025 Ghent University
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
Module with useful functions for getting system information

Authors:

* Kenneth Hoste (Ghent University)
* Jens Timmerman (Ghent University)
* Ward Poelmans (Ghent University)
* Jasper Grimm (UoY)
* Jan Andre Reuter (Forschungszentrum Juelich GmbH)
* Caspar van Leeuwen (SURF)
"""
import csv
import ctypes
import errno
import fcntl
import grp  # @UnresolvedImport
import io
import os
import platform
import pwd
import re
import shutil
import struct
import sys
import termios
import warnings
from collections import OrderedDict
from ctypes.util import find_library
from socket import gethostname

# pkg_resources is provided by the setuptools Python package,
# which we really want to keep as an *optional* dependency
try:
    # catch & ignore deprecation warning when importing pkg_resources produced by setuptools
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        import pkg_resources
    HAVE_PKG_RESOURCES = True
except ImportError:
    HAVE_PKG_RESOURCES = False

# importlib.metadata only available in Python 3.10+ (which we take into account when using it)
try:
    import importlib.metadata
except ImportError:
    pass

try:
    # only needed on macOS, may not be available on Linux
    import ctypes.macholib.dyld
except ImportError:
    pass

from easybuild.base import fancylogger
from easybuild.tools import LooseVersion
from easybuild.tools.build_log import EasyBuildError, EasyBuildExit, print_warning
from easybuild.tools.config import IGNORE
from easybuild.tools.filetools import is_readable, read_file, which
from easybuild.tools.run import run_shell_cmd, subprocess_popen_text


_log = fancylogger.getLogger('systemtools', fname=False)


try:
    import distro
    HAVE_DISTRO = True
except ImportError as err:
    _log.debug("Failed to import 'distro' Python module: %s", err)
    HAVE_DISTRO = False

try:
    from archspec.cpu import host as archspec_cpu_host
    HAVE_ARCHSPEC = True
except ImportError as err:
    _log.debug("Failed to import 'archspec' Python module: %s", err)
    HAVE_ARCHSPEC = False


# Architecture constants
AARCH32 = 'AArch32'
AARCH64 = 'AArch64'
POWER = 'POWER'
X86_64 = 'x86_64'
RISCV32 = 'RISCV32'
RISCV64 = 'RISCV64'

# known values for ARCH constant (determined by _get_arch_constant in easybuild.framework.easyconfig.constants)
KNOWN_ARCH_CONSTANTS = ('aarch64', 'ppc64le', 'riscv64', 'x86_64')

ARCH_KEY_PREFIX = 'arch='

# Vendor constants
AMD = 'AMD'
APM = 'Applied Micro'
APPLE = 'Apple'
ARM = 'ARM'
BROADCOM = 'Broadcom'
CAVIUM = 'Cavium'
DEC = 'DEC'
IBM = 'IBM'
INFINEON = 'Infineon'
INTEL = 'Intel'
MARVELL = 'Marvell'
MOTOROLA = 'Motorola/Freescale'
NVIDIA = 'NVIDIA'
QUALCOMM = 'Qualcomm'

# Family constants
POWER_LE = 'POWER little-endian'
RISCV = 'RISC-V'

# OS constants
LINUX = 'Linux'
DARWIN = 'Darwin'

UNKNOWN = 'UNKNOWN'

ETC_OS_RELEASE = '/etc/os-release'
MAX_FREQ_FP = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq'
PROC_CPUINFO_FP = '/proc/cpuinfo'
PROC_MEMINFO_FP = '/proc/meminfo'

CPU_ARCHITECTURES = [AARCH32, AARCH64, POWER, RISCV32, RISCV64, X86_64]
CPU_FAMILIES = [AMD, ARM, INTEL, POWER, POWER_LE, RISCV]
CPU_VENDORS = [AMD, APM, APPLE, ARM, BROADCOM, CAVIUM, DEC, IBM, INTEL, MARVELL, MOTOROLA, NVIDIA, QUALCOMM]
# ARM implementer IDs (i.e., the hexadeximal keys) taken from ARMv8-A Architecture Reference Manual
# (ARM DDI 0487A.j, Section G6.2.102, Page G6-4493)
VENDOR_IDS = {
    '0x41': ARM,
    '0x42': BROADCOM,
    '0x43': CAVIUM,
    '0x44': DEC,
    '0x49': INFINEON,
    '0x4D': MOTOROLA,
    '0x4E': NVIDIA,
    '0x50': APM,
    '0x51': QUALCOMM,
    '0x56': MARVELL,
    '0x69': INTEL,
    'AuthenticAMD': AMD,
    'GenuineIntel': INTEL,
    'IBM': IBM,
    # IBM POWER9
    '8335-GTH': IBM,
    '8335-GTX': IBM,
}
# ARM Cortex part numbers from the corresponding ARM Processor Technical Reference Manuals,
# see http://infocenter.arm.com - Cortex-A series processors, Section "Main ID Register"
ARM_CORTEX_IDS = {
    '0xc05': 'Cortex-A5',
    '0xc07': 'Cortex-A7',
    '0xc08': 'Cortex-A8',
    '0xc09': 'Cortex-A9',
    '0xc0e': 'Cortex-A17',
    '0xc0f': 'Cortex-A15',
    '0xd03': 'Cortex-A53',
    '0xd07': 'Cortex-A57',
    '0xd08': 'Cortex-A72',
    '0xd09': 'Cortex-A73',
}

# OS package handler name constants
RPM = 'rpm'
DPKG = 'dpkg'
ZYPPER = 'zypper'

SYSTEM_TOOLS = {
    '7z': "extracting sources (.iso)",
    'bunzip2': "decompressing sources (.bz2, .tbz, .tbz2, ...)",
    DPKG: "checking OS dependencies (Debian, Ubuntu, ...)",
    'git': "downloading sources using 'git clone'",
    'gunzip': "decompressing source files (.gz, .tgz, ...)",
    'make': "build tool",
    'patch': "applying patch files",
    RPM: "checking OS dependencies (CentOS, RHEL, OpenSuSE, SLES, ...)",
    'sed': "runtime patching",
    'Slurm': "backend for --job (sbatch command)",
    'tar': "unpacking source files (.tar)",
    'unxz': "decompressing source files (.xz, .txz)",
    'unzip': "decompressing files (.zip)",
    ZYPPER: "checking OS dependencies (openSUSE)",
}

SYSTEM_TOOL_CMDS = {
    'Slurm': 'sbatch',
}

EASYBUILD_OPTIONAL_DEPENDENCIES = {
    'archspec': (None, "determining name of CPU microarchitecture"),
    'autopep8': (None, "auto-formatting for dumped easyconfigs"),
    'GC3Pie': ('gc3libs', "backend for --job"),
    'GitPython': ('git', "GitHub integration + using Git repository as easyconfigs archive"),
    'graphviz': ('graphviz', "rendering dependency graph with Graphviz: --dep-graph"),
    'keyring': (None, "storing GitHub token"),
    'pbs-python': ('pbs', "using Torque as --job backend"),
    'pycodestyle': (None, "code style checking: --check-style, --check-contrib"),
    'pysvn': (None, "using SVN repository as easyconfigs archive"),
    'python-graph-core': ('pygraph.classes.digraph', "creating dependency graph: --dep-graph"),
    'python-graph-dot': ('pygraph.readwrite.dot', "saving dependency graph as dot file: --dep-graph"),
    'python-hglib': ('hglib', "using Mercurial repository as easyconfigs archive"),
    'requests': (None, "fallback library for downloading files"),
    'Rich': (None, "eb command rich terminal output"),
    'PyYAML': ('yaml', "easystack files easyconfig format"),
    'setuptools': ('pkg_resources', "obtaining information on Python packages via pkg_resources module"),
}


class SystemToolsException(Exception):
    """raised when systemtools fails"""


def sched_getaffinity():
    """Determine list of available cores for current process."""
    cpu_mask_t = ctypes.c_ulong
    n_cpu_bits = 8 * ctypes.sizeof(cpu_mask_t)

    _libc_lib = find_library('c')
    _libc = ctypes.CDLL(_libc_lib, use_errno=True)

    pid = os.getpid()

    cpu_setsize = 1024  # Max number of CPUs currently detectable
    max_cpu_setsize = cpu_mask_t(-1).value // 4  # (INT_MAX / 2)
    # Limit it to something reasonable but still big enough
    max_cpu_setsize = min(max_cpu_setsize, 1e9)
    while cpu_setsize < max_cpu_setsize:
        n_mask_bits = cpu_setsize // n_cpu_bits

        class cpu_set_t(ctypes.Structure):
            """Class that implements the cpu_set_t struct."""
            _fields_ = [('bits', cpu_mask_t * n_mask_bits)]

        cs = cpu_set_t()
        ec = _libc.sched_getaffinity(pid, ctypes.sizeof(cpu_set_t), ctypes.pointer(cs))
        if ec == 0:
            _log.debug("sched_getaffinity for pid %s successful", pid)
            break
        elif ctypes.get_errno() != errno.EINVAL:
            raise EasyBuildError("sched_getaffinity failed for pid %s errno %s", pid, ctypes.get_errno())
        cpu_setsize *= 2

    if ec != 0:
        raise EasyBuildError("sched_getaffinity failed finding a large enough cpuset for pid %s", pid)

    cpus = []
    for bitmask in cs.bits:
        for _ in range(n_cpu_bits):
            cpus.append(bitmask & 1)
            bitmask >>= 1

    return cpus


def get_avail_core_count():
    """
    Returns the number of available CPUs, according to cgroups and taskssets limits
    """
    core_cnt = None
    os_type = get_os_type()

    if os_type == LINUX:
        # simple use available sched_getaffinity() function (yields a long, so cast it down to int)
        core_cnt = int(sum(sched_getaffinity()))
    else:
        # BSD-type systems
        res = run_shell_cmd('sysctl -n hw.ncpu', in_dry_run=True, hidden=True, with_hooks=False,
                            output_file=False, stream_output=False)
        try:
            if int(res.output) > 0:
                core_cnt = int(res.output)
        except ValueError:
            pass

    if core_cnt is None:
        raise SystemToolsException('Can not determine number of cores on this system')
    else:
        return core_cnt


def get_core_count():
    """NO LONGER SUPPORTED: use get_avail_core_count() instead"""
    _log.nosupport("get_core_count() is replaced by get_avail_core_count()", '2.0')


def get_total_memory():
    """
    Try to ascertain this node's total memory

    :return: total memory as an integer, specifically a number of megabytes
    """
    memtotal = None
    os_type = get_os_type()

    if os_type == LINUX and is_readable(PROC_MEMINFO_FP):
        _log.debug("Trying to determine total memory size on Linux via %s", PROC_MEMINFO_FP)
        meminfo = read_file(PROC_MEMINFO_FP)
        mem_mo = re.match(r'^MemTotal:\s*(\d+)\s*kB', meminfo, re.M)
        if mem_mo:
            memtotal = int(mem_mo.group(1)) // 1024

    elif os_type == DARWIN:
        cmd = "sysctl -n hw.memsize"
        _log.debug("Trying to determine total memory size on Darwin via cmd '%s'", cmd)
        res = run_shell_cmd(cmd, in_dry_run=True, hidden=True, with_hooks=False, output_file=False, stream_output=False)
        if res.exit_code == EasyBuildExit.SUCCESS:
            memtotal = int(res.output.strip()) // (1024**2)

    if memtotal is None:
        memtotal = UNKNOWN
        _log.warning("Failed to determine total memory, returning %s", memtotal)

    return memtotal


def get_cpu_architecture():
    """
    Try to detect the CPU architecture

    :return: a value from the CPU_ARCHITECTURES list
    """
    aarch32_regex = re.compile("arm.*")
    aarch64_regex = re.compile("(aarch64|arm64).*")
    power_regex = re.compile("ppc64.*")
    riscv32_regex = re.compile("riscv32.*")
    riscv64_regex = re.compile("riscv64.*")

    system, node, release, version, machine, processor = platform.uname()

    arch = UNKNOWN
    if machine == X86_64:
        arch = X86_64
    elif power_regex.match(machine):
        arch = POWER
    elif aarch64_regex.match(machine):
        arch = AARCH64
    elif aarch32_regex.match(machine):
        arch = AARCH32
    elif riscv64_regex.match(machine):
        arch = RISCV64
    elif riscv32_regex.match(machine):
        arch = RISCV32

    if arch == UNKNOWN:
        _log.warning("Failed to determine CPU architecture, returning %s", arch)
    else:
        _log.debug("Determined CPU architecture: %s", arch)

    return arch


def get_cpu_vendor():
    """
    Try to detect the CPU vendor

    :return: a value from the CPU_VENDORS list
    """
    vendor = None
    os_type = get_os_type()

    if os_type == LINUX:
        vendor_regex = None

        arch = get_cpu_architecture()
        if arch == X86_64:
            vendor_regex = re.compile(r"vendor_id\s+:\s*(\S+)")
        elif arch == POWER:
            vendor_regex = re.compile(r"model\s+:\s*((\w|-)+)")
        elif arch in [AARCH32, AARCH64]:
            vendor_regex = re.compile(r"CPU implementer\s+:\s*(\S+)")

        if vendor_regex and is_readable(PROC_CPUINFO_FP):
            vendor_id = None

            proc_cpuinfo = read_file(PROC_CPUINFO_FP)
            res = vendor_regex.search(proc_cpuinfo)
            if res:
                vendor_id = res.group(1)

            if vendor_id in VENDOR_IDS:
                vendor = VENDOR_IDS[vendor_id]
                _log.debug("Determined CPU vendor on Linux as being '%s' via regex '%s' in %s",
                           vendor, vendor_regex.pattern, PROC_CPUINFO_FP)

    elif os_type == DARWIN:
        cmd = "sysctl -n machdep.cpu.vendor"
        res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True, with_hooks=False,
                            output_file=False, stream_output=False)
        out = res.output.strip()
        if res.exit_code == EasyBuildExit.SUCCESS and out in VENDOR_IDS:
            vendor = VENDOR_IDS[out]
            _log.debug("Determined CPU vendor on DARWIN as being '%s' via cmd '%s" % (vendor, cmd))
        else:
            cmd = "sysctl -n machdep.cpu.brand_string"
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True, with_hooks=False,
                                output_file=False, stream_output=False)
            out = res.output.strip().split(' ')[0]
            if res.exit_code == EasyBuildExit.SUCCESS and out in CPU_VENDORS:
                vendor = out
                _log.debug("Determined CPU vendor on DARWIN as being '%s' via cmd '%s" % (vendor, cmd))

    if vendor is None:
        vendor = UNKNOWN
        _log.warning("Could not determine CPU vendor on %s, returning %s" % (os_type, vendor))

    return vendor


def get_cpu_family():
    """
    Determine CPU family.
    :return: a value from the CPU_FAMILIES list
    """
    family = None
    vendor = get_cpu_vendor()
    if vendor in CPU_FAMILIES:
        family = vendor
        _log.debug("Using vendor as CPU family: %s" % family)

    else:
        arch = get_cpu_architecture()
        if arch in [AARCH32, AARCH64]:
            # Custom ARM-based designs from other vendors
            family = ARM

        elif arch == POWER:
            family = POWER

            # Distinguish POWER running in little-endian mode
            system, node, release, version, machine, processor = platform.uname()
            powerle_regex = re.compile(r"^ppc(\d*)le")
            if powerle_regex.search(machine):
                family = POWER_LE

        elif arch in [RISCV32, RISCV64]:
            family = RISCV

    if family is None:
        family = UNKNOWN
        _log.warning("Failed to determine CPU family, returning %s" % family)

    return family


def get_cpu_arch_name():
    """
    Determine CPU architecture name via archspec (if available).
    """
    cpu_arch_name = None
    if HAVE_ARCHSPEC:
        res = archspec_cpu_host()
        if res:
            cpu_arch_name = str(res.name)

    if cpu_arch_name is None:
        cpu_arch_name = UNKNOWN

    return cpu_arch_name


def get_cpu_model():
    """
    Determine CPU model, e.g., Intel(R) Core(TM) i5-2540M CPU @ 2.60GHz
    """
    model = None
    os_type = get_os_type()

    if os_type == LINUX and is_readable(PROC_CPUINFO_FP):
        proc_cpuinfo = read_file(PROC_CPUINFO_FP)

        arch = get_cpu_architecture()
        if arch in [AARCH32, AARCH64]:
            # On ARM platforms, no model name is provided in /proc/cpuinfo.  However, for vanilla ARM cores
            # we can reverse-map the part number.
            vendor = get_cpu_vendor()
            if vendor == ARM:
                model_regex = re.compile(r"CPU part\s+:\s*(\S+)", re.M)
                # There can be big.LITTLE setups with different types of cores!
                model_ids = model_regex.findall(proc_cpuinfo)
                if model_ids:
                    id_list = []
                    for model_id in sorted(set(model_ids)):
                        id_list.append(ARM_CORTEX_IDS.get(model_id, UNKNOWN))
                    model = vendor + ' ' + ' + '.join(id_list)
                    _log.debug("Determined CPU model on Linux using regex '%s' in %s: %s",
                               model_regex.pattern, PROC_CPUINFO_FP, model)
        else:
            # we need 'model name' on Linux/x86, but 'model' is there first with different info
            # 'model name' is not there for Linux/POWER, but 'model' has the right info
            model_regex = re.compile(r"^model(?:\s+name)?\s+:\s*(?P<model>.*[A-Za-z].+)\s*$", re.M)
            res = model_regex.search(proc_cpuinfo)
            if res is not None:
                model = res.group('model').strip()
                _log.debug("Determined CPU model on Linux using regex '%s' in %s: %s",
                           model_regex.pattern, PROC_CPUINFO_FP, model)

    elif os_type == DARWIN:
        cmd = "sysctl -n machdep.cpu.brand_string"
        res = run_shell_cmd(cmd, in_dry_run=True, hidden=True, with_hooks=False, output_file=False, stream_output=False)
        if res.exit_code == EasyBuildExit.SUCCESS:
            model = res.output.strip()
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
        if is_readable(MAX_FREQ_FP):
            _log.debug("Trying to determine CPU frequency on Linux via %s" % MAX_FREQ_FP)
            txt = read_file(MAX_FREQ_FP)
            cpu_freq = float(txt) // 1000

        # Linux without cpu scaling
        elif is_readable(PROC_CPUINFO_FP):
            _log.debug("Trying to determine CPU frequency on Linux via %s" % PROC_CPUINFO_FP)
            proc_cpuinfo = read_file(PROC_CPUINFO_FP)
            # 'cpu MHz' on Linux/x86 (& more), 'clock' on Linux/POWER
            cpu_freq_regex = re.compile(r"^(?:cpu MHz|clock)\s*:\s*(?P<cpu_freq>\d+(?:\.\d+)?)", re.M)
            res = cpu_freq_regex.search(proc_cpuinfo)
            if res:
                cpu_freq = float(res.group('cpu_freq'))
                _log.debug("Found CPU frequency using regex '%s': %s" % (cpu_freq_regex.pattern, cpu_freq))
            else:
                _log.debug("Failed to determine CPU frequency from %s", PROC_CPUINFO_FP)
        else:
            _log.debug("%s not found to determine max. CPU clock frequency without CPU scaling", PROC_CPUINFO_FP)

    elif os_type == DARWIN:
        cmd = "sysctl -n hw.cpufrequency_max"
        _log.debug("Trying to determine CPU frequency on Darwin via cmd '%s'" % cmd)
        res = run_shell_cmd(cmd, in_dry_run=True, hidden=True, with_hooks=False, output_file=False, stream_output=False)
        out = res.output.strip()
        cpu_freq = None
        if res.exit_code == EasyBuildExit.SUCCESS and out:
            # returns clock frequency in cycles/sec, but we want MHz
            cpu_freq = float(out) // (1000 ** 2)

    else:
        raise SystemToolsException("Could not determine CPU clock frequency (OS: %s)." % os_type)

    return cpu_freq


def get_cpu_features():
    """
    Get list of CPU features
    """
    cpu_feat = []
    os_type = get_os_type()

    if os_type == LINUX:
        if is_readable(PROC_CPUINFO_FP):
            _log.debug("Trying to determine CPU features on Linux via %s", PROC_CPUINFO_FP)
            proc_cpuinfo = read_file(PROC_CPUINFO_FP)
            # 'flags' on Linux/x86, 'Features' on Linux/ARM
            flags_regex = re.compile(r"^(?:flags|[fF]eatures)\s*:\s*(?P<flags>.*)", re.M)
            res = flags_regex.search(proc_cpuinfo)
            if res:
                cpu_feat = sorted(res.group('flags').lower().split())
                _log.debug("Found CPU features using regex '%s': %s", flags_regex.pattern, cpu_feat)
            elif get_cpu_architecture() == POWER:
                # for Linux@POWER systems, no flags/features are listed, but we can check for Altivec
                cpu_altivec_regex = re.compile(r"^cpu\s*:.*altivec supported", re.M)
                if cpu_altivec_regex.search(proc_cpuinfo):
                    cpu_feat.append('altivec')
                # VSX is supported since POWER7
                cpu_power7_regex = re.compile(r"^cpu\s*:.*POWER(7|8|9)", re.M)
                if cpu_power7_regex.search(proc_cpuinfo):
                    cpu_feat.append('vsx')
            else:
                _log.debug("Failed to determine CPU features from %s", PROC_CPUINFO_FP)
        else:
            _log.debug("%s not found to determine CPU features", PROC_CPUINFO_FP)

    elif os_type == DARWIN:
        for feature_set in ['extfeatures', 'features', 'leaf7_features']:
            cmd = "sysctl -n machdep.cpu.%s" % feature_set
            _log.debug("Trying to determine CPU features on Darwin via cmd '%s'", cmd)
            res = run_shell_cmd(cmd, in_dry_run=True, hidden=True, fail_on_error=False, with_hooks=False,
                                output_file=False, stream_output=False)
            if res.exit_code == EasyBuildExit.SUCCESS:
                cpu_feat.extend(res.output.strip().lower().split())

        cpu_feat.sort()

    else:
        raise SystemToolsException("Could not determine CPU features (OS: %s)" % os_type)

    return cpu_feat


def get_gpu_info():
    """
    Get the GPU info
    """
    if get_os_type() != LINUX:
        _log.info("Only know how to get GPU info on Linux, assuming no GPUs are present")
        return {}

    gpu_info = {}
    if not which('nvidia-smi', on_error=IGNORE):
        _log.info("nvidia-smi not found. Cannot detect NVIDIA GPUs")
    else:
        try:
            cmd = "nvidia-smi --query-gpu=gpu_name,driver_version --format=csv,noheader"
            _log.debug("Trying to determine NVIDIA GPU info on Linux via cmd '%s'", cmd)
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True, with_hooks=False,
                                output_file=False, stream_output=False)
            if res.exit_code == EasyBuildExit.SUCCESS:
                for line in res.output.strip().split('\n'):
                    nvidia_gpu_info = gpu_info.setdefault('NVIDIA', {})
                    nvidia_gpu_info.setdefault(line, 0)
                    nvidia_gpu_info[line] += 1
            else:
                _log.debug("None zero exit (%s) from nvidia-smi: %s", res.exit_code, res.output)
        except EasyBuildError as err:
            _log.debug("Exception was raised when running nvidia-smi: %s", err)
            _log.info("No NVIDIA GPUs detected")

    amdgpu_checked = False
    if not which('amd-smi', on_error=IGNORE):
        _log.info("amd-smi not found. Trying to detect AMD GPUs via rocm-smi")
    else:
        try:
            cmd = "amd-smi static --driver --board --asic --csv"
            _log.debug("Trying to determine AMD GPU info on Linux via cmd '%s'", cmd)
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True, with_hooks=False,
                                output_file=False, stream_output=False)
            if res.exit_code == EasyBuildExit.SUCCESS:
                csv_reader = csv.DictReader(io.StringIO(res.output.strip()))

                for row in csv_reader:
                    amd_card_series = row['product_name']
                    amd_card_device_id = row['device_id']
                    amd_card_gfx = row['target_graphics_version']
                    amd_card_driver = row['version']

                    amd_gpu = ("%s (device id: %s, gfx: %s, driver: %s)" %
                               (amd_card_series, amd_card_device_id, amd_card_gfx, amd_card_driver))
                    amd_gpu_info = gpu_info.setdefault('AMD', {})
                    amd_gpu_info.setdefault(amd_gpu, 0)
                    amd_gpu_info[amd_gpu] += 1
                amdgpu_checked = True
            else:
                _log.debug("None zero exit (%s) from amd-smi: %s.", res.exit_code, res.output)
        except EasyBuildError as err:
            _log.debug("Exception was raised when running amd-smi: %s", err)
            _log.info("No AMD GPUs detected via amd-smi.")
        except KeyError as err:
            _log.warning("Failed to extract AMD GPU info from amd-smi output: %s.", err)

    if not which('rocm-smi', on_error=IGNORE):
        _log.info("rocm-smi not found. Cannot detect AMD GPUs")
    elif not amdgpu_checked:
        try:
            cmd = "rocm-smi --showdriverversion --csv"
            _log.debug("Trying to determine AMD GPU driver on Linux via cmd '%s'", cmd)
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True, with_hooks=False,
                                output_file=False, stream_output=False)
            if res.exit_code == EasyBuildExit.SUCCESS:
                amd_driver = res.output.strip().split('\n')[1].split(',')[1]

            cmd = "rocm-smi --showproductname --csv"
            _log.debug("Trying to determine AMD GPU info on Linux via cmd '%s'", cmd)
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True, with_hooks=False,
                                output_file=False, stream_output=False)
            if res.exit_code == EasyBuildExit.SUCCESS:
                for line in res.output.strip().split('\n')[1:]:
                    amd_card_series = line.split(',')[1]
                    amd_card_model = line.split(',')[2]
                    amd_gpu = "%s (model: %s, driver: %s)" % (amd_card_series, amd_card_model, amd_driver)
                    amd_gpu_info = gpu_info.setdefault('AMD', {})
                    amd_gpu_info.setdefault(amd_gpu, 0)
                    amd_gpu_info[amd_gpu] += 1
            else:
                _log.debug("None zero exit (%s) from rocm-smi: %s", res.exit_code, res.output)
        except EasyBuildError as err:
            _log.debug("Exception was raised when running rocm-smi: %s", err)
            _log.info("No AMD GPUs detected")

    return gpu_info


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
    os_name = None

    # platform.linux_distribution was removed in Python 3.8,
    # see https://docs.python.org/2/library/platform.html#platform.linux_distribution
    if hasattr(platform, 'linux_distribution'):
        # this allows to differentiate between Fedora, CentOS, RHEL and Scientific Linux (Rocks is just CentOS)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=PendingDeprecationWarning)
            warnings.simplefilter("ignore", category=DeprecationWarning)
            os_name = platform.linux_distribution()[0].strip()

    # take into account that on some OSs, platform.distribution returns an empty string as OS name,
    # for example on OpenSUSE Leap 15.2
    if not os_name and HAVE_DISTRO:
        # distro package is the recommended alternative to platform.linux_distribution,
        # see https://pypi.org/project/distro
        os_name = distro.name()

    if not os_name and os.path.exists(ETC_OS_RELEASE):
        os_release_txt = read_file(ETC_OS_RELEASE)
        name_regex = re.compile('^NAME="?(?P<name>[^"\n]+)"?$', re.M)
        res = name_regex.search(os_release_txt)
        if res:
            os_name = res.group('name')

    os_name_map = {
        'red hat enterprise linux server': 'RHEL',
        'red hat enterprise linux': 'RHEL',  # RHEL8 has no server/client
        'scientific linux sl': 'SL',
        'scientific linux': 'SL',
        'suse linux enterprise server': 'SLES',
    }

    if os_name:
        return os_name_map.get(os_name.lower(), os_name)
    else:
        return UNKNOWN


def get_os_version():
    """Determine system version."""

    os_version = None

    # platform.dist was removed in Python 3.8
    if hasattr(platform, 'dist'):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=PendingDeprecationWarning)
            warnings.simplefilter("ignore", category=DeprecationWarning)
            os_version = platform.dist()[1]

    # take into account that on some OSs, platform.dist returns an empty string as OS version,
    # for example on OpenSUSE Leap 15.2
    if not os_version and HAVE_DISTRO:
        os_version = distro.version()

    if not os_version and os.path.exists(ETC_OS_RELEASE):
        os_release_txt = read_file(ETC_OS_RELEASE)
        version_regex = re.compile('^VERSION="?(?P<version>[^"\n]+)"?$', re.M)
        res = version_regex.search(os_release_txt)
        if res:
            os_version = res.group('version')
        else:
            # VERSION may not always be defined (for example on Gentoo),
            # fall back to VERSION_ID in that case
            version_regex = re.compile('^VERSION_ID="?(?P<version>[^"\n]+)"?$', re.M)
            res = version_regex.search(os_release_txt)
            if res:
                os_version = res.group('version')

    if os_version:
        # older SLES subversions can only be told apart based on kernel version,
        # see http://wiki.novell.com/index.php/Kernel_versions
        sles_version_suffixes = {
            '11': [
                ('2.6.27', ''),
                ('2.6.32', '_SP1'),
                ('3.0.101-63', '_SP4'),
                # not 100% correct, since early SP3 had 3.0.76 - 3.0.93, but close enough?
                ('3.0.101', '_SP3'),
                # SP2 kernel versions range from 3.0.13 - 3.0.101
                ('3.0', '_SP2'),
            ],

            '12': [
                ('3.12.28', ''),
                ('3.12.49', '_SP1'),
            ],
        }
        if get_os_name() in ['suse', 'SLES'] and os_version in sles_version_suffixes:
            # append suitable suffix to system version
            kernel_version = platform.uname()[2]
            for (kver, suff) in sles_version_suffixes[os_version]:
                if kernel_version.startswith(kver):
                    os_version += suff
                    break

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
    found = False
    cmd = None
    os_to_pkg_cmd_map = {
        'centos': RPM,
        'debian': DPKG,
        'opensuse': ZYPPER,
        'redhat': RPM,
        'rhel': RPM,
        'ubuntu': DPKG,
    }
    pkg_cmd_flag = {
        DPKG: '-s',
        RPM: '-q',
        ZYPPER: 'search -i',
    }
    os_name = get_os_name().lower().split(' ')[0]
    if os_name in os_to_pkg_cmd_map:
        pkg_cmds = [os_to_pkg_cmd_map[os_name]]
    else:
        pkg_cmds = [RPM, DPKG]

    for pkg_cmd in pkg_cmds:
        if which(pkg_cmd):
            cmd = ' '.join([
                # unset $LD_LIBRARY_PATH to avoid broken rpm command due to loaded dependencies
                # see https://github.com/easybuilders/easybuild-easyconfigs/pull/4179
                'unset LD_LIBRARY_PATH &&',
                pkg_cmd,
                pkg_cmd_flag.get(pkg_cmd),
                dep,
            ])
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True,
                                output_file=False, stream_output=False)
            found = res.exit_code == EasyBuildExit.SUCCESS
            if found:
                break

    if not found:
        # fallback for when os-dependency is a binary/library
        found = which(dep)

        # try locate if it's available
        if not found and which('locate'):
            cmd = 'locate -c --regexp "/%s$"' % dep
            res = run_shell_cmd(cmd, fail_on_error=False, in_dry_run=True, hidden=True,
                                output_file=False, stream_output=False)
            try:
                found = (res.exit_code == EasyBuildExit.SUCCESS and int(res.output.strip()) > 0)
            except ValueError:
                # Returned something else than an int -> Error
                found = False

    return found


def get_tool_version(tool, version_option='--version', ignore_ec=False):
    """
    Get output of running version option for specific command line tool.
    Output is returned as a single-line string (newlines are replaced by '; ').
    """
    res = run_shell_cmd(' '.join([tool, version_option]), fail_on_error=False, in_dry_run=True,
                        hidden=True, with_hooks=False, output_file=False, stream_output=False)
    if not ignore_ec and res.exit_code != EasyBuildExit.SUCCESS:
        _log.warning("Failed to determine version of %s using '%s %s': %s" % (tool, tool, version_option, res.output))
        return UNKNOWN
    else:
        return '; '.join(res.output.split('\n'))


def get_gcc_version():
    """
    Process `gcc --version` and return the GCC version.
    """
    res = run_shell_cmd('gcc --version', fail_on_error=False, in_dry_run=True, hidden=True,
                        output_file=False, stream_output=False)
    gcc_ver = None
    if res.exit_code != EasyBuildExit.SUCCESS:
        _log.warning("Failed to determine the version of GCC: %s", res.output)
        gcc_ver = UNKNOWN

    # Fedora: gcc (GCC) 5.1.1 20150618 (Red Hat 5.1.1-4)
    # Debian: gcc (Debian 4.9.2-10) 4.9.2
    find_version = re.search(r"^gcc\s+\([^)]+\)\s+(?P<version>[^\s]+)\s+", res.output)
    if find_version:
        gcc_ver = find_version.group('version')
        _log.debug("Found GCC version: %s from %s", res, res.output)
    else:
        # Apple likes to install clang but call it gcc. <insert rant about Apple>
        if get_os_type() == DARWIN:
            _log.warning("On recent version of Mac OS, gcc is actually clang, returning None as GCC version")
            gcc_ver = None
        else:
            raise EasyBuildError("Failed to determine the GCC version from: %s", res.output)

    return gcc_ver


def get_glibc_version():
    """
    Find the version of glibc used on this system
    """
    glibc_ver = UNKNOWN
    os_type = get_os_type()

    if os_type == LINUX:
        glibc_ver_str = get_tool_version('ldd')
        # note: get_tool_version replaces newlines with ';',
        # hence the use of ';' below after the expected glibc version
        glibc_ver_regex = re.compile(r"^ldd \(.+\) (\d[\d.]+);")
        res = glibc_ver_regex.search(glibc_ver_str)

        if res is not None:
            glibc_ver = res.group(1)
            _log.debug("Found glibc version %s" % glibc_ver)
        else:
            _log.warning("Failed to determine glibc version from '%s' using pattern '%s'.",
                         glibc_ver_str, glibc_ver_regex.pattern)
    else:
        # no glibc on OS X standard
        _log.debug("No glibc on a non-Linux system, so can't determine version.")

    return glibc_ver


def get_cuda_object_dump_raw(path):
    """
    Get raw ouput from command which extracts information from CUDA binary files in a human-readable format,
    or None for files containing no CUDA device code.
    See https://docs.nvidia.com/cuda/cuda-binary-utilities/index.html#cuobjdump
    """

    res = run_shell_cmd("file %s" % path, fail_on_error=False, hidden=True, output_file=False, stream_output=False)
    if res.exit_code != EasyBuildExit.SUCCESS:
        fail_msg = "Failed to run 'file %s': %s" % (path, res.output)
        _log.warning(fail_msg)

    # check that the file is an executable or object (shared library) or archive (static library)
    result = None
    if any(x in res.output for x in ['executable', 'object', 'archive']):
        # Make sure we have a cuobjdump command
        if not shutil.which('cuobjdump'):
            raise EasyBuildError("Failed to get object dump from CUDA file: cuobjdump command not found")
        cuda_cmd = f"cuobjdump {path}"
        res = run_shell_cmd(cuda_cmd, fail_on_error=False, hidden=True, output_file=False, stream_output=False)
        if res.exit_code == EasyBuildExit.SUCCESS:
            result = res.output
        else:
            # Check and report for the common case that this is simply not a CUDA binary, i.e. does not
            # contain CUDA device code
            no_device_code_match = re.search(r'does not contain device code', res.output)
            if no_device_code_match is not None:
                # File is a regular executable, object or library, but not a CUDA file
                msg = "'%s' does not appear to be a CUDA binary: cuobjdump failed to find device code in this file"
                _log.debug(msg, path)
            else:
                # This should not happen: there was no string saying this was NOT a CUDA file, yet no device code
                # was found at all
                msg = "Dumping CUDA binary file information for '%s' via '%s' failed! Output: '%s'"
                raise EasyBuildError(msg, path, cuda_cmd, res.output)

    return result


def get_cuda_architectures(path, section_type):
    """
    Get a sorted list of CUDA architectures supported in the file in 'path'.
    path: full path to a CUDA file
    section_type: the type of section in the cuobjdump output to check for architectures ('elf' or 'ptx')
    Returns None if no CUDA device code is present in the file
    """

    # Note that typical output for a cuobjdump call will look like this for device code:
    #
    # Fatbin elf code:
    # ================
    # arch = sm_90
    # code version = [1,7]
    # host = linux
    # compile_size = 64bit
    #
    # And for ptx code, it will look like this:
    #
    # Fatbin ptx code:
    # ================
    # arch = sm_90
    # code version = [8,1]
    # host = linux
    # compile_size = 64bit

    # Pattern to extract elf code architectures and ptx code architectures respectively
    code_regex = re.compile(f'Fatbin {section_type} code:\n=+\narch = sm_([0-9]+)([0-9][af]?)')

    # resolve symlinks
    if os.path.islink(path) and os.path.exists(path):
        path = os.path.realpath(path)

    cc_archs = None
    cuda_raw = get_cuda_object_dump_raw(path)
    if cuda_raw is not None:
        # extract unique device code architectures from raw dump
        code_matches = re.findall(code_regex, cuda_raw)
        if code_matches:
            # convert match tuples into unique list of cuda compute capabilities
            # e.g. [('8', '6'), ('8', '6'), ('9', '0')] -> ['8.6', '9.0']
            cc_archs = sorted(['.'.join(m) for m in set(code_matches)], key=LooseVersion)
        else:
            # Try to be clear in the warning... did we not find elf/ptx code sections at all? or was the arch missing?
            section_regex = re.compile(f'Fatbin {section_type} code')
            section_matches = re.findall(section_regex, cuda_raw)
            if section_matches:
                fail_msg = f"Found Fatbin {section_type} code section(s) in cuobjdump output for {path}, "
                fail_msg += "but failed to extract CUDA architecture"
            else:
                # In this case, the "Fatbin {section_type} code" section is simply missing from the binary
                # It is entirely possible for a CUDA binary to have only device code or only ptx code (and thus the
                # other section could be missing). However, considering --cuda-compute-capabilities is supposed to
                # generate both PTX and device code (at least for the highest CC in that list), it is unexpected
                # in an EasyBuild context and thus we print a warning
                fail_msg = f"Failed to find Fatbin {section_type} code section(s) in cuobjdump output for {path}."
            _log.warning(fail_msg)

    return cc_archs


def get_linked_libs_raw(path):
    """
    Get raw output from command that reports linked libraries for dynamically linked executables/libraries,
    or None for other types of files.
    """

    if os.path.islink(path):
        _log.debug(f"{path} is a symbolic link, so skipping check for linked libs")
        return None
    res = run_shell_cmd("file %s" % path, fail_on_error=False, hidden=True, output_file=False, stream_output=False)
    if res.exit_code != EasyBuildExit.SUCCESS:
        fail_msg = "Failed to run 'file %s': %s" % (path, res.output)
        _log.warning(fail_msg)

    os_type = get_os_type()

    # check whether specified path is a dynamically linked binary or a shared library
    if os_type == LINUX:
        # example output for dynamically linked binaries:
        #   /usr/bin/ls: ELF 64-bit LSB executable, x86-64, ..., dynamically linked (uses shared libs), ...
        # example output for shared libraries:
        #   /lib64/libc-2.17.so: ELF 64-bit LSB shared object, x86-64, ..., dynamically linked (uses shared libs), ...
        if "dynamically linked" in res.output:
            # determine linked libraries via 'ldd'
            linked_libs_cmd = "ldd %s" % path
        else:
            return None

    elif os_type == DARWIN:
        # example output for dynamically linked binaries:
        #   /bin/ls: Mach-O 64-bit executable x86_64
        # example output for shared libraries:
        #   /usr/lib/libz.dylib: Mach-O 64-bit dynamically linked shared library x86_64
        bin_lib_regex = re.compile('(Mach-O .* executable)|(dynamically linked)', re.M)
        if bin_lib_regex.search(res.output):
            linked_libs_cmd = "otool -L %s" % path
        else:
            return None
    else:
        raise EasyBuildError("Unknown OS type: %s", os_type)

    # take into account that 'ldd' may fail for strange reasons,
    # like printing 'not a dynamic executable' when not enough memory is available
    # (see also https://bugzilla.redhat.com/show_bug.cgi?id=1817111)
    res = run_shell_cmd(linked_libs_cmd, fail_on_error=False, hidden=True, output_file=False, stream_output=False)
    if res.exit_code == EasyBuildExit.SUCCESS:
        linked_libs_out = res.output
    else:
        fail_msg = "Determining linked libraries for %s via '%s' failed! Output: '%s'"
        print_warning(fail_msg % (path, linked_libs_cmd, res.output))
        linked_libs_out = None

    return linked_libs_out


def check_linked_shared_libs(path, required_patterns=None, banned_patterns=None):
    """
    Check for (lack of) patterns in linked shared libraries for binary/library at specified path.
    Uses 'ldd' on Linux and 'otool -L' on macOS to determine linked shared libraries.

    Returns True or False for dynamically linked binaries and shared libraries to indicate
    whether all patterns match and antipatterns don't match.

    Returns None if given path is not a dynamically linked binary or library.
    """
    if required_patterns is None:
        required_regexs = []
    else:
        required_regexs = [re.compile(p) if isinstance(p, str) else p for p in required_patterns]

    if banned_patterns is None:
        banned_regexs = []
    else:
        banned_regexs = [re.compile(p) if isinstance(p, str) else p for p in banned_patterns]

    # resolve symbolic links (unless they're broken)
    if os.path.islink(path) and os.path.exists(path):
        path = os.path.realpath(path)

    linked_libs_out = get_linked_libs_raw(path)
    if linked_libs_out is None:
        return None

    found_banned_patterns = []
    missing_required_patterns = []
    for regex in required_regexs:
        if not regex.search(linked_libs_out):
            missing_required_patterns.append(regex.pattern)

    for regex in banned_regexs:
        if regex.search(linked_libs_out):
            found_banned_patterns.append(regex.pattern)

    if missing_required_patterns:
        patterns = ', '.join("'%s'" % p for p in missing_required_patterns)
        _log.warning("Required patterns not found in linked libraries output for %s: %s", path, patterns)

    if found_banned_patterns:
        patterns = ', '.join("'%s'" % p for p in found_banned_patterns)
        _log.warning("Banned patterns found in linked libraries output for %s: %s", path, patterns)

    return not (found_banned_patterns or missing_required_patterns)


def locate_solib(libobj):
    """
    Return absolute path to loaded library using dlinfo
    Based on https://stackoverflow.com/a/35683698

    :param libobj: ctypes CDLL object
    """
    # early return if we're not on a Linux system
    if get_os_type() != LINUX:
        return None

    class LINKMAP(ctypes.Structure):
        _fields_ = [
            ("l_addr", ctypes.c_void_p),
            ("l_name", ctypes.c_char_p)
        ]

    libdl = ctypes.cdll.LoadLibrary(ctypes.util.find_library('dl'))

    dlinfo = libdl.dlinfo
    dlinfo.argtypes = ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p
    dlinfo.restype = ctypes.c_int

    libpointer = ctypes.c_void_p()
    dlinfo(libobj._handle, 2, ctypes.byref(libpointer))
    libpath = ctypes.cast(libpointer, ctypes.POINTER(LINKMAP)).contents.l_name

    return libpath.decode('utf-8')


def find_library_path(lib_filename):
    """
    Search library by file name in the system
    Return absolute path to existing libraries

    :param lib_filename: name of library file
    """

    lib_abspath = None
    os_type = get_os_type()

    try:
        lib_obj = ctypes.cdll.LoadLibrary(lib_filename)
    except OSError:
        _log.info("Library '%s' not found in host system", lib_filename)
    else:
        # ctypes.util.find_library only accepts unversioned library names
        if os_type == LINUX:
            # find path to library with dlinfo
            lib_abspath = locate_solib(lib_obj)
        elif os_type == DARWIN:
            # ctypes.macholib.dyld.dyld_find accepts file names and returns full path
            lib_abspath = ctypes.macholib.dyld.dyld_find(lib_filename)
        else:
            raise EasyBuildError("Unknown host OS type: %s", os_type)

        _log.info("Found absolute path to %s: %s", lib_filename, lib_abspath)

    return lib_abspath


def get_system_info():
    """Return a dictionary with system information."""
    python_version = '; '.join(sys.version.split('\n'))
    return {
        'core_count': get_avail_core_count(),
        'total_memory': get_total_memory(),
        'cpu_arch': get_cpu_architecture(),
        'cpu_arch_name': get_cpu_arch_name(),
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
    except KeyError as err:
        raise EasyBuildError("Failed to get group ID for '%s', group does not exist (err: %s)", group_name, err)

    group = (group_name, group_id)
    try:
        os.setgid(group_id)
    except OSError as err:
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
    Default: educated guess based on # cores and 'ulimit -u' setting: min(# cores, ((ulimit -u) - 15) // 6)
    """
    def get_default_parallelism():
        try:
            # Get cache value if any
            par = det_parallelism._default_parallelism
        except AttributeError:
            # No cache -> Calculate value from current system values
            par = get_avail_core_count()
            # determine max user processes via ulimit -u
            res = run_shell_cmd("ulimit -u", in_dry_run=True, hidden=True, output_file=False, stream_output=False)
            try:
                if res.output.startswith("unlimited"):
                    maxuserproc = 2 ** 32 - 1
                else:
                    maxuserproc = int(res.output)
            except ValueError as err:
                raise EasyBuildError(
                    "Failed to determine max user processes (%s, %s): %s", res.exit_code, res.output, err
                )
            # assume 6 processes per build thread + 15 overhead
            par_guess = (maxuserproc - 15) // 6
            if par_guess < par:
                par = par_guess
                _log.info("Limit parallel builds to %s because max user processes is %s", par, res.output)
            # Cache value
            det_parallelism._default_parallelism = par
        return par

    if par is None:
        par = get_default_parallelism()
    else:
        try:
            par = int(par)
        except ValueError as err:
            raise EasyBuildError("Specified level of parallelism '%s' is not an integer value: %s", par, err)

    if maxpar is not None and maxpar < par:
        if maxpar is False:
            maxpar = 1
        _log.info("Limiting parallelism from %s to %s", par, maxpar)
        par = maxpar

    return par


def det_terminal_size():
    """
    Determine the current size of the terminal window.
    :return: tuple with terminal width and height
    """
    # see http://stackoverflow.com/questions/566746/how-to-get-console-window-width-in-python
    try:
        height, width, _, _ = struct.unpack('HHHH', fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0)))
    except Exception as err:
        _log.warning("First attempt to determine terminal size failed: %s", err)
        try:
            height, width = [int(x) for x in subprocess_popen_text("stty size").communicate()[0].strip().split()]
        except Exception as err:
            _log.warning("Second attempt to determine terminal size failed, going to return defaults: %s", err)
            height, width = 25, 80

    return height, width


def check_python_version():
    """Check currently used Python version."""
    python_maj_ver = sys.version_info[0]
    python_min_ver = sys.version_info[1]
    python_ver = '%d.%d' % (python_maj_ver, python_min_ver)
    _log.info("Found Python version %s", python_ver)

    if python_maj_ver == 3:
        if python_min_ver < 6:
            raise EasyBuildError("Python 3.6 or higher is required, found Python %s", python_ver)
        else:
            _log.info("Running EasyBuild with Python 3 (version %s)", python_ver)
    elif python_maj_ver < 3:
        raise EasyBuildError("EasyBuild is not compatible with Python %s", python_ver)
    else:
        raise EasyBuildError("EasyBuild is not compatible (yet) with Python %s", python_ver)

    return (python_maj_ver, python_min_ver)


def pick_system_specific_value(description, options_or_value, allow_none=False):
    """Pick an entry for the current system when the input has multiple options

    :param description: Descriptive string about the value to be retrieved. Used for logging.
    :param options_or_value: Either a dictionary with options to choose from or a value of any other type
    :param allow_none: When True and no matching arch key was found, return None instead of an error

    :return options_or_value when it is not a dictionary or the matching entry (if existing)
    """
    result = options_or_value
    if isinstance(options_or_value, dict):
        if not options_or_value:
            raise EasyBuildError("Found empty dict as %s!", description)
        other_keys = [x for x in options_or_value.keys() if not x.startswith(ARCH_KEY_PREFIX)]
        if other_keys:
            other_keys = ','.join(sorted(other_keys))
            raise EasyBuildError("Unexpected keys in %s: %s (only '%s' keys are supported)",
                                 description, other_keys, ARCH_KEY_PREFIX)
        host_arch_key = ARCH_KEY_PREFIX + get_cpu_architecture()
        star_arch_key = ARCH_KEY_PREFIX + '*'
        # check for specific 'arch=' key first
        try:
            result = options_or_value[host_arch_key]
            _log.info("Selected %s from %s for %s (using key %s)",
                      result, options_or_value, description, host_arch_key)
        except KeyError:
            # fall back to 'arch=*'
            try:
                result = options_or_value[star_arch_key]
                _log.info("Selected %s from %s for %s (using fallback key %s)",
                          result, options_or_value, description, star_arch_key)
            except KeyError:
                if allow_none:
                    result = None
                else:
                    raise EasyBuildError("No matches for %s in %s (looking for %s)",
                                         description, options_or_value, host_arch_key)
    return result


def pick_dep_version(dep_version):
    """
    Pick the correct dependency version to use for this system.
    Input can either be:
    * a string value (or None)
    * a dict with options to choose from

    Return value is the version to use or False to skip this dependency.
    """
    if dep_version is None:
        _log.debug("Version is None, OK")
        result = None
    else:
        result = pick_system_specific_value("version", dep_version)
        if not isinstance(result, str) and result is not False:
            typ = type(dep_version)
            raise EasyBuildError("Unknown value type for version: %s (%s), should be string value", typ, dep_version)

    return result


def det_pypkg_version(pkg_name, imported_pkg, import_name=None):
    """Determine version of a Python package."""

    version = None

    # prefer using importlib.metadata, since pkg_resources is deprecated since setuptools v68.0.0
    # and is scheduled to be removed in November 2025; see also https://github.com/pypa/setuptools/pull/5007

    raised_error = None

    # figure out which function to use to determine module/package version,
    # and which error may be raised if the name is unknown
    if check_python_version() >= (3, 10):

        def _get_version(name):
            return importlib.metadata.version(name)

        raised_error = importlib.metadata.PackageNotFoundError

    elif HAVE_PKG_RESOURCES:

        def _get_version(name):
            return pkg_resources.get_distribution(name).version

        raised_error = pkg_resources.DistributionNotFound

    if raised_error is not None:
        if import_name:
            try:
                version = _get_version(import_name)
            except raised_error as err:
                _log.debug("%s Python package not found: %s", import_name, err)

        if version is None:
            try:
                version = _get_version(pkg_name)
            except raised_error as err:
                _log.debug("%s Python package not found: %s", pkg_name, err)

    if version is None:
        version = getattr(imported_pkg, '__version__', None)

    return version


def check_easybuild_deps(modtool):
    """
    Check presence and version of required and optional EasyBuild dependencies, and report back to terminal.
    """
    version_regex = re.compile(r'\s(?P<version>[0-9][0-9.]+[a-z]*)')

    checks_data = OrderedDict()

    def extract_version(tool):
        """Helper function to extract (only) version for specific command line tool."""
        out = get_tool_version(tool, ignore_ec=True)
        res = version_regex.search(out)
        if res:
            version = res.group('version')
        else:
            version = "UNKNOWN version"

        return version

    python_version = extract_version(sys.executable)

    opt_dep_versions = {}
    for key, opt_dep in EASYBUILD_OPTIONAL_DEPENDENCIES.items():

        pkg = opt_dep[0]
        if pkg is None:
            pkg = key.lower()

        try:
            mod = __import__(pkg)
        except ImportError:
            mod = None

        if mod:
            dep_version = det_pypkg_version(key, mod, import_name=pkg)
        else:
            dep_version = False

        opt_dep_versions[key] = dep_version

    checks_data['col_titles'] = ('name', 'version', 'used for')

    req_deps_key = "Required dependencies"
    checks_data[req_deps_key] = OrderedDict()
    checks_data[req_deps_key]['Python'] = (python_version, None)
    checks_data[req_deps_key]['modules tool:'] = (str(modtool), None)

    opt_deps_key = "Optional dependencies"
    checks_data[opt_deps_key] = {}

    for key, version in opt_dep_versions.items():
        checks_data[opt_deps_key][key] = (version, EASYBUILD_OPTIONAL_DEPENDENCIES[key][1])

    sys_tools_key = "System tools"
    checks_data[sys_tools_key] = {}

    for tool in SYSTEM_TOOLS:
        tool_info = None
        cmd = SYSTEM_TOOL_CMDS.get(tool, tool)
        if which(cmd):
            version = extract_version(cmd)
            if version.startswith('UNKNOWN'):
                tool_info = None
            else:
                tool_info = version
        else:
            tool_info = False

        checks_data[sys_tools_key][tool] = (tool_info, None)

    return checks_data
