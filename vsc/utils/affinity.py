##
# Copyright 2012-2013 Ghent University
#
# This file is part of vsc-base,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/vsc-base
#
# vsc-base is free software: you can redistribute it and/or modify
# it under the terms of the GNU Library General Public License as
# published by the Free Software Foundation, either version 2 of
# the License, or (at your option) any later version.
#
# vsc-base is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public License
# along with vsc-base. If not, see <http://www.gnu.org/licenses/>.
##
"""
Linux cpu affinity.
    - Based on C{sched.h} and C{bits/sched.h},
    - see man pages for  C{sched_getaffinity} and C{sched_setaffinity}
    - also provides a C{cpuset} class to convert between human readable cpusets and the bit version
Linux priority
    - Based on sys/resources.h and bits/resources.h see man pages for
      C{getpriority} and C{setpriority}

@author: Stijn De Weirdt (Ghent University)
"""

import ctypes
import os
from ctypes.util import find_library
from vsc.utils.fancylogger import getLogger, setLogLevelDebug

_logger = getLogger("affinity")

_libc_lib = find_library('c')
_libc = ctypes.cdll.LoadLibrary(_libc_lib)

#/* Type for array elements in 'cpu_set_t'.  */
#typedef unsigned long int __cpu_mask;
cpu_mask_t = ctypes.c_ulong

##define __CPU_SETSIZE  1024
##define __NCPUBITS     (8 * sizeof(__cpu_mask))
CPU_SETSIZE = 1024
NCPUBITS = 8 * ctypes.sizeof(cpu_mask_t)
NMASKBITS = CPU_SETSIZE / NCPUBITS

#/* Priority limits.  */
##define PRIO_MIN        -20     /* Minimum priority a process can have.  */
##define PRIO_MAX        20      /* Maximum priority a process can have.  */
PRIO_MIN = -20
PRIO_MAX = 20

#/* The type of the WHICH argument to `getpriority' and `setpriority',
#   indicating what flavor of entity the WHO argument specifies.  * /
#enum __priority_which
##{
#  PRIO_PROCESS = 0, /* WHO is a process ID.  * /
##define PRIO_PROCESS PRIO_PROCESS
#  PRIO_PGRP = 1, /* WHO is a process group ID.  * /
##define PRIO_PGRP PRIO_PGRP
#  PRIO_USER = 2 /* WHO is a user ID.  * /
##define PRIO_USER PRIO_USER
##};
PRIO_PROCESS = 0
PRIO_PGRP = 1
PRIO_USER = 2

#/* using pid_t for __pid_t */
#typedef unsigned pid_t;
pid_t = ctypes.c_uint

##if defined __USE_GNU && !defined __cplusplus
#typedef enum __rlimit_resource __rlimit_resource_t;
#typedef enum __rusage_who __rusage_who_t;
#typedef enum __priority_which __priority_which_t;
##else
#typedef int __rlimit_resource_t;
#typedef int __rusage_who_t;
#typedef int __priority_which_t;
##endif
priority_which_t = ctypes.c_int

##  typedef __u_int __id_t;
id_t = ctypes.c_uint


#/* Data structure to describe CPU mask.  */
#typedef struct
#{
#  __cpu_mask __bits[__NMASKBITS];
#} cpu_set_t;
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
            indices = [int(x) for x in rng.split('-')] * 2  # always at least 2 elements: twice the same or start,end,start,end

            ## sanity check
            if indices[1] < indices[0]:
                self.log.raiseException("convert_hr_bits: end is lower then start in '%s'" % rng)
            elif indices[0] < 0:
                self.log.raiseException("convert_hr_bits: negative start in '%s'" % rng)
            elif indices[1] > CPU_SETSIZE + 1 :  # also covers start, since end > start
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
            for idx in xrange(NCPUBITS):
                self.cpus.append(bitmask & 1)
                bitmask >>= 1
        return self.cpus

    def set_cpus(self, cpus_list):
        """Given list, set it as cpus"""
        nr_cpus = len(cpus_list)
        if  nr_cpus > CPU_SETSIZE:
            self.log.warning("set_cpus: length cpu list %s is larger then cpusetsize %s. Truncating to cpusetsize" %
                           (nr_cpus , CPU_SETSIZE))
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
            cpus = [2 ** cpuidx for cpuidx, val in enumerate(self.cpus[idx * NCPUBITS:(idx + 1) * NCPUBITS]) if val == 1]
            __bits[idx] = cpu_mask_t(sum(cpus))
        ## sanity check
        if not prev_cpus == self.get_cpus():
            ## get_cpus() rescans
            self.log.raiseException("set_bits: something went wrong: previous cpus %s; current ones %s" % (prev_cpus[:20], self.cpus[:20]))
        else:
            self.log.debug("set_bits: new set to %s" % self.convert_bits_hr())

    def str_cpus(self):
        """Return a string representation of the cpus"""
        if self.cpus is None:
            self.get_cpus()
        return "".join(["%d" % x for x in self.cpus])

#/* Get the CPU affinity for a task */
#extern int sched_getaffinity (pid_t __pid, size_t __cpusetsize,
#                              cpu_set_t *__cpuset);
def sched_getaffinity(cs=None, pid=None):
    """Get the affinity"""
    if cs is None:
        cs = cpu_set_t()
    if pid is None:
        pid = os.getpid()

    ec = _libc.sched_getaffinity(pid_t(pid),
                              ctypes.sizeof(cpu_set_t),
                              ctypes.pointer(cs))
    if ec == 0:
        _logger.debug("sched_getaffinity for pid %s returned cpuset %s" % (pid, cs))
    else:
        _logger.error("sched_getaffinity failed for pid %s ec %s" % (pid, ec))
    return cs


#/* Set the CPU affinity for a task */
#extern int sched_setaffinity (pid_t __pid, size_t __cpusetsize,
#                              cpu_set_t *__cpuset);
def sched_setaffinity(cs, pid=None):
    """Set the affinity"""
    if pid is None:
        pid = os.getpid()

    ec = _libc.sched_setaffinity(pid_t(pid),
                              ctypes.sizeof(cpu_set_t),
                              ctypes.pointer(cs))
    if ec == 0:
        _logger.debug("sched_setaffinity for pid %s and cpuset %s" % (pid, cs))
    else:
        _logger.error("sched_setaffinity failed for pid %s cpuset %s ec %s" % (pid, cs, ec))

#/* Get index of currently used CPU.  */
#extern int sched_getcpu (void) __THROW;
def sched_getcpu():
    """Get currently used cpu"""
    return _libc.sched_getcpu()

#Utility function
#    tobin not used anymore
def tobin(s):
    """Convert integer to binary format"""
    ## bin() missing in 2.4
    # eg: self.cpus.extend([int(x) for x in tobin(bitmask).zfill(NCPUBITS)[::-1]])
    if s <= 1:
        return str(s)
    else:
        return tobin(s >> 1) + str(s & 1)


#/* Return the highest priority of any process specified by WHICH and WHO
#   (see above); if WHO is zero, the current process, process group, or user
#   (as specified by WHO) is used.  A lower priority number means higher
#   priority.  Priorities range from PRIO_MIN to PRIO_MAX (above).  */
#extern int getpriority (__priority_which_t __which, id_t __who) __THROW;
#
#/* Set the priority of all processes specified by WHICH and WHO (see above)
#   to PRIO.  Returns 0 on success, -1 on errors.  */
#extern int setpriority (__priority_which_t __which, id_t __who, int __prio)
#     __THROW;
def getpriority(which=None, who=None):
    """Get the priority"""
    if which is None:
        which = PRIO_PROCESS
    elif not which in (PRIO_PROCESS, PRIO_PGRP, PRIO_USER,):
        _logger.raiseException("getpriority: which %s not in correct range" % which)
    if who is None:
        who = 0  # current which-ever
    prio = _libc.getpriority(priority_which_t(which),
                             id_t(who),
                             )
    _logger.debug("getpriority prio %s for which %s who %s" % (prio, which, who))

    return prio

def setpriority(prio, which=None, who=None):
    """Set the priority (aka nice)"""
    if which is None:
        which = PRIO_PROCESS
    elif not which in (PRIO_PROCESS, PRIO_PGRP, PRIO_USER,):
        _logger.raiseException("setpriority: which %s not in correct range" % which)
    if who is None:
        who = 0  # current which-ever
    try:
        prio = int(prio)
    except:
        _logger.raiseException("setpriority: failed to convert priority %s into int" % prio)

    if prio < PRIO_MIN or prio > PRIO_MAX:
        _logger.raiseException("setpriority: prio not in allowed range MIN %s MAX %s" % (PRIO_MIN, PRIO_MAX))

    ec = _libc.setpriority(priority_which_t(which),
                           id_t(who),
                           ctypes.c_int(prio)
                           )
    if ec == 0:
        _logger.debug("setpriority for which %s who %s prio %s" % (which, who, prio))
    else:
        _logger.error("setpriority failed for which %s who %s prio %s" % (which, who, prio))


if __name__ == '__main__':
    ## some examples of usage
    setLogLevelDebug()

    cs = cpu_set_t()
    print "__bits", cs.__bits
    print "sizeof cpu_set_t", ctypes.sizeof(cs)
    x = sched_getaffinity()
    print "x", x
    hr_mask = "1-5,7,9,10-15"
    print hr_mask, x.convert_hr_bits(hr_mask)
    print x
    x.set_bits()
    print x

    sched_setaffinity(x)
    print sched_getaffinity()

    x.convert_hr_bits("1")
    x.set_bits()
    sched_setaffinity(x)
    y = sched_getaffinity()
    print x, y

    print sched_getcpu()

    ## resources
    ## nice -n 5 python affinity.py prints 5 here
    currentprio = getpriority()
    print "getpriority", currentprio
    newprio = 10
    setpriority(newprio)
    newcurrentprio = getpriority()
    print "getpriority", newcurrentprio
    assert newcurrentprio == newprio
