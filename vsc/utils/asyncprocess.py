# #
# Copyright 2005 Josiah Carlson
# The Asynchronous Python Subprocess recipe was originally created by Josiah Carlson.
# and released under the GNU Library General Public License v2 or any later version
# on Jan 23, 2013.
#
# http://code.activestate.com/recipes/440554/
#
# Copyright 2009-2013 Ghent University
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
# #

"""
Module to allow Asynchronous subprocess use on Windows and Posix platforms

The 'subprocess' module in Python 2.4 has made creating and accessing subprocess
streams in Python relatively convenient for all supported platforms,
but what if you want to interact with the started subprocess?
That is, what if you want to send a command, read the response,
and send a new command based on that response?

Now there is a solution.
The included subprocess.Popen subclass adds three new commonly used methods:
 - C{recv(maxsize=None)}
 - C{recv_err(maxsize=None)}
 - and C{send(input)}

along with a utility method:
 - {send_recv(input='', maxsize=None)}.

C{recv()} and C{recv_err()} both read at most C{maxsize} bytes from the started subprocess.
C{send()} sends strings to the started subprocess. C{send_recv()} will send the provided input,
and read up to C{maxsize} bytes from both C{stdout} and C{stderr}.

If any of the pipes are closed, the attributes for those pipes will be set to None,
and the methods will return None.

  - downloaded 05/08/2010
  - modified
    - added STDOUT handle
    - added maxread to recv_some (2012-08-30)

@author: Josiah Carlson
@author: Stijn De Weirdt (Ghent University)
"""

import errno
import fcntl  # @UnresolvedImport
import os
import select  # @UnresolvedImport
import subprocess
import time


PIPE = subprocess.PIPE
STDOUT = subprocess.STDOUT
MESSAGE = "Other end disconnected!"


class Popen(subprocess.Popen):
    def recv(self, maxsize=None):
        return self._recv('stdout', maxsize)

    def recv_err(self, maxsize=None):
        return self._recv('stderr', maxsize)

    def send_recv(self, inp='', maxsize=None):
        return self.send(inp), self.recv(maxsize), self.recv_err(maxsize)

    def get_conn_maxsize(self, which, maxsize):
        if maxsize is None:
            maxsize = 1024
        elif maxsize == 0:  # do not use < 1: -1 means all
            maxsize = 1
        return getattr(self, which), maxsize

    def _close(self, which):
        getattr(self, which).close()
        setattr(self, which, None)

    def send(self, inp):
        if not self.stdin:
            return None

        if not select.select([], [self.stdin], [], 0)[1]:
            return 0

        try:
            written = os.write(self.stdin.fileno(), inp)
        except OSError, why:
            if why[0] == errno.EPIPE:  # broken pipe
                return self._close('stdin')
            raise

        return written

    def _recv(self, which, maxsize):
        conn, maxsize = self.get_conn_maxsize(which, maxsize)
        if conn is None:
            return None

        flags = fcntl.fcntl(conn, fcntl.F_GETFL)
        if not conn.closed:
            fcntl.fcntl(conn, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        try:
            if not select.select([conn], [], [], 0)[0]:
                return ''

            r = conn.read(maxsize)
            if not r:
                return self._close(which)  # close when nothing left to read

            if self.universal_newlines:
                r = self._translate_newlines(r)
            return r
        finally:
            if not conn.closed:
                fcntl.fcntl(conn, fcntl.F_SETFL, flags)


def recv_some(p, t=.1, e=False, tr=5, stderr=False, maxread=None):
    """
    @param p: process
    @param t: max time to wait without any output before returning
    @param e: boolean, raise exception is process stopped
    @param tr: time resolution used for intermediate sleep
    @param stderr: boolean, read from stderr
    @param maxread: stop when max read bytes have been read (before timeout t kicks in) (-1: read all)

    Changes made wrt original:
      - add maxread here
      - set e to False by default
    """
    if maxread is None:
        maxread = -1

    if tr < 1:
        tr = 1
    x = time.time() + t
    y = []
    len_y = 0
    r = ''
    pr = p.recv
    if stderr:
        pr = p.recv_err
    while (maxread < 0 or len_y <= maxread) and (time.time() < x or r):
        r = pr(maxread)
        if r is None:
            if e:
                raise Exception(MESSAGE)
            else:
                break
        elif r:
            y.append(r)
            len_y += len(r)
        else:
            time.sleep(max((x - time.time()) / tr, 0))
    return ''.join(y)


def send_all(p, data):
    """
    Send data to process p
    """
    while len(data):
        sent = p.send(data)
        if sent is None:
            raise Exception(MESSAGE)
        data = buffer(data, sent)
