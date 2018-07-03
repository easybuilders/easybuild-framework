##
# Copyright 2013-2018 Ghent University
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
import re
import sys

from os.path import exists as orig_os_path_exists
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

import easybuild.tools.systemtools as st
from easybuild.tools.filetools import read_file
from easybuild.tools.run import run_cmd
from easybuild.tools.systemtools import CPU_ARCHITECTURES, AARCH32, AARCH64, POWER, X86_64
from easybuild.tools.systemtools import CPU_FAMILIES, POWER_LE, DARWIN, LINUX, UNKNOWN
from easybuild.tools.systemtools import CPU_VENDORS, AMD, APM, ARM, CAVIUM, IBM, INTEL
from easybuild.tools.systemtools import MAX_FREQ_FP, PROC_CPUINFO_FP, PROC_MEMINFO_FP
from easybuild.tools.systemtools import det_parallelism, get_avail_core_count, get_cpu_architecture, get_cpu_family
from easybuild.tools.systemtools import get_cpu_features, get_cpu_model, get_cpu_speed, get_cpu_vendor
from easybuild.tools.systemtools import get_glibc_version, get_os_type, get_os_name, get_os_version, get_platform_name
from easybuild.tools.systemtools import get_shared_lib_ext, get_system_info, get_total_memory, get_gcc_version


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
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm 3dnowext 3dnow constant_tsc rep_good nopl nonstop_tsc extd_apicid pni monitor cx16 popcnt lahf_lm cmp_legacy svm extapic cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw ibs skinit wdt hw_pstate npt lbrv svm_lock nrip_save pausefilter vmmcall
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
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm 3dnowext 3dnow constant_tsc rep_good nopl nonstop_tsc extd_apicid pni monitor cx16 popcnt lahf_lm cmp_legacy svm extapic cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw ibs skinit wdt hw_pstate npt lbrv svm_lock nrip_save pausefilter vmmcall
bogomips	: 4400.54
TLB size	: 1024 4K pages
clflush size	: 64
cache_alignment	: 64
address sizes	: 48 bits physical, 48 bits virtual
power management: ts ttp tm stc 100mhzsteps hwpstate
"""
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
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc arch_perfmon pebs bts rep_good xtopology nonstop_tsc aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 cx16 xtpr pdcm pcid dca sse4_1 sse4_2 x2apic popcnt tsc_deadline_timer aes xsave avx lahf_lm ida arat xsaveopt pln pts dts tpr_shadow vnmi flexpriority ept vpid
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
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc arch_perfmon pebs bts rep_good xtopology nonstop_tsc aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 cx16 xtpr pdcm pcid dca sse4_1 sse4_2 x2apic popcnt tsc_deadline_timer aes xsave avx lahf_lm ida arat xsaveopt pln pts dts tpr_shadow vnmi flexpriority ept vpid
bogomips	: 5200.04
clflush size	: 64
cache_alignment	: 64
address sizes	: 46 bits physical, 48 bits virtual
power management:
"""
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

MACHINE_NAME = None


def mocked_read_file(fp):
    """Mocked version of read_file, with specified contents for known filenames."""
    known_fps = {
        MAX_FREQ_FP:  '2850000',
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


def mocked_run_cmd(cmd, **kwargs):
    """Mocked version of run_cmd, with specified output for known commands."""
    known_cmds = {
        "gcc --version": "gcc (GCC) 5.1.1 20150618 (Red Hat 5.1.1-4)",
        "ldd --version": "ldd (GNU libc) 2.12",
        "sysctl -n hw.cpufrequency_max": "2400000000",
        "sysctl -n hw.ncpu": '10',
        "sysctl -n hw.memsize": '8589934592',
        "sysctl -n machdep.cpu.brand_string": "Intel(R) Core(TM) i5-4258U CPU @ 2.40GHz",
        "sysctl -n machdep.cpu.extfeatures": "SYSCALL XD 1GBPAGE EM64T LAHF LZCNT RDTSCP TSCI",
        "sysctl -n machdep.cpu.features": "FPU VME DE PSE TSC MSR PAE MCE CX8 APIC SEP MTRR PGE MCA CMOV PAT PSE36 CLFSH DS ACPI MMX FXSR SSE SSE2 SS HTT TM PBE SSE3 PCLMULQDQ DTES64 MON DSCPL VMX EST TM2 SSSE3 FMA CX16 TPR PDCM SSE4.1 SSE4.2 x2APIC MOVBE POPCNT AES PCID XSAVE OSXSAVE SEGLIM64 TSCTMR AVX1.0 RDRAND F16C",
        "sysctl -n machdep.cpu.leaf7_features": "SMEP ERMS RDWRFSGS TSC_THREAD_OFFSET BMI1 AVX2 BMI2 INVPCID FPU_CSDS",
        "sysctl -n machdep.cpu.vendor": 'GenuineIntel',
        "ulimit -u": '40',
    }
    if cmd in known_cmds:
        if 'simple' in kwargs and kwargs['simple']:
            return True
        else:
            return (known_cmds[cmd], 0)
    else:
        return run_cmd(cmd, **kwargs)

def mocked_uname():
    """Mocked version of platform.uname, with specified contents for known machine names."""
    return ('Linux', 'localhost', '3.16', '3.16', MACHINE_NAME, '')

class SystemToolsTest(EnhancedTestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def setUp(self):
        """Set up systemtools test."""
        super(SystemToolsTest, self).setUp()
        self.orig_get_cpu_architecture = st.get_cpu_architecture
        self.orig_get_os_type = st.get_os_type
        self.orig_is_readable = st.is_readable
        self.orig_read_file = st.read_file
        self.orig_run_cmd = st.run_cmd
        self.orig_platform_uname = st.platform.uname
        self.orig_get_tool_version = st.get_tool_version

    def tearDown(self):
        """Cleanup after systemtools test."""
        st.is_readable = self.orig_is_readable
        st.read_file = self.orig_read_file
        st.get_cpu_architecture = self.orig_get_cpu_architecture
        st.get_os_type = self.orig_get_os_type
        st.run_cmd = self.orig_run_cmd
        st.platform.uname = self.orig_platform_uname
        st.get_tool_version = self.orig_get_tool_version
        super(SystemToolsTest, self).tearDown()

    def test_avail_core_count_native(self):
        """Test getting core count."""
        core_count = get_avail_core_count()
        self.assertTrue(isinstance(core_count, int), "core_count has type int: %s, %s" % (core_count, type(core_count)))
        self.assertTrue(core_count > 0, "core_count %d > 0" % core_count)

    def test_avail_core_count_linux(self):
        """Test getting core count (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        orig_sched_getaffinity = st.sched_getaffinity
        class MockedSchedGetaffinity(object):
            cpus = [1L, 1L, 0L, 0L, 1L, 1L, 0L, 0L, 1L, 1L, 0L, 0L]
        st.sched_getaffinity = lambda: MockedSchedGetaffinity()
        self.assertEqual(get_avail_core_count(), 6)
        st.sched_getaffinity = orig_sched_getaffinity

    def test_avail_core_count_darwin(self):
        """Test getting core count (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_avail_core_count(), 10)

    def test_cpu_model_native(self):
        """Test getting CPU model."""
        cpu_model = get_cpu_model()
        self.assertTrue(isinstance(cpu_model, basestring))

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
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_cpu_model(), "Intel(R) Core(TM) i5-4258U CPU @ 2.40GHz")

    def test_cpu_speed_native(self):
        """Test getting CPU speed."""
        cpu_speed = get_cpu_speed()
        self.assertTrue(isinstance(cpu_speed, float) or cpu_speed is None)
        self.assertTrue(cpu_speed > 0.0 or cpu_speed is None)

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
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_cpu_speed(), 2400.0)

    def test_cpu_features_native(self):
        """Test getting CPU features."""
        cpu_feat = get_cpu_features()
        self.assertTrue(isinstance(cpu_feat, list))
        self.assertTrue(len(cpu_feat) > 0)
        self.assertTrue(all([isinstance(x, basestring) for x in cpu_feat]))

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
        st.run_cmd = mocked_run_cmd
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
        self.assertTrue(arch in CPU_ARCHITECTURES)

    def test_cpu_architecture(self):
        """Test getting the CPU architecture (mocked)."""
        st.platform.uname = mocked_uname
        global MACHINE_NAME

        machine_names = {
            'aarch64': AARCH64,
            'aarch64_be': AARCH64,
            'armv7l': AARCH32,
            'ppc64': POWER,
            'ppc64le': POWER,
            'x86_64': X86_64,
            'some_fancy_arch': UNKNOWN,
        }
        for name in machine_names:
            MACHINE_NAME = name
            self.assertEqual(get_cpu_architecture(), machine_names[name])

    def test_cpu_vendor_native(self):
        """Test getting CPU vendor."""
        cpu_vendor = get_cpu_vendor()
        self.assertTrue(cpu_vendor in CPU_VENDORS)

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
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_cpu_vendor(), INTEL)

    def test_cpu_family_native(self):
        """Test get_cpu_family function."""
        run_cmd.clear_cache()
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
        st.run_cmd = mocked_run_cmd
        run_cmd.clear_cache()
        self.assertEqual(get_cpu_family(), INTEL)

    def test_os_type(self):
        """Test getting OS type."""
        os_type = get_os_type()
        self.assertTrue(os_type in [DARWIN, LINUX])

    def test_shared_lib_ext_native(self):
        """Test getting extension for shared libraries."""
        ext = get_shared_lib_ext()
        self.assertTrue(ext in ['dylib', 'so'])

    def test_shared_lib_ext_native(self):
        """Test getting extension for shared libraries (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        self.assertEqual(get_shared_lib_ext(), 'so')

    def test_shared_lib_ext_native(self):
        """Test getting extension for shared libraries (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        self.assertEqual(get_shared_lib_ext(), 'dylib')

    def test_platform_name_native(self):
        """Test getting platform name."""
        platform_name_nover = get_platform_name()
        self.assertTrue(isinstance(platform_name_nover, basestring))
        len_nover = len(platform_name_nover.split('-'))
        self.assertTrue(len_nover >= 3)

        platform_name_ver = get_platform_name(withversion=True)
        self.assertTrue(isinstance(platform_name_ver, basestring))
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
        self.assertTrue(isinstance(os_name, basestring) or os_name == UNKNOWN)

    def test_os_version(self):
        """Test getting OS version."""
        os_version = get_os_version()
        self.assertTrue(isinstance(os_version, basestring) or os_version == UNKNOWN)

    def test_gcc_version_native(self):
        """Test getting gcc version."""
        gcc_version = get_gcc_version()
        self.assertTrue(isinstance(gcc_version, basestring) or gcc_version == None)

    def test_gcc_version_linux(self):
        """Test getting gcc version (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_gcc_version(), '5.1.1')

    def test_gcc_version_darwin(self):
        """Test getting gcc version (mocked for Darwin)."""
        st.get_os_type = lambda: st.DARWIN
        st.run_cmd = lambda *args, **kwargs: ("Apple LLVM version 7.0.0 (clang-700.1.76)", 0)
        self.assertEqual(get_gcc_version(), None)

    def test_glibc_version_native(self):
        """Test getting glibc version."""
        glibc_version = get_glibc_version()
        self.assertTrue(isinstance(glibc_version, basestring) or glibc_version == UNKNOWN)

    def test_glibc_version_linux(self):
        """Test getting glibc version (mocked for Linux)."""
        st.get_os_type = lambda: st.LINUX
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_glibc_version(), '2.12')

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
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_total_memory(), 8192)

    def test_get_total_memory_native(self):
        """Test the function that gets the total memory."""
        memtotal = get_total_memory()
        self.assertTrue(isinstance(memtotal, int))

    def test_system_info(self):
        """Test getting system info."""
        system_info = get_system_info()
        self.assertTrue(isinstance(system_info, dict))

    def test_det_parallelism_native(self):
        """Test det_parallelism function (native calls)."""
        self.assertTrue(det_parallelism() > 0)
        # specified parallellism
        self.assertEqual(det_parallelism(par=5), 5)
        # max parallellism caps
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
        st.run_cmd = mocked_run_cmd
        self.assertTrue(det_parallelism(), 4)
        self.assertTrue(det_parallelism(par=6), 4)
        self.assertTrue(det_parallelism(maxpar=2), 2)

        st.get_avail_core_count = orig_get_avail_core_count

    def test_det_terminal_size(self):
        """Test det_terminal_size function."""
        (height, width) = st.det_terminal_size()
        self.assertTrue(isinstance(height, int) and height >= 0)
        self.assertTrue(isinstance(width, int) and width >= 0)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(SystemToolsTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
