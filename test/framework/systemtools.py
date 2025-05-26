##
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
##
"""
Unit tests for systemtools.py

@author: Kenneth hoste (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import copy
import ctypes
import logging
import os
import re
import sys
import stat

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.systemtools as st
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.environment import modify_env, setvar
from easybuild.tools.filetools import adjust_permissions, mkdir, read_file, symlink, which, write_file
from easybuild.tools.run import RunShellCmdResult, run_shell_cmd
from easybuild.tools.systemtools import CPU_ARCHITECTURES, AARCH32, AARCH64, POWER, X86_64
from easybuild.tools.systemtools import CPU_FAMILIES, POWER_LE, DARWIN, LINUX, UNKNOWN
from easybuild.tools.systemtools import CPU_VENDORS, AMD, APM, ARM, CAVIUM, IBM, INTEL
from easybuild.tools.systemtools import MAX_FREQ_FP, PROC_CPUINFO_FP, PROC_MEMINFO_FP
from easybuild.tools.systemtools import check_linked_shared_libs, check_os_dependency, check_python_version
from easybuild.tools.systemtools import det_parallelism, get_avail_core_count, get_cuda_object_dump_raw
from easybuild.tools.systemtools import get_cuda_architectures, get_cpu_arch_name, get_cpu_architecture
from easybuild.tools.systemtools import get_cpu_family, get_cpu_features, get_cpu_model, get_cpu_speed, get_cpu_vendor
from easybuild.tools.systemtools import get_gcc_version, get_glibc_version, get_os_type, get_os_name, get_os_version
from easybuild.tools.systemtools import get_platform_name, get_shared_lib_ext, get_system_info, get_total_memory
from easybuild.tools.systemtools import find_library_path, locate_solib, pick_dep_version, pick_system_specific_value


PROC_CPUINFO_TXT = None

PROC_CPUINFO_TXT_RASPI2 = """processor : 0
model name : ARMv7 Processor rev 5 (v7l)
BogoMIPS : 57.60
Features : half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm
CPU implementer : 0x41
CPU architecture: 7
CPU variant : 0x0
CPU part : 0xc07
CPU revision : 5

processor : 1
model name : ARMv7 Processor rev 5 (v7l)
BogoMIPS : 57.60
Features : half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm
CPU implementer : 0x41
CPU architecture: 7
CPU variant : 0x0
CPU part : 0xc07
CPU revision : 5
"""

PROC_CPUINFO_TXT_ODROID_XU3 = """processor	: 0
model name	: ARMv7 Processor rev 3 (v7l)
BogoMIPS	: 84.00
Features	: swp half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt
CPU implementer	: 0x41
CPU architecture: 7
CPU variant	: 0x0
CPU part	: 0xc07
CPU revision	: 3

processor	: 4
model name	: ARMv7 Processor rev 3 (v7l)
BogoMIPS	: 120.00
Features	: swp half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt
CPU implementer	: 0x41
CPU architecture: 7
CPU variant	: 0x2
CPU part	: 0xc0f
CPU revision	: 3
"""

PROC_CPUINFO_TXT_XGENE2 = """processor	: 0
cpu MHz		: 2400.000
Features	: fp asimd evtstrm aes pmull sha1 sha2 crc32
CPU implementer	: 0x50
CPU architecture: 8
CPU variant	: 0x1
CPU part	: 0x000
CPU revision	: 0
"""

PROC_CPUINFO_TXT_THUNDERX = """processor	: 0
Features	: fp asimd evtstrm aes pmull sha1 sha2 crc32
CPU implementer	: 0x43
CPU architecture: 8
CPU variant	: 0x1
CPU part	: 0x0a1
CPU revision	: 0
"""

PROC_CPUINFO_TXT_POWER = """processor	: 0
cpu		: POWER7 (architected), altivec supported
clock		: 3550.000000MHz
revision	: 2.3 (pvr 003f 0203)

processor	: 13
cpu		: POWER7 (architected), altivec supported
clock		: 3550.000000MHz
revision	: 2.3 (pvr 003f 0203)

timebase	: 512000000
platform	: pSeries
model		: IBM,8205-E6C
machine		: CHRP IBM,8205-E6C
"""

PROC_CPUINFO_TXT_AMD_FLAGS = ' '.join([
    "fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall",
    "nx mmxext fxsr_opt pdpe1gb rdtscp lm 3dnowext 3dnow constant_tsc rep_good nopl nonstop_tsc extd_apicid pni",
    "monitor cx16 popcnt lahf_lm cmp_legacy svm extapic cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw ibs",
    "skinit wdt hw_pstate npt lbrv svm_lock nrip_save pausefilter vmmcall",
])
PROC_CPUINFO_TXT_AMD = """processor	: 0
vendor_id	: AuthenticAMD
cpu family	: 16
model		: 8
model name	: Six-Core AMD Opteron(tm) Processor 2427
stepping	: 0
microcode	: 0x10000da
cpu MHz		: 2200.000
cache size	: 512 KB
physical id	: 0
siblings	: 6
core id		: 0
cpu cores	: 6
apicid		: 8
initial apicid	: 0
fpu		: yes
fpu_exception	: yes
cpuid level	: 5
wp		: yes
flags		: %(flags)s
bogomips	: 4400.54
TLB size	: 1024 4K pages
clflush size	: 64
cache_alignment	: 64
address sizes	: 48 bits physical, 48 bits virtual
power management: ts ttp tm stc 100mhzsteps hwpstate

processor	: 1
vendor_id	: AuthenticAMD
cpu family	: 16
model		: 8
model name	: Six-Core AMD Opteron(tm) Processor 2427
stepping	: 0
microcode	: 0x10000da
cpu MHz		: 2200.000
cache size	: 512 KB
physical id	: 0
siblings	: 6
core id		: 1
cpu cores	: 6
apicid		: 9
initial apicid	: 1
fpu		: yes
fpu_exception	: yes
cpuid level	: 5
wp		: yes
flags		: %(flags)s
bogomips	: 4400.54
TLB size	: 1024 4K pages
clflush size	: 64
cache_alignment	: 64
address sizes	: 48 bits physical, 48 bits virtual
power management: ts ttp tm stc 100mhzsteps hwpstate
""" % {'flags': PROC_CPUINFO_TXT_AMD_FLAGS}

PROC_CPUINFO_TXT_INTEL_FLAGS = ' '.join([
    "fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss",
    "ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc arch_perfmon pebs bts rep_good xtopology nonstop_tsc",
    "aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 cx16 xtpr pdcm pcid dca sse4_1 sse4_2",
    "x2apic popcnt tsc_deadline_timer aes xsave avx lahf_lm ida arat xsaveopt pln pts dts tpr_shadow vnmi",
    "flexpriority ept vpid",
])

PROC_CPUINFO_TXT_INTEL = """processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 45
model name	: Intel(R) Xeon(R) CPU E5-2670 0 @ 2.60GHz
stepping	: 7
microcode	: 1808
cpu MHz		: 2600.075
cache size	: 20480 KB
physical id	: 0
siblings	: 8
core id		: 0
cpu cores	: 8
apicid		: 0
initial apicid	: 0
fpu		: yes
fpu_exception	: yes
cpuid level	: 13
wp		: yes
flags		: %(flags)s
bogomips	: 5200.15
clflush size	: 64
cache_alignment	: 64
address sizes	: 46 bits physical, 48 bits virtual
power management:

processor	: 1
vendor_id	: GenuineIntel
cpu family	: 6
model		: 45
model name	: Intel(R) Xeon(R) CPU E5-2670 0 @ 2.60GHz
stepping	: 7
microcode	: 1808
cpu MHz		: 2600.075
cache size	: 20480 KB
physical id	: 1
siblings	: 8
core id		: 0
cpu cores	: 8
apicid		: 32
initial apicid	: 32
fpu		: yes
fpu_exception	: yes
cpuid level	: 13
wp		: yes
flags		: %(flags)s
bogomips	: 5200.04
clflush size	: 64
cache_alignment	: 64
address sizes	: 46 bits physical, 48 bits virtual
power management:
""" % {'flags': PROC_CPUINFO_TXT_INTEL_FLAGS}

PROC_MEMINFO_TXT = """MemTotal:       66059108 kB
MemFree:         2639988 kB
Buffers:          236368 kB
Cached:         59396644 kB
SwapCached:           84 kB
Active:          3288736 kB
Inactive:       56906588 kB
Active(anon):     246284 kB
Inactive(anon):   348796 kB
Active(file):    3042452 kB
Inactive(file): 56557792 kB
Unevictable:     1048576 kB
Mlocked:            2048 kB
SwapTotal:      20971516 kB
SwapFree:       20969556 kB
Dirty:                76 kB
Writeback:             0 kB
AnonPages:       1610864 kB
Mapped:           118176 kB
Shmem:             32744 kB
Slab:             891272 kB
SReclaimable:     646764 kB
SUnreclaim:       244508 kB
KernelStack:       18960 kB
PageTables:        31528 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:    54001068 kB
Committed_AS:    2331888 kB
VmallocTotal:   34359738367 kB
VmallocUsed:      492584 kB
VmallocChunk:   34325311012 kB
HardwareCorrupted:     0 kB
AnonHugePages:   1232896 kB
HugePages_Total:       0
HugePages_Free:        0
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
DirectMap4k:        5056 kB
DirectMap2M:     2045952 kB
DirectMap1G:    65011712 kB
"""

FILE_BIN = "ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter "
FILE_BIN += "/lib64/ld-linux-x86-64.so.2, for GNU/Linux 3.2.0, not stripped, too many notes (256)"

FILE_SHAREDLIB = "ELF 64-bit LSB shared object, x86-64, version 1 (SYSV), dynamically linked, "
FILE_SHAREDLIB += "BuildID[sha1]=5535086d3380568f8eaecfa2e73f456f1edd94ec, stripped"

CUOBJDUMP_FAT = """
Fatbin elf code:
================
arch = sm_50
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_60
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_61
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_70
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_75
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_80
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_86
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_89
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin ptx code:
================
arch = sm_90
code version = [8,1]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_90
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_90a
code version = [1,7]
host = linux
compile_size = 64bit

Fatbin ptx code:
================
arch = sm_90a
code version = [8,4]
host = linux
compile_size = 64bit
compressed
ptxasOptions ="""

CUOBJDUMP_PTX_ONLY = """
Fatbin ptx code:
================
arch = sm_90
code version = [8,4]
host = linux
compile_size = 64bit
compressed
ptxasOptions =

Fatbin ptx code:
================
arch = sm_90a
code version = [8,4]
host = linux
compile_size = 64bit
compressed
ptxasOptions ="""

CUOBJDUMP_DEVICE_CODE_ONLY = """
Fatbin elf code:
================
arch = sm_90
code version = [1,7]
host = linux
compile_size = 64bit
compressed

Fatbin elf code:
================
arch = sm_90a
code version = [1,7]
host = linux
compile_size = 64bit"""

# Invalid, because it doesn't contain an arch = sm_XX entry
CUOBJDUMP_INVALID = """
Fatbin elf code:
================
code version = [1,7]
host = linux
compile_size = 64bit
compressed"""

MACHINE_NAME = None


def mocked_read_file(fp):
    """Mocked version of read_file, with specified contents for known filenames."""
    known_fps = {
        MAX_FREQ_FP: '2850000',
        PROC_CPUINFO_FP: PROC_CPUINFO_TXT,
        PROC_MEMINFO_FP: PROC_MEMINFO_TXT,
    }
    if fp in known_fps:
        return known_fps[fp]
    else:
        return read_file(fp)


def mocked_is_readable(mocked_fp, fp):
    """Mocked version of is_readable, returns True for a particular specified filepath."""
    return fp == mocked_fp


def mocked_run_shell_cmd(cmd, **kwargs):
    """Mocked version of run_shell_cmd, with specified output for known commands."""
    known_cmds = {
        "gcc --version": "gcc (GCC) 5.1.1 20150618 (Red Hat 5.1.1-4)",
        "ldd --version": "ldd (GNU libc) 2.12; ",
        "sysctl -n hw.cpufrequency_max": "2400000000",
        "sysctl -n hw.ncpu": '10',
        "sysctl -n hw.memsize": '8589934592',
        "sysctl -n machdep.cpu.brand_string": "Intel(R) Core(TM) i5-4258U CPU @ 2.40GHz",
        "sysctl -n machdep.cpu.extfeatures": "SYSCALL XD 1GBPAGE EM64T LAHF LZCNT RDTSCP TSCI",
        "sysctl -n machdep.cpu.features": ' '.join([
            "FPU VME DE PSE TSC MSR PAE MCE CX8 APIC SEP MTRR PGE MCA CMOV PAT PSE36 CLFSH DS ACPI MMX FXSR SSE SSE2",
            "SS HTT TM PBE SSE3 PCLMULQDQ DTES64 MON DSCPL VMX EST TM2 SSSE3 FMA CX16 TPR PDCM SSE4.1 SSE4.2 x2APIC",
            "MOVBE POPCNT AES PCID XSAVE OSXSAVE SEGLIM64 TSCTMR AVX1.0 RDRAND F16C",
        ]),
        "sysctl -n machdep.cpu.leaf7_features": "SMEP ERMS RDWRFSGS TSC_THREAD_OFFSET BMI1 AVX2 BMI2 INVPCID FPU_CSDS",
        "sysctl -n machdep.cpu.vendor": 'GenuineIntel',
        "ulimit -u": '40',
        "file mock_cuda_bin": FILE_BIN,
        "file mock_cuda_sharedlib": FILE_SHAREDLIB,
        "file mock_invalid_cuda_sharedlib": FILE_SHAREDLIB,
        "file mock_non_cuda_sharedlib": FILE_SHAREDLIB,
        "file mock_non_cuda_sharedlib_unexpected": FILE_SHAREDLIB,
        "file mock_cuda_staticlib": "current ar archive",
        "file mock_noncuda_file": "ASCII text",
        "cuobjdump mock_cuda_bin": CUOBJDUMP_FAT,
        "cuobjdump mock_cuda_sharedlib": CUOBJDUMP_PTX_ONLY,
        "cuobjdump mock_invalid_cuda_sharedlib": CUOBJDUMP_INVALID,
        "cuobjdump mock_cuda_staticlib": CUOBJDUMP_DEVICE_CODE_ONLY,
    }
    known_fail_cmds = {
        "cuobjdump mock_non_cuda_sharedlib": ("cuobjdump info  : File '/path/to/mock.so' does not contain device code",
                                              255),
        "cuobjdump mock_non_cuda_sharedlib_unexpected": ("cuobjdump info    : Some unexpected output", 255),
    }
    if cmd in known_cmds:
        return RunShellCmdResult(cmd=cmd, exit_code=0, output=known_cmds[cmd], stderr=None, work_dir=os.getcwd(),
                                 out_file=None, err_file=None, cmd_sh=None, thread_id=None, task_id=None)
    elif cmd in known_fail_cmds:
        return RunShellCmdResult(cmd=cmd, exit_code=known_fail_cmds[cmd][1], output=known_fail_cmds[cmd][0],
                                 stderr=None, work_dir=os.getcwd(), out_file=None, err_file=None, cmd_sh=None,
                                 thread_id=None, task_id=None)
    else:
        return run_shell_cmd(cmd, **kwargs)


def mocked_uname():
    """Mocked version of platform.uname, with specified contents for known machine names."""
    return ('Linux', 'localhost', '3.16', '3.16', MACHINE_NAME, '')


class SystemToolsTest(EnhancedTestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def setUp(self):
        """Set up systemtools test."""
        super().setUp()
        self.orig_get_cpu_architecture = st.get_cpu_architecture
        self.orig_get_os_name = st.get_os_name
        self.orig_get_os_type = st.get_os_type
        self.orig_is_readable = st.is_readable
        self.orig_read_file = st.read_file
        self.orig_run_shell_cmd = st.run_shell_cmd
        self.orig_platform_dist = st.platform.dist if hasattr(st.platform, 'dist') else None
        self.orig_platform_uname = st.platform.uname
        self.orig_get_tool_version = st.get_tool_version
        self.orig_sys_version_info = st.sys.version_info
        self.orig_HAVE_ARCHSPEC = st.HAVE_ARCHSPEC
        self.orig_HAVE_DISTRO = st.HAVE_DISTRO
        self.orig_ETC_OS_RELEASE = st.ETC_OS_RELEASE
        self.orig_archspec_cpu_host = getattr(st, 'archspec_cpu_host', None)

    def tearDown(self):
        """Cleanup after systemtools test."""
        st.is_readable = self.orig_is_readable
        st.read_file = self.orig_read_file
        st.get_cpu_architecture = self.orig_get_cpu_architecture
        st.get_os_name = self.orig_get_os_name
        st.get_os_type = self.orig_get_os_type
        st.run_shell_cmd = self.orig_run_shell_cmd
        if self.orig_platform_dist is not None:
            st.platform.dist = self.orig_platform_dist
        st.platform.uname = self.orig_platform_uname
        st.get_tool_version = self.orig_get_tool_version
        st.sys.version_info = self.orig_sys_version_info
        st.HAVE_ARCHSPEC = self.orig_HAVE_ARCHSPEC
        st.HAVE_DISTRO = self.orig_HAVE_DISTRO
        st.ETC_OS_RELEASE = self.orig_ETC_OS_RELEASE
        if self.orig_archspec_cpu_host is not None:
            st.archspec_cpu_host = self.orig_archspec_cpu_host
        super().tearDown()

    def test_avail_core_count_native(self):
        """Test getting core count."""
        core_count = get_avail_core_count()
        self.assertIsInstance(core_count, int)
        self.assertTrue(core_count > 0, "core_count %d > 0" % core_count)

    def test_avail_core_count_linux(self):
        """Test getting core count (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        orig_sched_getaffinity = st.sched_getaffinity
        cpus = [1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0]
        st.sched_getaffinity = lambda: cpus
        self.assertEqual(get_avail_core_count(), 6)
        st.sched_getaffinity = orig_sched_getaffinity

    def test_avail_core_count_darwin(self):
        """Test getting core count (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_avail_core_count(), 10)

    def test_cpu_model_native(self):
        """Test getting CPU model."""
        cpu_model = get_cpu_model()
        self.assertIsInstance(cpu_model, str)

    def test_cpu_model_linux(self):
        """Test getting CPU model (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.is_readable = lambda fp: mocked_is_readable(PROC_CPUINFO_FP, fp)
        st.platform.uname = mocked_uname
        global MACHINE_NAME
        global PROC_CPUINFO_TXT

        MACHINE_NAME = 'x86_64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_INTEL
        self.assertEqual(get_cpu_model(), "Intel(R) Xeon(R) CPU E5-2670 0 @ 2.60GHz")

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_AMD
        self.assertEqual(get_cpu_model(), "Six-Core AMD Opteron(tm) Processor 2427")

        MACHINE_NAME = 'ppc64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        self.assertEqual(get_cpu_model(), "IBM,8205-E6C")

        MACHINE_NAME = 'armv7l'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_RASPI2
        self.assertEqual(get_cpu_model(), "ARM Cortex-A7")

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_ODROID_XU3
        self.assertEqual(get_cpu_model(), "ARM Cortex-A7 + Cortex-A15")

    def test_cpu_model_darwin(self):
        """Test getting CPU model (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_cpu_model(), "Intel(R) Core(TM) i5-4258U CPU @ 2.40GHz")

    def test_cpu_speed_native(self):
        """Test getting CPU speed."""
        cpu_speed = get_cpu_speed()
        if cpu_speed is not None:
            self.assertIsInstance(cpu_speed, float)
            self.assertTrue(cpu_speed > 0.0)

    def test_cpu_speed_linux(self):
        """Test getting CPU speed (mocked for Linux)."""
        # test for particular type of system by mocking used functions
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.is_readable = lambda fp: mocked_is_readable(PROC_CPUINFO_FP, fp)

        # tweak global constant used by mocked_read_file
        global PROC_CPUINFO_TXT

        # /proc/cpuinfo on Linux x86 (no cpufreq)
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_INTEL
        self.assertEqual(get_cpu_speed(), 2600.075)

        # /proc/cpuinfo on Linux POWER
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        self.assertEqual(get_cpu_speed(), 3550.0)

        # Linux (x86) with cpufreq
        st.is_readable = lambda fp: mocked_is_readable(MAX_FREQ_FP, fp)
        self.assertEqual(get_cpu_speed(), 2850.0)

    def test_cpu_speed_darwin(self):
        """Test getting CPU speed (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_cpu_speed(), 2400.0)

    def test_cpu_features_native(self):
        """Test getting CPU features."""
        cpu_feat = get_cpu_features()
        self.assertIsInstance(cpu_feat, list)
        self.assertTrue(len(cpu_feat) >= 0)
        self.assertTrue(all(isinstance(x, str) for x in cpu_feat))

    def test_cpu_features_linux(self):
        """Test getting CPU features (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.is_readable = lambda fp: mocked_is_readable(PROC_CPUINFO_FP, fp)

        # tweak global constant used by mocked_read_file
        global PROC_CPUINFO_TXT

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_INTEL
        expected = ['acpi', 'aes', 'aperfmperf', 'apic', 'arat', 'arch_perfmon', 'avx', 'bts', 'clflush', 'cmov',
                    'constant_tsc', 'cx16', 'cx8', 'dca', 'de', 'ds_cpl', 'dtes64', 'dts', 'dts', 'ept', 'est',
                    'flexpriority', 'fpu', 'fxsr', 'ht', 'ida', 'lahf_lm', 'lm', 'mca', 'mce', 'mmx', 'monitor',
                    'msr', 'mtrr', 'nonstop_tsc', 'nx', 'pae', 'pat', 'pbe', 'pcid', 'pclmulqdq', 'pdcm', 'pdpe1gb',
                    'pebs', 'pge', 'pln', 'pni', 'popcnt', 'pse', 'pse36', 'pts', 'rdtscp', 'rep_good', 'sep', 'smx',
                    'ss', 'sse', 'sse2', 'sse4_1', 'sse4_2', 'ssse3', 'syscall', 'tm', 'tm2', 'tpr_shadow', 'tsc',
                    'tsc_deadline_timer', 'vme', 'vmx', 'vnmi', 'vpid', 'x2apic', 'xsave', 'xsaveopt', 'xtopology',
                    'xtpr']
        self.assertEqual(get_cpu_features(), expected)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_RASPI2
        expected = ['edsp', 'evtstrm', 'fastmult', 'half', 'idiva', 'idivt', 'lpae', 'neon',
                    'thumb', 'tls', 'vfp', 'vfpd32', 'vfpv3', 'vfpv4']
        self.assertEqual(get_cpu_features(), expected)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_ODROID_XU3
        expected = ['edsp', 'fastmult', 'half', 'idiva', 'idivt', 'neon', 'swp', 'thumb',
                    'tls', 'vfp', 'vfpv3', 'vfpv4']
        self.assertEqual(get_cpu_features(), expected)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_XGENE2
        expected = ['aes', 'asimd', 'crc32', 'evtstrm', 'fp', 'pmull', 'sha1', 'sha2']
        self.assertEqual(get_cpu_features(), expected)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_THUNDERX
        expected = ['aes', 'asimd', 'crc32', 'evtstrm', 'fp', 'pmull', 'sha1', 'sha2']
        self.assertEqual(get_cpu_features(), expected)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        st.get_cpu_architecture = lambda: POWER
        self.assertEqual(get_cpu_features(), ['altivec', 'vsx'])

    def test_cpu_features_darwin(self):
        """Test getting CPU features (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        expected = ['1gbpage', 'acpi', 'aes', 'apic', 'avx1.0', 'avx2', 'bmi1', 'bmi2', 'clfsh', 'cmov', 'cx16',
                    'cx8', 'de', 'ds', 'dscpl', 'dtes64', 'em64t', 'erms', 'est', 'f16c', 'fma', 'fpu', 'fpu_csds',
                    'fxsr', 'htt', 'invpcid', 'lahf', 'lzcnt', 'mca', 'mce', 'mmx', 'mon', 'movbe', 'msr', 'mtrr',
                    'osxsave', 'pae', 'pat', 'pbe', 'pcid', 'pclmulqdq', 'pdcm', 'pge', 'popcnt', 'pse', 'pse36',
                    'rdrand', 'rdtscp', 'rdwrfsgs', 'seglim64', 'sep', 'smep', 'ss', 'sse', 'sse2', 'sse3', 'sse4.1',
                    'sse4.2', 'ssse3', 'syscall', 'tm', 'tm2', 'tpr', 'tsc', 'tsc_thread_offset', 'tsci', 'tsctmr',
                    'vme', 'vmx', 'x2apic', 'xd', 'xsave']
        self.assertEqual(get_cpu_features(), expected)

    def test_cpu_architecture_native(self):
        """Test getting the CPU architecture."""
        arch = get_cpu_architecture()
        self.assertIn(arch, CPU_ARCHITECTURES)

    def test_cpu_architecture(self):
        """Test getting the CPU architecture (mocked)."""
        st.platform.uname = mocked_uname
        global MACHINE_NAME

        machine_names = {
            'aarch64': AARCH64,
            'aarch64_be': AARCH64,
            'arm64': AARCH64,
            'armv7l': AARCH32,
            'ppc64': POWER,
            'ppc64le': POWER,
            'x86_64': X86_64,
            'some_fancy_arch': UNKNOWN,
        }
        for name in machine_names:
            MACHINE_NAME = name
            self.assertEqual(get_cpu_architecture(), machine_names[name])

    def test_cpu_arch_name_native(self):
        """Test getting CPU arch name."""
        arch_name = get_cpu_arch_name()
        self.assertIsInstance(arch_name, str)

    def test_cpu_arch_name(self):
        """Test getting CPU arch name."""

        class MicroArch:
            def __init__(self, name):
                self.name = name

        st.HAVE_ARCHSPEC = True
        st.archspec_cpu_host = lambda: MicroArch('haswell')
        arch_name = get_cpu_arch_name()
        self.assertEqual(arch_name, 'haswell')

        st.archspec_cpu_host = lambda: None
        arch_name = get_cpu_arch_name()
        self.assertEqual(arch_name, 'UNKNOWN')

    def test_cpu_vendor_native(self):
        """Test getting CPU vendor."""
        cpu_vendor = get_cpu_vendor()
        self.assertIn(cpu_vendor, CPU_VENDORS)

    def test_cpu_vendor_linux(self):
        """Test getting CPU vendor (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.is_readable = lambda fp: mocked_is_readable(PROC_CPUINFO_FP, fp)
        st.platform.uname = mocked_uname
        global MACHINE_NAME
        global PROC_CPUINFO_TXT

        MACHINE_NAME = 'x86_64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_INTEL
        self.assertEqual(get_cpu_vendor(), INTEL)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_AMD
        self.assertEqual(get_cpu_vendor(), AMD)

        MACHINE_NAME = 'ppc64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        self.assertEqual(get_cpu_vendor(), IBM)

        MACHINE_NAME = 'armv7l'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_RASPI2
        self.assertEqual(get_cpu_vendor(), ARM)

        MACHINE_NAME = 'aarch64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_XGENE2
        self.assertEqual(get_cpu_vendor(), APM)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_THUNDERX
        self.assertEqual(get_cpu_vendor(), CAVIUM)

    def test_cpu_vendor_darwin(self):
        """Test getting CPU vendor (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_cpu_vendor(), INTEL)

    def test_cpu_family_native(self):
        """Test get_cpu_family function."""
        run_shell_cmd.clear_cache()
        cpu_family = get_cpu_family()
        self.assertTrue(cpu_family in CPU_FAMILIES or cpu_family == UNKNOWN)

    def test_cpu_family_linux(self):
        """Test get_cpu_family function (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.is_readable = lambda fp: mocked_is_readable(PROC_CPUINFO_FP, fp)
        st.platform.uname = mocked_uname
        global MACHINE_NAME
        global PROC_CPUINFO_TXT

        MACHINE_NAME = 'x86_64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_INTEL
        self.assertEqual(get_cpu_family(), INTEL)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_AMD
        self.assertEqual(get_cpu_family(), AMD)

        MACHINE_NAME = 'armv7l'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_RASPI2
        self.assertEqual(get_cpu_family(), ARM)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_ODROID_XU3
        self.assertEqual(get_cpu_family(), ARM)

        MACHINE_NAME = 'aarch64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_XGENE2
        self.assertEqual(get_cpu_family(), ARM)

        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_THUNDERX
        self.assertEqual(get_cpu_family(), ARM)

        MACHINE_NAME = 'ppc64'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        self.assertEqual(get_cpu_family(), POWER)

        MACHINE_NAME = 'ppc64le'
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        self.assertEqual(get_cpu_family(), POWER_LE)

    def test_cpu_family_darwin(self):
        """Test get_cpu_family function (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        run_shell_cmd.clear_cache()
        self.assertEqual(get_cpu_family(), INTEL)

    def test_os_type(self):
        """Test getting OS type."""
        os_type = get_os_type()
        self.assertIn(os_type, [DARWIN, LINUX])

    def test_shared_lib_ext_native(self):
        """Test getting extension for shared libraries."""
        ext = get_shared_lib_ext()
        self.assertIn(ext, ['dylib', 'so'])

    def test_shared_lib_ext_linux(self):
        """Test getting extension for shared libraries (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        self.assertEqual(get_shared_lib_ext(), 'so')

    def test_shared_lib_ext_darwin(self):
        """Test getting extension for shared libraries (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        self.assertEqual(get_shared_lib_ext(), 'dylib')

    def test_platform_name_native(self):
        """Test getting platform name."""
        platform_name_nover = get_platform_name()
        self.assertIsInstance(platform_name_nover, str)
        len_nover = len(platform_name_nover.split('-'))
        self.assertTrue(len_nover >= 3)

        platform_name_ver = get_platform_name(withversion=True)
        self.assertIsInstance(platform_name_ver, str)
        len_ver = len(platform_name_ver.split('-'))
        self.assertTrue(platform_name_ver.startswith(platform_name_ver))
        self.assertTrue(len_ver >= len_nover)

    def test_platform_name_linux(self):
        """Test getting platform name (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        self.assertTrue(re.match('.*-unknown-linux$', get_platform_name()))
        self.assertTrue(re.match('.*-unknown-linux-gnu$', get_platform_name(withversion=True)))

    def test_platform_name_darwin(self):
        """Test getting platform name (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        self.assertTrue(re.match('.*-apple-darwin$', get_platform_name()))
        self.assertTrue(re.match('.*-apple-darwin.*$', get_platform_name(withversion=True)))

    def test_os_name(self):
        """Test getting OS name."""
        os_name = get_os_name()
        self.assertTrue(isinstance(os_name, str) or os_name == UNKNOWN)

    def test_os_version(self):
        """Test getting OS version."""
        os_version = get_os_version()
        self.assertTrue(isinstance(os_version, str) or os_version == UNKNOWN)

        # make sure that bug fixed in https://github.com/easybuilders/easybuild-framework/issues/3952
        # does not surface again, by mocking what's needed to make get_os_version fall into SLES-specific path

        if hasattr(st.platform, 'dist'):
            st.platform.dist = lambda: (None, None)
        st.HAVE_DISTRO = False

        st.get_os_name = lambda: 'SLES'
        fake_etc_os_release = os.path.join(self.test_prefix, 'os-release')
        write_file(fake_etc_os_release, 'VERSION="15-SP1"')
        st.ETC_OS_RELEASE = fake_etc_os_release

        os_version = get_os_version()
        self.assertEqual(os_version, '15-SP1')

    def test_gcc_version_native(self):
        """Test getting gcc version."""
        gcc_version = get_gcc_version()
        if gcc_version is not None:
            self.assertIsInstance(gcc_version, str)

    def test_gcc_version_linux(self):
        """Test getting gcc version (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_gcc_version(), '5.1.1')

    def test_gcc_version_darwin(self):
        """Test getting gcc version (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        out = "Apple LLVM version 7.0.0 (clang-700.1.76)"
        cwd = os.getcwd()
        mocked_run_res = RunShellCmdResult(cmd="gcc --version", exit_code=0, output=out, stderr=None, work_dir=cwd,
                                           out_file=None, err_file=None, cmd_sh=None, thread_id=None, task_id=None)
        st.run_shell_cmd = lambda *args, **kwargs: mocked_run_res
        self.assertEqual(get_gcc_version(), None)

    def test_glibc_version_native(self):
        """Test getting glibc version."""
        glibc_version = get_glibc_version()
        self.assertTrue(isinstance(glibc_version, str) or glibc_version == UNKNOWN)

    def test_glibc_version_linux(self):
        """Test getting glibc version (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_glibc_version(), '2.12')

    def test_glibc_version_linux_gentoo(self):
        """Test getting glibc version (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        ldd_version_out = "ldd (Gentoo 2.37-r3 (patchset 5)) 2.37; Copyright (C) 2023 Free Software Foundation, Inc."
        st.get_tool_version = lambda _: ldd_version_out
        self.assertEqual(get_glibc_version(), '2.37')

    def test_glibc_version_linux_musl_libc(self):
        """Test getting glibc version (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.get_tool_version = lambda _: "musl libc (x86_64); Version 1.1.18; Dynamic Program Loader"
        self.assertEqual(get_glibc_version(), UNKNOWN)

    def test_glibc_version_darwin(self):
        """Test getting glibc version (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        self.assertEqual(get_glibc_version(), UNKNOWN)

    def test_get_total_memory_linux(self):
        """Test the function that gets the total memory."""
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.is_readable = lambda fp: mocked_is_readable(PROC_MEMINFO_FP, fp)
        self.assertEqual(get_total_memory(), 64510)

    def test_get_total_memory_darwin(self):
        """Test the function that gets the total memory."""
        st.get_os_type = lambda: st.DARWIN
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(get_total_memory(), 8192)

    def test_get_total_memory_native(self):
        """Test the function that gets the total memory."""
        memtotal = get_total_memory()
        self.assertIsInstance(memtotal, int)

    def test_system_info(self):
        """Test getting system info."""
        system_info = get_system_info()
        self.assertIsInstance(system_info, dict)

    def test_det_parallelism_native(self):
        """Test det_parallelism function (native calls)."""
        self.assertTrue(det_parallelism() > 0)
        # specified parallelism
        self.assertEqual(det_parallelism(par=5), 5)
        # max parallelism caps
        self.assertEqual(det_parallelism(maxpar=1), 1)
        self.assertEqual(det_parallelism(16, 1), 1)
        self.assertEqual(det_parallelism(par=5, maxpar=2), 2)
        self.assertEqual(det_parallelism(par=5, maxpar=10), 5)

    def test_det_parallelism_mocked(self):
        """Test det_parallelism function (with mocked ulimit/get_avail_core_count)."""
        orig_get_avail_core_count = st.get_avail_core_count

        # mock number of available cores to 8
        st.get_avail_core_count = lambda: 8
        self.assertTrue(det_parallelism(), 8)

        # make 'ulimit -u' return '40', which should result in default (max) parallelism of 4 ((40-15)/6)
        del det_parallelism._default_parallelism
        st.run_shell_cmd = mocked_run_shell_cmd
        self.assertEqual(det_parallelism(), 4)
        self.assertEqual(det_parallelism(par=6), 6)
        self.assertEqual(det_parallelism(maxpar=2), 2)

        st.get_avail_core_count = orig_get_avail_core_count

    def test_det_terminal_size(self):
        """Test det_terminal_size function."""
        (height, width) = st.det_terminal_size()
        self.assertTrue(isinstance(height, int) and height >= 0)
        self.assertTrue(isinstance(width, int) and width >= 0)

    def test_check_python_version(self):
        """Test check_python_version function."""

        init_config(build_options={'silence_deprecation_warnings': []})

        def mock_python_ver(py_maj_ver, py_min_ver):
            """Helper function to mock a particular Python version."""
            st.sys.version_info = (py_maj_ver, py_min_ver) + sys.version_info[2:]

        # mock running with different Python versions
        mock_python_ver(1, 4)
        error_pattern = r"EasyBuild is not compatible with Python 1.4"
        self.assertErrorRegex(EasyBuildError, error_pattern, check_python_version)

        mock_python_ver(4, 0)
        error_pattern = r"EasyBuild is not compatible \(yet\) with Python 4.0"
        self.assertErrorRegex(EasyBuildError, error_pattern, check_python_version)

        mock_python_ver(2, 7)
        error_pattern = r"EasyBuild is not compatible with Python 2.7"
        self.assertErrorRegex(EasyBuildError, error_pattern, check_python_version)

        mock_python_ver(3, 5)
        error_pattern = r"Python 3.6 or higher is required, found Python 3.5"
        self.assertErrorRegex(EasyBuildError, error_pattern, check_python_version)

        # no problems when running with a supported Python version
        for pyver in [(3, 6), (3, 7), (3, 11)]:
            mock_python_ver(*pyver)
            self.assertEqual(check_python_version(), pyver)

        # shouldn't raise any errors, since Python version used to run tests should be supported;
        self.mock_stderr(True)
        (py_maj_ver, py_min_ver) = check_python_version()
        stderr = self.get_stderr()
        self.mock_stderr(False)
        self.assertFalse(stderr)

        self.assertIn(py_maj_ver, [2, 3])
        if py_maj_ver == 2:
            self.assertTrue(py_min_ver == 7)
        else:
            self.assertTrue(py_min_ver >= 5)

    def test_pick_dep_version(self):
        """Test pick_dep_version function."""

        self.assertEqual(pick_dep_version(None), None)
        self.assertEqual(pick_dep_version('1.2.3'), '1.2.3')

        dep_ver_dict = {
            'arch=x86_64': '1.2.3-amd64',
            'arch=POWER': '1.2.3-ppc64le',
        }

        st.get_cpu_architecture = lambda: X86_64
        self.assertEqual(pick_dep_version(dep_ver_dict), '1.2.3-amd64')

        st.get_cpu_architecture = lambda: POWER
        self.assertEqual(pick_dep_version(dep_ver_dict), '1.2.3-ppc64le')

        error_pattern = "Unknown value type for version"
        self.assertErrorRegex(EasyBuildError, error_pattern, pick_dep_version, ('1.2.3', '4.5.6'))

        # check support for using 'arch=*' as fallback key
        dep_ver_dict = {
            'arch=*': '1.2.3',
            'arch=foo': '1.2.3-foo',
            'arch=POWER': '1.2.3-ppc64le',
        }
        self.assertEqual(pick_dep_version(dep_ver_dict), '1.2.3-ppc64le')

        del dep_ver_dict['arch=POWER']
        self.assertEqual(pick_dep_version(dep_ver_dict), '1.2.3')

        # check how faulty input is handled
        self.assertErrorRegex(EasyBuildError, "Found empty dict as version!", pick_dep_version, {})
        error_pattern = r"Unexpected keys in version: bar,foo \(only 'arch=' keys are supported\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, pick_dep_version, {'foo': '1.2', 'bar': '2.3'})
        error_pattern = r"Unknown value type for version: .* \(1.23\), should be string value"
        self.assertErrorRegex(EasyBuildError, error_pattern, pick_dep_version, 1.23)

    def test_pick_system_specific_value(self):
        """Test pick_system_specific_value function."""

        self.assertEqual(pick_system_specific_value('test-desc', None), None)
        self.assertEqual(pick_system_specific_value('test-desc', '1.2.3'), '1.2.3')
        self.assertEqual(pick_system_specific_value('test-desc', (42, 'foobar')), (42, 'foobar'))

        option_dict = {
            'arch=x86_64': '1.2.3-amd64',
            'arch=POWER': '1.2.3-ppc64le',
            'arch=*': '1.2.3-other',
        }

        st.get_cpu_architecture = lambda: X86_64
        self.assertEqual(pick_system_specific_value('test-desc', option_dict), '1.2.3-amd64')

        st.get_cpu_architecture = lambda: POWER
        self.assertEqual(pick_system_specific_value('test-desc', option_dict), '1.2.3-ppc64le')

        st.get_cpu_architecture = lambda: "NON_EXISTING_ARCH"
        self.assertEqual(pick_system_specific_value('test-desc', option_dict), '1.2.3-other')

        error_pattern = "Found empty dict as test-desc"
        self.assertErrorRegex(EasyBuildError, error_pattern, pick_system_specific_value, 'test-desc', {})

        error_pattern = r"Unexpected keys in test-desc: foo \(only 'arch=' keys are supported\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, pick_system_specific_value, 'test-desc',
                              {'foo': '1'})
        error_pattern = r"Unexpected keys in test-desc: foo \(only 'arch=' keys are supported\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, pick_system_specific_value, 'test-desc',
                              {'foo': '1', 'arch=POWER': '2'})

    def test_check_os_dependency(self):
        """Test check_os_dependency."""

        # mock get_os_name in systemtools module to get control over command used to check OS dep
        st.get_os_name = lambda: 'centos'

        # add fake 'rpm' command that fails when $LD_LIBRARY_PATH is set
        rpm = os.path.join(self.test_prefix, 'rpm')
        rpm_txt = '\n'.join([
            "#!/bin/bash",
            "if [[ -z $LD_LIBRARY_PATH ]]; then",
            '    echo "OK: $@ (LD_LIBRARY_PATH: $LD_LIBRARY_PATH)"',
            "    exit 0",
            "else",
            '    echo "LD_LIBRARY_PATH set ($LD_LIBRARY_PATH), fail!"',
            "    exit 1",
            "fi",
        ])
        write_file(rpm, rpm_txt)
        adjust_permissions(rpm, stat.S_IXUSR, add=True)

        # also create fake 'locate' command, which is used as fallback
        locate = os.path.join(self.test_prefix, 'locate')
        write_file(locate, 'exit 1')
        adjust_permissions(locate, stat.S_IXUSR, add=True)

        os.environ['PATH'] = self.test_prefix + ':' + os.getenv('PATH')

        self.assertTrue(os.path.samefile(which('rpm'), rpm))

        # redefine $HOME to put .bash_profile startup script to control $LD_LIBRARY_PATH value
        # we can't directly control the $LD_LIBRARY_PATH via os.environ, doesn't work...
        os.environ['HOME'] = self.test_prefix
        bash_profile = os.path.join(self.test_prefix, '.bash_profile')
        write_file(bash_profile, 'unset LD_LIBRARY_PATH')

        # mocked rpm always exits with exit code 0 (unless $LD_LIBRARY_PATH is set)
        self.assertTrue(check_os_dependency('foo'))

        # still works fine if $LD_LIBRARY_PATH is set
        write_file(bash_profile, 'export LD_LIBRARY_PATH=%s' % self.test_prefix)
        self.assertTrue(check_os_dependency('bar'))

    def test_check_linked_shared_libs(self):
        """Test for check_linked_shared_libs function."""

        txt_path = os.path.join(self.test_prefix, 'test.txt')
        write_file(txt_path, "some text")

        broken_symlink_path = os.path.join(self.test_prefix, 'broken_symlink')
        symlink('/doesnotexist', broken_symlink_path, use_abspath_source=False)

        # result is always None for anything other than dynamically linked binaries or shared libraries
        self.assertEqual(check_linked_shared_libs(self.test_prefix), None)
        self.assertEqual(check_linked_shared_libs(txt_path), None)
        self.assertEqual(check_linked_shared_libs(broken_symlink_path), None)

        bin_bash_path = which('bash')

        os_type = get_os_type()
        if os_type == LINUX:
            with self.mocked_stdout_stderr():
                res = run_shell_cmd("ldd %s" % bin_bash_path)
        elif os_type == DARWIN:
            with self.mocked_stdout_stderr():
                res = run_shell_cmd("otool -L %s" % bin_bash_path)
        else:
            raise EasyBuildError("Unknown OS type: %s" % os_type)

        shlib_ext = get_shared_lib_ext()
        lib_path_regex = re.compile(r'(?P<lib_path>[^\s]*/lib[^ ]+\.%s[^ ]*)' % shlib_ext, re.M)
        lib_path = lib_path_regex.search(res.output).group(1)

        test_pattern_named_args = [
            # if no patterns are specified, result is always True
            {},
            {'required_patterns': ['/lib', shlib_ext]},
            {'banned_patterns': ['this_pattern_should_not_match']},
            {'required_patterns': ['/lib', shlib_ext], 'banned_patterns': ['weirdstuff']},
        ]
        for pattern_named_args in test_pattern_named_args:
            # result is always None for anything other than dynamically linked binaries or shared libraries
            self.assertEqual(check_linked_shared_libs(self.test_prefix, **pattern_named_args), None)
            self.assertEqual(check_linked_shared_libs(txt_path, **pattern_named_args), None)
            self.assertEqual(check_linked_shared_libs(broken_symlink_path, **pattern_named_args), None)
            for path in (bin_bash_path, lib_path):
                # path may not exist, especially for library paths obtained via 'otool -L' on macOS
                if os.path.exists(path):
                    error_msg = "Check on linked libs should pass for %s with %s" % (path, pattern_named_args)
                    self.assertTrue(check_linked_shared_libs(path, **pattern_named_args), error_msg)

        # also test with input that should result in failing check
        test_pattern_named_args = [
            {'required_patterns': ['this_pattern_will_not_match']},
            {'banned_patterns': ['/lib']},
            {'required_patterns': ['weirdstuff'], 'banned_patterns': ['/lib', shlib_ext]},
        ]
        for pattern_named_args in test_pattern_named_args:
            # result is always None for anything other than dynamically linked binaries or shared libraries
            self.assertEqual(check_linked_shared_libs(self.test_prefix, **pattern_named_args), None)
            self.assertEqual(check_linked_shared_libs(txt_path, **pattern_named_args), None)
            self.assertEqual(check_linked_shared_libs(broken_symlink_path, **pattern_named_args), None)
            for path in (bin_bash_path, lib_path):
                error_msg = "Check on linked libs should fail for %s with %s" % (path, pattern_named_args)
                self.assertFalse(check_linked_shared_libs(path, **pattern_named_args), error_msg)

        if get_os_type() == LINUX:
            # inject fake 'file' command which always reports that the file is "dynamically linked"
            file_cmd = os.path.join(self.test_prefix, 'bin', 'file')
            write_file(file_cmd, "echo '(dynamically linked)'")
            adjust_permissions(file_cmd, stat.S_IXUSR, add=True)

            os.environ['PATH'] = os.path.join(self.test_prefix, 'bin') + ':' + os.getenv('PATH')

            test_file = os.path.join(self.test_prefix, 'test.txt')
            write_file(test_file, 'test')

            warning_regex = re.compile(r"WARNING: Determining linked libraries.* via 'ldd .*/test.txt' failed!", re.M)

            self.mock_stderr(True)
            self.mock_stdout(True)
            res = check_linked_shared_libs(test_file, banned_patterns=['/lib'])
            stderr = self.get_stderr()
            stdout = self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            fail_msg = "Pattern '%s' should be found in: %s" % (warning_regex.pattern, stderr)
            self.assertTrue(warning_regex.search(stderr), fail_msg)
            self.assertFalse(stdout)

            self.assertEqual(res, None)

    def test_locate_solib(self):
        """Test locate_solib function (Linux only)."""
        if get_os_type() == LINUX:
            libname = 'libc.so.6'
            libc_obj = None
            try:
                libc_obj = ctypes.cdll.LoadLibrary(libname)
            except OSError:
                pass
            if libc_obj:
                libc_path = locate_solib(libc_obj)
                self.assertEqual(os.path.basename(libc_path), libname)
                self.assertExists(libc_path)

    def test_find_library_path(self):
        """Test find_library_path function (Linux and Darwin only)."""
        os_type = get_os_type()
        if os_type == LINUX:
            libname = 'libc.so.6'
        elif os_type == DARWIN:
            libname = 'libSystem.dylib'
        else:
            libname = None

        if libname:
            lib_path = find_library_path(libname)
            self.assertEqual(os.path.basename(lib_path), libname)
            if os_type != DARWIN:
                self.assertExists(lib_path)

    def test_get_cuda_object_dump_raw(self):
        """Test get_cuda_object_dump_raw function"""
        # This test modifies environment, make sure we can revert the changes:
        start_env = copy.deepcopy(os.environ)

        # Mock the shell command for certain known commands
        st.run_shell_cmd = mocked_run_shell_cmd

        # Test case 1: there's no cuobjdump on the path yet
        error_pattern = r"cuobjdump command not found"
        self.assertErrorRegex(EasyBuildError, error_pattern, get_cuda_object_dump_raw, path='mock_cuda_bin')

        # Put a cuobjdump on the path, doesn't matter what. It will be mocked anyway
        cuobjdump_dir = os.path.join(self.test_prefix, 'cuobjdump_dir')
        mkdir(cuobjdump_dir, parents=True)
        setvar('PATH', '%s:%s' % (cuobjdump_dir, os.getenv('PATH')))
        cuobjdump_file = os.path.join(cuobjdump_dir, 'cuobjdump')
        write_file(cuobjdump_file, "#!/bin/bash\n")
        write_file(cuobjdump_file, "echo 'Mock script, this should never actually be called\n'")
        adjust_permissions(cuobjdump_file, stat.S_IXUSR, add=True)  # Make sure our mock cuobjdump is executable

        # Test case 2: get raw output from mock_cuda_bin, a 'fat' binary
        self.assertEqual(get_cuda_object_dump_raw('mock_cuda_bin'), CUOBJDUMP_FAT)

        # Test case 3: call on a file that is NOT an executable, object or archive:
        self.assertIsNone(get_cuda_object_dump_raw('mock_noncuda_file'))

        # Test case 4: call on a file that is an shared lib, but not a CUDA shared lib
        # Check debug message in this case
        debug_regex = re.compile(r"DEBUG .* does not appear to be a CUDA binary: cuobjdump failed to find device code "
                                 "in this file", re.M)
        old_log_level = st._log.getEffectiveLevel()
        st._log.setLevel(logging.DEBUG)
        with self.log_to_testlogfile():
            res = get_cuda_object_dump_raw('mock_non_cuda_sharedlib')
        st._log.setLevel(old_log_level)
        logtxt = read_file(self.logfile)
        self.assertIsNone(res)
        fail_msg = "Pattern '%s' should be found in: %s" % (debug_regex.pattern, logtxt)
        self.assertTrue(debug_regex.search(logtxt), fail_msg)

        # Test case 5: call on a file where cuobjdump produces really unexpected output
        error_pattern = r"Dumping CUDA binary file information for .* via .* failed!"
        self.assertErrorRegex(EasyBuildError, error_pattern, get_cuda_object_dump_raw,
                              path='mock_non_cuda_sharedlib_unexpected')

        # Test case 6: call on CUDA shared lib, which only contains PTX code
        self.assertEqual(get_cuda_object_dump_raw('mock_cuda_sharedlib'), CUOBJDUMP_PTX_ONLY)

        # Test case 7: call on CUDA static lib, which only contains device code
        self.assertEqual(get_cuda_object_dump_raw('mock_cuda_staticlib'), CUOBJDUMP_DEVICE_CODE_ONLY)

        # Restore original environment
        modify_env(os.environ, start_env, verbose=False)

    def test_get_cuda_architectures(self):
        """Test get_cuda_architectures function"""
        # This test modifies environment, make sure we can revert the changes:
        start_env = copy.deepcopy(os.environ)

        # Mock the shell command for certain known commands
        st.run_shell_cmd = mocked_run_shell_cmd

        # Put a cuobjdump on the path, doesn't matter what. It will be mocked anyway
        cuobjdump_dir = os.path.join(self.test_prefix, 'cuobjdump_dir')
        mkdir(cuobjdump_dir, parents=True)
        setvar('PATH', '%s:%s' % (cuobjdump_dir, os.getenv('PATH')))
        cuobjdump_file = os.path.join(cuobjdump_dir, 'cuobjdump')
        write_file(cuobjdump_file, "#!/bin/bash\n")
        write_file(cuobjdump_file, "echo 'Mock script, this should never actually be called\n'")
        adjust_permissions(cuobjdump_file, stat.S_IXUSR, add=True)  # Make sure our mock cuobjdump is executable

        # Test case 1: get raw output from mock_cuda_bin, a 'fat' binary
        mock_cuda_bin_device_codes = ['5.0', '6.0', '6.1', '7.0', '7.5', '8.0', '8.6', '8.9', '9.0', '9.0a']
        mock_cuda_bin_ptx = ['9.0', '9.0a']
        self.assertEqual(get_cuda_architectures('mock_cuda_bin', 'elf'), mock_cuda_bin_device_codes)
        self.assertEqual(get_cuda_architectures('mock_cuda_bin', 'ptx'), mock_cuda_bin_ptx)

        # Test case 2: call on a file that is NOT an executable, object or archive:
        self.assertIsNone(get_cuda_architectures('mock_noncuda_file', 'elf'))
        self.assertIsNone(get_cuda_architectures('mock_noncuda_file', 'ptx'))

        # Test case 3: call on a file that is an shared lib, but not a CUDA shared lib
        self.assertIsNone(get_cuda_architectures('mock_non_cuda_sharedlib', 'elf'))
        self.assertIsNone(get_cuda_architectures('mock_non_cuda_sharedlib', 'ptx'))

        # Test case 4: call on CUDA shared lib, which only contains PTX code
        warning_regex_elf = re.compile(r"WARNING Failed to find Fatbin elf code section\(s\) in cuobjdump output for "
                                       "mock_cuda_sharedlib", re.M)
        old_log_level = st._log.getEffectiveLevel()
        st._log.setLevel(logging.DEBUG)
        with self.log_to_testlogfile():
            res_elf = get_cuda_architectures('mock_cuda_sharedlib', 'elf')
            res_ptx = get_cuda_architectures('mock_cuda_sharedlib', 'ptx')
        st._log.setLevel(old_log_level)
        logtxt = read_file(self.logfile)
        self.assertIsNone(res_elf)
        fail_msg = "Pattern '%s' should be found in: %s" % (warning_regex_elf.pattern, logtxt)
        self.assertTrue(warning_regex_elf.search(logtxt), fail_msg)
        self.assertEqual(res_ptx, ['9.0', '9.0a'])

        # Test case 5: call on CUDA static lib, which only contains device code
        warning_regex_ptx = re.compile(r"WARNING Failed to find Fatbin ptx code section\(s\) in cuobjdump output for "
                                       "mock_cuda_staticlib", re.M)
        old_log_level = st._log.getEffectiveLevel()
        st._log.setLevel(logging.DEBUG)
        with self.log_to_testlogfile():
            res_elf = get_cuda_architectures('mock_cuda_staticlib', 'elf')
            res_ptx = get_cuda_architectures('mock_cuda_staticlib', 'ptx')
        st._log.setLevel(old_log_level)
        logtxt = read_file(self.logfile)
        self.assertIsNone(res_ptx)
        fail_msg = "Pattern '%s' should be found in: %s" % (warning_regex_ptx.pattern, logtxt)
        self.assertTrue(warning_regex_ptx.search(logtxt), fail_msg)
        self.assertEqual(res_elf, ['9.0', '9.0a'])

        # Test case 6: call on CUDA shared lib which lacks an arch = sm_XX entry (should never happen)
        warning_regex_elf = re.compile(r"WARNING Found Fatbin elf code section\(s\) in cuobjdump output for "
                                       "mock_invalid_cuda_sharedlib, but failed to extract CUDA architecture", re.M)
        old_log_level = st._log.getEffectiveLevel()
        st._log.setLevel(logging.DEBUG)
        with self.log_to_testlogfile():
            res_elf = get_cuda_architectures('mock_invalid_cuda_sharedlib', 'elf')
        st._log.setLevel(old_log_level)
        logtxt = read_file(self.logfile)
        fail_msg = "Pattern '%s' should be found in: %s" % (warning_regex_elf.pattern, logtxt)
        self.assertTrue(warning_regex_elf.search(logtxt), fail_msg)
        self.assertIsNone(res_elf)

        # Restore original environment
        modify_env(os.environ, start_env, verbose=False)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(SystemToolsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
