##
# Copyright 2013-2014 Ghent University
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
Unit tests for systemtools.py

@author: Kenneth hoste (Ghent University)
"""
import os
from os.path import exists as orig_os_path_exists
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

import easybuild.tools.systemtools as st
from easybuild.tools.filetools import read_file
from easybuild.tools.run import run_cmd
from easybuild.tools.systemtools import AMD, ARM, DARWIN, INTEL, LINUX, UNKNOWN
from easybuild.tools.systemtools import get_avail_core_count
from easybuild.tools.systemtools import get_cpu_model, get_cpu_speed, get_cpu_vendor, get_glibc_version
from easybuild.tools.systemtools import get_os_type, get_os_name, get_os_version, get_platform_name, get_shared_lib_ext
from easybuild.tools.systemtools import get_system_info


MAX_FREQ_FP = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq'
PROC_CPUINFO_FP = '/proc/cpuinfo'

PROC_CPUINFO_TXT = None
PROC_CPUINFO_TXT_X86 = """processor	: 0
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
PROC_CPUINFO_TXT_POWER = """
processor	: 0
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


def mocked_read_file(fp):
    """Mocked version of read_file, with specified contents for known filenames."""
    known_fps = {
        MAX_FREQ_FP:  '2850000',
        PROC_CPUINFO_FP: PROC_CPUINFO_TXT,
    }
    if fp in known_fps:
        return known_fps[fp]
    else:
        return read_file(fp)

def mocked_os_path_exists(mocked_fp, fp):
    """Mocked version of os.path.exists, returns True for a particular specified filepath."""
    if fp == mocked_fp:
        return True
    else:
        orig_os_path_exists(fp)

def mocked_run_cmd(cmd, **kwargs):
    """Mocked version of run_cmd, with specified output for known commands."""
    known_cmds = {
        "sysctl -n hw.cpufrequency_max": "2400000000",
        "sysctl -n hw.ncpu": '10',
    }
    if cmd in known_cmds:
        if 'simple' in kwargs and kwargs['simple']:
            return True
        else:
            return (known_cmds[cmd], 0)
    else:
        return run_cmd(cmd, **kwargs)


class SystemToolsTest(EnhancedTestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def setUp(self):
        """Set up systemtools test."""
        super(SystemToolsTest, self).setUp()
        self.orig_get_os_type = st.get_os_type
        self.orig_os_path_exists = st.os.path.exists
        self.orig_read_file = st.read_file
        self.orig_run_cmd = st.run_cmd

    def tearDown(self):
        """Cleanup after systemtools test."""
        st.os.path.exists = self.orig_os_path_exists
        st.read_file = self.orig_read_file
        st.get_os_type = self.orig_get_os_type
        super(SystemToolsTest, self).tearDown()

    def test_avail_core_count(self):
        """Test getting core count."""
        core_count = get_avail_core_count()
        self.assertTrue(isinstance(core_count, int), "core_count has type int: %s, %s" % (core_count, type(core_count)))
        self.assertTrue(core_count > 0, "core_count %d > 0" % core_count)

        st.get_os_type = lambda: st.LINUX
        orig_sched_getaffinity = st.sched_getaffinity
        class MockedSchedGetaffinity(object):
            cpus = [1L, 1L, 0L, 0L, 1L, 1L, 0L, 0L, 1L, 1L, 0L, 0L]
        st.sched_getaffinity = lambda: MockedSchedGetaffinity()
        self.assertEqual(get_avail_core_count(), 6)
        st.sched_getaffinity = orig_sched_getaffinity

        st.get_os_type = lambda: st.DARWIN
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_avail_core_count(), 10)

    def test_cpu_model(self):
        """Test getting CPU model."""
        cpu_model = get_cpu_model()
        self.assertTrue(isinstance(cpu_model, basestring))

    def test_cpu_speed(self):
        """Test getting CPU speed."""
        cpu_speed = get_cpu_speed()
        self.assertTrue(isinstance(cpu_speed, float))
        self.assertTrue(cpu_speed > 0.0)

        # test for particular type of system by mocking used functions
        st.get_os_type = lambda: st.LINUX
        st.read_file = mocked_read_file
        st.os.path.exists = lambda fp: mocked_os_path_exists(PROC_CPUINFO_FP, fp)

        # tweak global constant used by mocked_read_file
        global PROC_CPUINFO_TXT

        # /proc/cpuinfo on Linux x86 (no cpufreq)
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_X86
        self.assertEqual(get_cpu_speed(), 2600.075)

        # /proc/cpuinfo on Linux POWER
        PROC_CPUINFO_TXT = PROC_CPUINFO_TXT_POWER
        self.assertEqual(get_cpu_speed(), 3550.0)

        # Linux (x86) with cpufreq
        st.os.path.exists = lambda fp: mocked_os_path_exists(MAX_FREQ_FP, fp)
        self.assertEqual(get_cpu_speed(), 2850.0)

        # OS X
        st.os.path.exists = self.orig_os_path_exists
        st.get_os_type = lambda: st.DARWIN
        st.run_cmd = mocked_run_cmd
        self.assertEqual(get_cpu_speed(), 2400.0)

    def test_cpu_vendor(self):
        """Test getting CPU vendor."""
        cpu_vendor = get_cpu_vendor()
        self.assertTrue(cpu_vendor in [AMD, ARM, INTEL, UNKNOWN])

    def test_os_type(self):
        """Test getting OS type."""
        os_type = get_os_type()
        self.assertTrue(os_type in [DARWIN, LINUX])

    def test_shared_lib_ext(self):
        """Test getting extension for shared libraries."""
        ext = get_shared_lib_ext()
        self.assertTrue(ext in ['dylib', 'so'])

    def test_platform_name(self):
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

    def test_os_name(self):
        """Test getting OS name."""
        os_name = get_os_name()
        self.assertTrue(isinstance(os_name, basestring) or os_name == UNKNOWN)

    def test_os_version(self):
        """Test getting OS version."""
        os_version = get_os_version()
        self.assertTrue(isinstance(os_version, basestring) or os_version == UNKNOWN)

    def test_glibc_version(self):
        """Test getting glibc version."""
        glibc_version = get_glibc_version()
        self.assertTrue(isinstance(glibc_version, basestring) or glibc_version == UNKNOWN)

    def test_system_info(self):
        """Test getting system info."""
        system_info = get_system_info()
        self.assertTrue(isinstance(system_info, dict))

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(SystemToolsTest)

if __name__ == '__main__':
    main()
