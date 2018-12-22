#
# Copyright 2012-2018 Ghent University
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
Linux cpu affinity.
    - Based on C{sched.h} and C{bits/sched.h},
    - see man pages for  C{sched_getaffinity} and C{sched_setaffinity}
    - also provides a C{cpuset} class to convert between human readable cpusets and the bit version
Linux priority
    - Based on sys/resources.h and bits/resources.h see man pages for
      C{getpriority} and C{setpriority}

:author: Stijn De Weirdt (Ghent University)
"""

import ctypes
import os
from ctypes.util import find_library

from easybuild.base.fancylogger import getLogger

_logger = getLogger("affinity")

_libc_lib = find_library('c')
_libc = ctypes.cdll.LoadLibrary(_libc_lib)

# /* Type for array elements in 'cpu_set_t'.  */
# typedef unsigned long int __cpu_mask;
cpu_mask_t = ctypes.c_ulong

# define __CPU_SETSIZE  1024
# define __NCPUBITS     (8 * sizeof(__cpu_mask))
CPU_SETSIZE = 1024
NCPUBITS = 8 * ctypes.sizeof(cpu_mask_t)
NMASKBITS = CPU_SETSIZE / NCPUBITS

# /* using pid_t for __pid_t */
# typedef unsigned pid_t;
pid_t = ctypes.c_uint


# /* Data structure to describe CPU mask.  */
# typedef struct
# {
#   __cpu_mask __bits[__NMASKBITS];
# } cpu_set_t;
class cpu_set_t(ctypes.Structure):
    """Class that implements the cpu_set_t struct
        also provides some methods to convert between bit representation and soem human readable format
    """
    _fields_ = [('__bits', cpu_mask_t * NMASKBITS)]

    def __init__(self, *args, **kwargs):
        super(cpu_set_t, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)
        self.cpus = None

    def __str__(self):
        return self.convert_bits_hr()

    def convert_hr_bits(self, txt):
        """Convert human readable text into bits"""
        self.cpus = [0] * CPU_SETSIZE
        for rng in txt.split(','):
            # always at least 2 elements: twice the same or start,end,start,end
            indices = [int(x) for x in rng.split('-')] * 2

            # sanity check
            if indices[1] < indices[0]:
                self.log.raiseException("convert_hr_bits: end is lower then start in '%s'" % rng)
            elif indices[0] < 0:
                self.log.raiseException("convert_hr_bits: negative start in '%s'" % rng)
            elif indices[1] > CPU_SETSIZE + 1:  # also covers start, since end > start
                self.log.raiseException("convert_hr_bits: end larger then max %s in '%s'" % (CPU_SETSIZE, rng))

            self.cpus[indices[0]:indices[1] + 1] = [1] * (indices[1] + 1 - indices[0])
        self.log.debug("convert_hr_bits: converted %s into cpus %s" % (txt, self.cpus))

    def convert_bits_hr(self):
        """Convert __bits into human readable text"""
        if self.cpus is None:
            self.get_cpus()
        cpus_index = [idx for idx, cpu in enumerate(self.cpus) if cpu == 1]
        prev = -2  # not adjacent to 0 !
        parsed_idx = []
        for idx in cpus_index:
            if prev + 1 < idx:
                parsed_idx.append("%s" % idx)
            else:
                first_idx = parsed_idx[-1].split("-")[0]
                parsed_idx[-1] = "%s-%s" % (first_idx, idx)
            prev = idx
        return ",".join(parsed_idx)

    def get_cpus(self):
        """Convert bits in list len == CPU_SETSIZE
            Use 1 / 0 per cpu
        """
        self.cpus = []
        for bitmask in getattr(self, '__bits'):
            for _ in range(NCPUBITS):
                self.cpus.append(bitmask & 1)
                bitmask >>= 1
        return self.cpus

    def set_cpus(self, cpus_list):
        """Given list, set it as cpus"""
        nr_cpus = len(cpus_list)
        if nr_cpus > CPU_SETSIZE:
            self.log.warning("set_cpus: length cpu list %s is larger then cpusetsize %s. Truncating to cpusetsize" %
                             (nr_cpus, CPU_SETSIZE))
            cpus_list = cpus_list[:CPU_SETSIZE]
        elif nr_cpus < CPU_SETSIZE:
            cpus_list.extend([0] * (CPU_SETSIZE - nr_cpus))

        self.cpus = cpus_list

    def set_bits(self, cpus=None):
        """Given self.cpus, set the bits"""
        if cpus is not None:
            self.set_cpus(cpus)
        __bits = getattr(self, '__bits')
        prev_cpus = map(long, self.cpus)
        for idx in xrange(NMASKBITS):
            cpus = [2 ** cpuidx for cpuidx, val in
                    enumerate(self.cpus[idx * NCPUBITS:(idx + 1) * NCPUBITS]) if val == 1]
            __bits[idx] = cpu_mask_t(sum(cpus))
        # sanity check
        if prev_cpus == self.get_cpus():
            self.log.debug("set_bits: new set to %s" % self.convert_bits_hr())
        else:
            # get_cpus() rescans
            self.log.raiseException("set_bits: something went wrong: previous cpus %s; current ones %s" %
                                    (prev_cpus[:20], self.cpus[:20]))

    def str_cpus(self):
        """Return a string representation of the cpus"""
        if self.cpus is None:
            self.get_cpus()
        return "".join(["%d" % x for x in self.cpus])


# /* Get the CPU affinity for a task */
# extern int sched_getaffinity (pid_t __pid, size_t __cpusetsize,
#                              cpu_set_t *__cpuset);
def sched_getaffinity(cs=None, pid=None):
    """Get the affinity"""
    if cs is None:
        cs = cpu_set_t()
    if pid is None:
        pid = os.getpid()

    ec = _libc.sched_getaffinity(pid_t(pid), ctypes.sizeof(cpu_set_t), ctypes.pointer(cs))
    if ec == 0:
        _logger.debug("sched_getaffinity for pid %s returned cpuset %s" % (pid, cs))
    else:
        _logger.error("sched_getaffinity failed for pid %s ec %s" % (pid, ec))
    return cs
