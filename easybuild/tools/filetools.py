##
# Copyright 2009-2013 Ghent University
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
Set of file tools.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""
import errno
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import urllib
from vsc import fancylogger

import easybuild.tools.build_log  # @UnusedImport (required to get an EasyBuildLog object from fancylogger.getLogger)
import easybuild.tools.environment as env
from easybuild.tools.asyncprocess import Popen, PIPE, STDOUT
from easybuild.tools.asyncprocess import send_all, recv_some


_log = fancylogger.getLogger('filetools', fname=False)
errorsFoundInLog = 0

# constants for strictness levels
IGNORE = 'ignore'
WARN = 'warn'
ERROR = 'error'

# default strictness level
strictness = WARN

# easyblock class prefix
EASYBLOCK_CLASS_PREFIX = 'EB_'

# character map for encoding strings
STRING_ENCODING_CHARMAP = {
    r' ': "_space_",
    r'!': "_exclamation_",
    r'"': "_quotation_",
    r'#': "_hash_",
    r'$': "_dollar_",
    r'%': "_percent_",
    r'&': "_ampersand_",
    r'(': "_leftparen_",
    r')': "_rightparen_",
    r'*': "_asterisk_",
    r'+': "_plus_",
    r',': "_comma_",
    r'-': "_minus_",
    r'.': "_period_",
    r'/': "_slash_",
    r':': "_colon_",
    r';': "_semicolon_",
    r'<': "_lessthan_",
    r'=': "_equals_",
    r'>': "_greaterthan_",
    r'?': "_question_",
    r'@': "_atsign_",
    r'[': "_leftbracket_",
    r'\'': "_apostrophe_",
    r'\\': "_backslash_",
    r']': "_rightbracket_",
    r'^': "_circumflex_",
    r'_': "_underscore_",
    r'`': "_backquote_",
    r'{': "_leftcurly_",
    r'|': "_verticalbar_",
    r'}': "_rightcurly_",
    r'~': "_tilde_",
}


def read_file(path, log_error=True):
    """Read contents of file at given path, in a robust way."""
    f = None
    # note: we can't use try-except-finally, because Python 2.4 doesn't support it as a single block
    try:
        f = open(path, 'r')
        txt = f.read()
        f.close()
        return txt
    except IOError, err:
        # make sure file handle is always closed
        if f is not None:
            f.close()
        if log_error:
            _log.error("Failed to read %s: %s" % (path, err))
        else:
            return None


def write_file(path, txt):
    """Write given contents to file at given path (overwrites current file contents!)."""
    f = None
    # note: we can't use try-except-finally, because Python 2.4 doesn't support it as a single block
    try:
        f = open(path, 'w')
        f.write(txt)
        f.close()
    except IOError, err:
        # make sure file handle is always closed
        if f is not None:
            f.close()
        _log.error("Failed to write to %s: %s" % (path, err))


def extract_file(fn, dest, cmd=None, extra_options=None, overwrite=False):
    """
    Given filename fn, try to extract in directory dest
    - returns the directory name in case of success
    """
    if not os.path.isfile(fn):
        _log.error("Can't extract file %s: no such file" % fn)

    if not os.path.isdir(dest):
        ## try to create it
        try:
            os.makedirs(dest)
        except OSError, err:
            _log.exception("Can't extract file %s: directory %s can't be created: %err " % (fn, dest, err))

    ## use absolute pathnames from now on
    absDest = os.path.abspath(dest)

    ## change working directory
    try:
        _log.debug("Unpacking %s in directory %s." % (fn, absDest))
        os.chdir(absDest)
    except OSError, err:
        _log.error("Can't change to directory %s: %s" % (absDest, err))

    if not cmd:
        cmd = extract_cmd(fn, overwrite=overwrite)
    else:
        # complete command template with filename
        cmd = cmd % fn
    if not cmd:
        _log.error("Can't extract file %s with unknown filetype" % fn)

    if extra_options:
        cmd = "%s %s" % (cmd, extra_options)

    run_cmd(cmd, simple=True)

    return find_base_dir()


def which(cmd):
    """Return (first) path in $PATH for specified command, or None if command is not found."""
    paths = os.environ.get('PATH', '').split(os.pathsep)
    for path in paths:
        cmd_path = os.path.join(path, cmd)
        # only accept path is command is there, and both readable and executable
        if os.access(cmd_path, os.R_OK | os.X_OK):
            _log.info("Command %s found at %s" % (cmd, cmd_path))
            return cmd_path
    _log.warning("Could not find command '%s' (with permissions to read/execute it) in $PATH (%s)" % (cmd, paths))
    return None

def download_file(filename, url, path):
    """Download a file from the given URL, to the specified path."""

    _log.debug("Downloading %s from %s to %s" % (filename, url, path))

    # make sure directory exists
    basedir = os.path.dirname(path)
    if not os.path.exists(basedir):
        os.makedirs(basedir)

    downloaded = False
    attempt_cnt = 0

    # try downloading three times max.
    while not downloaded and attempt_cnt < 3:

        (_, httpmsg) = urllib.urlretrieve(url, path)

        if httpmsg.type == "text/html" and not filename.endswith('.html'):
            _log.warning("HTML file downloaded but not expecting it, so assuming invalid download.")
            _log.debug("removing downloaded file %s from %s" % (filename, path))
            try:
                os.remove(path)
            except OSError, err:
                _log.error("Failed to remove downloaded file:" % err)
        else:
            _log.info("Downloading file %s from url %s: done" % (filename, url))
            downloaded = True
            return path

        attempt_cnt += 1
        _log.warning("Downloading failed at attempt %s, retrying..." % attempt_cnt)

    # failed to download after multiple attempts
    return None


def find_base_dir():
    """
    Try to locate a possible new base directory
    - this is typically a single subdir, e.g. from untarring a tarball
    - when extracting multiple tarballs in the same directory,
      expect only the first one to give the correct path
    """
    def get_local_dirs_purged():
        ## e.g. always purge the log directory
        ignoreDirs = ["easybuild"]

        lst = os.listdir(os.getcwd())
        for ignDir in ignoreDirs:
            if ignDir in lst:
                lst.remove(ignDir)
        return lst

    lst = get_local_dirs_purged()
    new_dir = os.getcwd()
    while len(lst) == 1:
        new_dir = os.path.join(os.getcwd(), lst[0])
        if not os.path.isdir(new_dir):
            break

        try:
            os.chdir(new_dir)
        except OSError, err:
            _log.exception("Changing to dir %s from current dir %s failed: %s" % (new_dir, os.getcwd(), err))
        lst = get_local_dirs_purged()

    # make sure it's a directory, and not a (single) file that was in a tarball for example
    while not os.path.isdir(new_dir):
        new_dir = os.path.dirname(new_dir)

    _log.debug("Last dir list %s" % lst)
    _log.debug("Possible new dir %s found" % new_dir)
    return new_dir


def extract_cmd(fn, overwrite=False):
    """
    Determines the file type of file fn, returns extract cmd
    - based on file suffix
    - better to use Python magic?
    """
    ff = [x.lower() for x in fn.split('.')]
    ftype = None

    # gzipped or gzipped tarball
    if ff[-1] in ['gz']:
        ftype = 'gunzip %s'
        if ff[-2] in ['tar']:
            ftype = 'tar xzf %s'
    if ff[-1] in ['tgz', 'gtgz']:
        ftype = 'tar xzf %s'

    # bzipped or bzipped tarball
    if ff[-1] in ['bz2']:
        ftype = 'bunzip2 %s'
        if ff[-2] in ['tar']:
            ftype = 'tar xjf %s'
    if ff[-1] in ['tbz', 'tbz2', 'tb2']:
        ftype = 'tar xjf %s'

    # xzipped or xzipped tarball
    if ff[-1] in ['xz']:
        ftype = 'unxz %s'
        if ff[-2] in ['tar']:
            ftype = 'unxz %s --stdout | tar x'
    if ff[-1] in ['txz']:
        ftype = 'unxz %s --stdout | tar x'

    # tarball
    if ff[-1] in ['tar']:
        ftype = 'tar xf %s'

    # zip file
    if ff[-1] in ['zip']:
        if overwrite:
            ftype = 'unzip -qq -o %s'
        else:
            ftype = 'unzip -qq %s'

    if not ftype:
        _log.error('Unknown file type from file %s (%s)' % (fn, ff))

    return ftype % fn


def apply_patch(patchFile, dest, fn=None, copy=False, level=None):
    """
    Apply a patch to source code in directory dest
    - assume unified diff created with "diff -ru old new"
    """

    if not os.path.isfile(patchFile):
        _log.error("Can't find patch %s: no such file" % patchFile)
        return

    if fn and not os.path.isfile(fn):
        _log.error("Can't patch file %s: no such file" % fn)
        return

    if not os.path.isdir(dest):
        _log.error("Can't patch directory %s: no such directory" % dest)
        return

    ## copy missing files
    if copy:
        try:
            shutil.copy2(patchFile, dest)
            _log.debug("Copied patch %s to dir %s" % (patchFile, dest))
            return 'ok'
        except IOError, err:
            _log.error("Failed to copy %s to dir %s: %s" % (patchFile, dest, err))
            return

    ## use absolute paths
    apatch = os.path.abspath(patchFile)
    adest = os.path.abspath(dest)

    try:
        os.chdir(adest)
        _log.debug("Changing to directory %s" % adest)
    except OSError, err:
        _log.error("Can't change to directory %s: %s" % (adest, err))
        return

    if not level:
        # Guess p level
        # - based on +++ lines
        # - first +++ line that matches an existing file determines guessed level
        # - we will try to match that level from current directory
        patchreg = re.compile(r"^\s*\+\+\+\s+(?P<file>\S+)")
        try:
            f = open(apatch)
            txt = "ok"
            plusLines = []
            while txt:
                txt = f.readline()
                found = patchreg.search(txt)
                if found:
                    plusLines.append(found)
            f.close()
        except IOError, err:
            _log.error("Can't read patch %s: %s" % (apatch, err))
            return

        if not plusLines:
            _log.error("Can't guess patchlevel from patch %s: no testfile line found in patch" % apatch)
            return

        p = None
        for line in plusLines:
            ## locate file by stripping of /
            f = line.group('file')
            tf2 = f.split('/')
            n = len(tf2)
            plusFound = False
            i = None
            for i in range(n):
                if os.path.isfile('/'.join(tf2[i:])):
                    plusFound = True
                    break
            if plusFound:
                p = i
                break
            else:
                _log.debug('No match found for %s, trying next +++ line of patch file...' % f)

        if p == None: # p can also be zero, so don't use "not p"
            ## no match
            _log.error("Can't determine patch level for patch %s from directory %s" % (patchFile, adest))
        else:
            _log.debug("Guessed patch level %d for patch %s" % (p, patchFile))

    else:
        p = level
        _log.debug("Using specified patch level %d for patch %s" % (level, patchFile))

    patchCmd = "patch -b -p%d -i %s" % (p, apatch)
    result = run_cmd(patchCmd, simple=True)
    if not result:
        _log.error("Patching with patch %s failed" % patchFile)
        return

    return result

def adjust_cmd(func):
    """Make adjustments to given command, if required."""

    def inner(cmd, *args, **kwargs):
        # SuSE hack
        # - profile is not resourced, and functions (e.g. module) is not inherited
        if 'PROFILEREAD' in os.environ and (len(os.environ['PROFILEREAD']) > 0):
            filepaths = ['/etc/profile.d/modules.sh']
            extra = ''
            for fp in filepaths:
                if os.path.exists(fp):
                    extra = ". %s &&%s" % (fp, extra)
                else:
                    _log.warning("Can't find file %s" % fp)

            cmd = "%s %s" % (extra, cmd)

        return func(cmd, *args, **kwargs)

    return inner

@adjust_cmd
def run_cmd(cmd, log_ok=True, log_all=False, simple=False, inp=None, regexp=True, log_output=False, path=None):
    """
    Executes a command cmd
    - returns exitcode and stdout+stderr (mixed)
    - no input though stdin
    - if log_ok or log_all are set -> will log.error if non-zero exit-code
    - if simple is True -> instead of returning a tuple (output, ec) it will just return True or False signifying succes
    - inp is the input given to the command
    - regexp -> Regex used to check the output for errors. If True will use default (see parselogForError)
    - if log_output is True -> all output of command will be logged to a tempfile
    - path is the path run_cmd should chdir to before doing anything
    """
    try:
        if path:
            os.chdir(path)

        _log.debug("run_cmd: running cmd %s (in %s)" % (cmd, os.getcwd()))
    except:
        _log.info("running cmd %s in non-existing directory, might fail!" % cmd)

    ## Log command output
    if log_output:
        runLog = tempfile.NamedTemporaryFile(suffix='.log', prefix='easybuild-run_cmd-')
        _log.debug('run_cmd: Command output will be logged to %s' % runLog.name)
        runLog.write(cmd + "\n\n")
    else:
        runLog = None

    readSize = 1024 * 8

    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           stdin=subprocess.PIPE, close_fds=True, executable="/bin/bash")
    except OSError, err:
        _log.error("run_cmd init cmd %s failed:%s" % (cmd, err))
    if inp:
        p.stdin.write(inp)
    p.stdin.close()

    ec = p.poll()
    stdouterr = ''
    while ec < 0:
        # need to read from time to time.
        # - otherwise the stdout/stderr buffer gets filled and it all stops working
        output = p.stdout.read(readSize)
        if runLog:
            runLog.write(output)
        stdouterr += output
        ec = p.poll()

    # read remaining data (all of it)
    stdouterr += p.stdout.read()

    # not needed anymore. subprocess does this correct?
    # ec=os.WEXITSTATUS(ec)

    ## Command log output
    if log_output:
        runLog.close()

    return parse_cmd_output(cmd, stdouterr, ec, simple, log_all, log_ok, regexp)


@adjust_cmd
def run_cmd_qa(cmd, qa, no_qa=None, log_ok=True, log_all=False, simple=False, regexp=True, std_qa=None, path=None):
    """
    Executes a command cmd
    - looks for questions and tries to answer based on qa dictionary
    - returns exitcode and stdout+stderr (mixed)
    - no input though stdin
    - if log_ok or log_all are set -> will log.error if non-zero exit-code
    - if simple is True -> instead of returning a tuple (output, ec) it will just return True or False signifying succes
    - regexp -> Regex used to check the output for errors. If True will use default (see parselogForError)
    - if log_output is True -> all output of command will be logged to a tempfile
    - path is the path run_cmd should chdir to before doing anything
    """
    try:
        if path:
            os.chdir(path)

        _log.debug("run_cmd_qa: running cmd %s (in %s)" % (cmd, os.getcwd()))
    except:
        _log.info("running cmd %s in non-existing directory, might fail!" % cmd)

    # Part 1: process the QandA dictionary
    # given initial set of Q and A (in dict), return dict of reg. exp. and A
    #
    # make regular expression that matches the string with
    # - replace whitespace
    # - replace newline

    def escape_special(string):
        return re.sub(r"([\+\?\(\)\[\]\*\.\\\$])" , r"\\\1", string)

    split = '[\s\n]+'
    regSplit = re.compile(r"" + split)

    def process_QA(q, a):
        splitq = [escape_special(x) for x in regSplit.split(q)]
        regQtxt = split.join(splitq) + split.rstrip('+') + "*$"
        ## add optional split at the end
        if not a.endswith('\n'):
            a += '\n'
        regQ = re.compile(r"" + regQtxt)
        if regQ.search(q):
            return (a, regQ)
        else:
            _log.error("runqanda: Question %s converted in %s does not match itself" % (q, regQtxt))

    newQA = {}
    _log.debug("newQA: ")
    for question, answer in qa.items():
        (a, regQ) = process_QA(question, answer)
        newQA[regQ] = a
        _log.debug("newqa[%s]: %s" % (regQ.pattern, a))

    newstdQA = {}
    if std_qa:
        for question, answer in std_qa.items():
            regQ = re.compile(r"" + question + r"[\s\n]*$")
            if not answer.endswith('\n'):
                answer += '\n'
            newstdQA[regQ] = answer
            _log.debug("newstdQA[%s]: %s" % (regQ.pattern, answer))

    new_no_qa = []
    if no_qa:
        # simple statements, can contain wildcards
        new_no_qa = [re.compile(r"" + x + r"[\s\n]*$") for x in no_qa]

    _log.debug("New noQandA list is: %s" % [x.pattern for x in new_no_qa])

    # Part 2: Run the command and answer questions
    # - this needs asynchronous stdout

    ## Log command output
    if log_all:
        try:
            runLog = tempfile.NamedTemporaryFile(suffix='.log', prefix='easybuild-cmdqa-')
            _log.debug('run_cmd_qa: Command output will be logged to %s' % runLog.name)
            runLog.write(cmd + "\n\n")
        except IOError, err:
            _log.error("Opening log file for Q&A failed: %s" % err)
    else:
        runLog = None

    maxHitCount = 50

    try:
        p = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT, stdin=PIPE, close_fds=True, executable="/bin/bash")
    except OSError, err:
        _log.error("run_cmd_qa init cmd %s failed:%s" % (cmd, err))

    ec = p.poll()
    stdoutErr = ''
    oldLenOut = -1
    hitCount = 0

    while ec < 0:
        # need to read from time to time.
        # - otherwise the stdout/stderr buffer gets filled and it all stops working
        try:
            tmpOut = recv_some(p)
            if runLog:
                runLog.write(tmpOut)
            stdoutErr += tmpOut
        # recv_some may throw Exception
        except (IOError, Exception), err:
            _log.debug("run_cmd_qa cmd %s: read failed: %s" % (cmd, err))
            tmpOut = None

        hit = False
        for q, a in newQA.items():
            res = q.search(stdoutErr)
            if tmpOut and res:
                fa = a % res.groupdict()
                _log.debug("run_cmd_qa answer %s question %s out %s" % (fa, q.pattern, stdoutErr[-50:]))
                send_all(p, fa)
                hit = True
                break
        if not hit:
            for q, a in newstdQA.items():
                res = q.search(stdoutErr)
                if tmpOut and res:
                    fa = a % res.groupdict()
                    _log.debug("run_cmd_qa answer %s standard question %s out %s" % (fa, q.pattern, stdoutErr[-50:]))
                    send_all(p, fa)
                    hit = True
                    break
            if not hit:
                if len(stdoutErr) > oldLenOut:
                    oldLenOut = len(stdoutErr)
                else:
                    noqa = False
                    for r in new_no_qa:
                        if r.search(stdoutErr):
                            _log.debug("runqanda: noQandA found for out %s" % stdoutErr[-50:])
                            noqa = True
                    if not noqa:
                        hitCount += 1
            else:
                hitCount = 0
        else:
            hitCount = 0

        if hitCount > maxHitCount:
            # explicitly kill the child process before exiting
            try:
                os.killpg(p.pid, signal.SIGKILL)
                os.kill(p.pid, signal.SIGKILL)
            except OSError, err:
                _log.debug("run_cmd_qa exception caught when killing child process: %s" % err)
            _log.debug("run_cmd_qa: full stdouterr: %s" % stdoutErr)
            _log.error("run_cmd_qa: cmd %s : Max nohits %s reached: end of output %s" % (cmd,
                                                                                    maxHitCount,
                                                                                    stdoutErr[-500:]
                                                                                    ))

        # the sleep below is required to avoid exiting on unknown 'questions' too early (see above)
        time.sleep(1)
        ec = p.poll()

    # Process stopped. Read all remaining data
    try:
        if p.stdout:
            readTxt = p.stdout.read()
            stdoutErr += readTxt
            if runLog:
                runLog.write(readTxt)
    except IOError, err:
        _log.debug("runqanda cmd %s: remaining data read failed: %s" % (cmd, err))

    # Not needed anymore. Subprocess does this correct?
    # ec=os.WEXITSTATUS(ec)

    return parse_cmd_output(cmd, stdoutErr, ec, simple, log_all, log_ok, regexp)


def parse_cmd_output(cmd, stdouterr, ec, simple, log_all, log_ok, regexp):
    """
    will parse and perform error checks based on strictness setting
    """
    if strictness == IGNORE:
        check_ec = False
        use_regexp = False
    elif strictness == WARN:
        check_ec = True
        use_regexp = False
    elif strictness == ERROR:
        check_ec = True
        use_regexp = True
    else:
        _log.error("invalid strictness setting: %s" % strictness)

    # allow for overriding the regexp setting
    if not regexp:
        use_regexp = False

    if ec and (log_all or log_ok):
        # We don't want to error if the user doesn't care
        if check_ec:
            _log.error('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))
        else:
            _log.warn('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))

    if not ec:
        if log_all:
            _log.info('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))
        else:
            _log.debug('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))

    # parse the stdout/stderr for errors when strictness dictates this or when regexp is passed in
    if use_regexp or regexp:
        res = parse_log_for_error(stdouterr, regexp, msg="Command used: %s" % cmd)
        if len(res) > 0:
            message = "Found %s errors in command output (output: %s)" % (len(res), ", ".join([r[0] for r in res]))
            if use_regexp:
                _log.error(message)
            else:
                _log.warn(message)

    if simple:
        if ec:
            # If the user does not care -> will return true
            return not check_ec
        else:
            return True
    else:
        # Because we are not running in simple mode, we return the output and ec to the user
        return (stdouterr, ec)


def modify_env(old, new):
    """
    Compares 2 os.environ dumps. Adapts final environment.
    """
    _log.deprecated("moved modify_env to tools.environment", "2.0")
    return env.modify_env(old, new)


def convert_name(name, upper=False):
    """
    Converts name so it can be used as variable name
    """
    ## no regexps
    charmap = {
         '+':'plus',
         '-':'min'
        }
    for ch, new in charmap.items():
        name = name.replace(ch, new)

    if upper:
        return name.upper()
    else:
        return name


def parse_log_for_error(txt, regExp=None, stdout=True, msg=None):
    """
    txt is multiline string.
    - in memory
    regExp is a one-line regular expression
    - default
    """
    global errorsFoundInLog

    if regExp and type(regExp) == bool:
        regExp = r"(?<![(,-]|\w)(?:error|segmentation fault|failed)(?![(,-]|\.?\w)"
        _log.debug('Using default regular expression: %s' % regExp)
    elif type(regExp) == str:
        pass
    else:
        _log.error("parselogForError no valid regExp used: %s" % regExp)

    reg = re.compile(regExp, re.I)

    res = []
    for l in txt.split('\n'):
        r = reg.search(l)
        if r:
            res.append([l, r.groups()])
            errorsFoundInLog += 1

    if stdout and res:
        if msg:
            _log.info("parseLogError msg: %s" % msg)
        _log.info("parseLogError (some may be harmless) regExp %s found:\n%s" % (regExp,
                                                                              '\n'.join([x[0] for x in res])
                                                                              ))

    return res


def adjust_permissions(name, permissionBits, add=True, onlyfiles=False, onlydirs=False, recursive=True,
                       group_id=None, relative=True, ignore_errors=False):
    """
    Add or remove (if add is False) permissionBits from all files (if onlydirs is False)
    and directories (if onlyfiles is False) in path
    """

    name = os.path.abspath(name)

    if recursive:
        _log.info("Adjusting permissions recursively for %s" % name)
        allpaths = [name]
        for root, dirs, files in os.walk(name):
            paths = []
            if not onlydirs:
                paths += files
            if not onlyfiles:
                paths += dirs

            for path in paths:
                allpaths.append(os.path.join(root, path))

    else:
        _log.info("Adjusting permissions for %s" % name)
        allpaths = [name]

    failed_paths = []
    fail_cnt = 0
    for path in allpaths:

        try:
            if relative:

                # relative permissions (add or remove)
                perms = os.stat(path)[stat.ST_MODE]

                if add:
                    os.chmod(path, perms | permissionBits)
                else:
                    os.chmod(path, perms & ~permissionBits)

            else:
                # hard permissions bits (not relative)
                os.chmod(path, permissionBits)

            if group_id:
                # only change the group id if it the current gid is different from what we want
                cur_gid = os.stat(path).st_gid
                if not cur_gid == group_id:
                    _log.debug("Changing group id of %s to %s" % (path, group_id))
                    os.chown(path, -1, group_id)
                else:
                    _log.debug("Group id of %s is already OK (%s)" % (path, group_id))

        except OSError, err:
            if ignore_errors:
                # ignore errors while adjusting permissions (for example caused by bad links)
                _log.info("Failed to chmod/chown %s (but ignoring it): %s" % (path, err))
                fail_cnt += 1
            else:
                failed_paths.append(path)

    if failed_paths:
        _log.error("Failed to chmod/chown several paths: %s (last error: %s)" % (failed_paths, err))

    # we ignore some errors, but if there are to many, something is definitely wrong
    fail_ratio = fail_cnt / float(len(allpaths))
    max_fail_ratio = 0.5
    if fail_ratio > max_fail_ratio:
        _log.error("%.2f%% of permissions/owner operations failed (more than %.2f%%), something must be wrong..." % \
                  (100*fail_ratio, 100*max_fail_ratio))
    elif fail_cnt > 0:
        _log.debug("%.2f%% of permissions/owner operations failed, ignoring that..." % (100*fail_ratio))


def patch_perl_script_autoflush(path):
    # patch Perl script to enable autoflush,
    # so that e.g. run_cmd_qa receives all output to answer questions

    txt = read_file(path)
    origpath = "%s.eb.orig" % path
    write_file(origpath, txt)
    _log.debug("Patching Perl script %s for autoflush, original script copied to %s" % (path, origpath))

    # force autoflush for Perl print buffer
    lines = txt.split('\n')
    newtxt = '\n'.join([
        lines[0],  # shebang line
        "\nuse IO::Handle qw();",
        "STDOUT->autoflush(1);\n",  # extra newline to separate from actual script
    ] + lines[1:])

    write_file(path, newtxt)


def mkdir(directory, parents=False):
    """
    Create a directory
    Directory is the path to create
    
    When parents is True then no error if directory already exists
    and make parent directories as needed (cfr. mkdir -p)
    """
    if parents:
        try:
            os.makedirs(directory)
            _log.debug("Succesfully created directory %s and needed parents" % directory)
        except OSError, err:
            if err.errno == errno.EEXIST:
                _log.debug("Directory %s already exitst" % directory)
            else:
                _log.error("Failed to create directory %s: %s" % (directory, err))
    else:#not parrents
        try:
            os.mkdir(directory)
            _log.debug("Succesfully created directory %s" % directory)
        except OSError, err:
            if err.errno == errno.EEXIST:
                _log.warning("Directory %s already exitst" % directory)
            else:
                _log.error("Failed to create directory %s: %s" % (directory, err))

def rmtree2(path, n=3):
    """Wrapper around shutil.rmtree to make it more robust when used on NFS mounted file systems."""

    ok = False
    for i in range(0,n):
        try:
            shutil.rmtree(path)
            ok = True
            break
        except OSError, err:
            _log.debug("Failed to remove path %s with shutil.rmtree at attempt %d: %s" % (path, n, err))
            time.sleep(2)
    if not ok:
        _log.error("Failed to remove path %s with shutil.rmtree, even after %d attempts." % (path, n))
    else:
        _log.info("Path %s successfully removed." % path)

def copytree(src, dst, symlinks=False, ignore=None):
    """
    Copied from Lib/shutil.py in python 2.7, since we need this to work for python2.4 aswell
    and this code can be improved...
    
    Recursively copy a directory tree using copy2().

    The destination directory must not already exist.
    If exception(s) occur, an Error is raised with a list of reasons.

    If the optional symlinks flag is true, symbolic links in the
    source tree result in symbolic links in the destination tree; if
    it is false, the contents of the files pointed to by symbolic
    links are copied.

    The optional ignore argument is a callable. If given, it
    is called with the `src` parameter, which is the directory
    being visited by copytree(), and `names` which is the list of
    `src` contents, as returned by os.listdir():

        callable(src, names) -> ignored_names

    Since copytree() is called recursively, the callable will be
    called once for each directory that is copied. It returns a
    list of names relative to the `src` directory that should
    not be copied.

    XXX Consider this example code rather than the ultimate tool.

    """
    class Error(EnvironmentError):
        pass
    try:
        WindowsError #@UndefinedVariable
    except NameError:
        WindowsError = None

    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()
    _log.debug("copytree: skipping copy of %s" % ignored_names)
    os.makedirs(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks, ignore)
            else:
                # Will raise a SpecialFileError for unsupported file types
                shutil.copy2(srcname, dstname)
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error, err:
            errors.extend(err.args[0])
        except EnvironmentError, why:
            errors.append((srcname, dstname, str(why)))
    try:
        shutil.copystat(src, dst)
    except OSError, why:
        if WindowsError is not None and isinstance(why, WindowsError):
            # Copying file access times may fail on Windows
            pass
        else:
            errors.extend((src, dst, str(why)))
    if errors:
        raise Error, errors

def encode_string(name):
    """
    This encoding function handles funky software names ad infinitum, like:
      example: '0_foo+0x0x#-$__'
      becomes: '0_underscore_foo_plus_0x0x_hash__minus__dollar__underscore__underscore_'
    The intention is to have a robust escaping mechanism for names like c++, C# et al

    It has been inspired by the concepts seen at, but in lowercase style:
    * http://fossies.org/dox/netcdf-4.2.1.1/escapes_8c_source.html
    * http://celldesigner.org/help/CDH_Species_01.html
    * http://research.cs.berkeley.edu/project/sbp/darcsrepo-no-longer-updated/src/edu/berkeley/sbp/misc/ReflectiveWalker.java
    and can be extended freely as per ISO/IEC 10646:2012 / Unicode 6.1 names:
    * http://www.unicode.org/versions/Unicode6.1.0/ 
    For readability of >2 words, it is suggested to use _CamelCase_ style.
    So, yes, '_GreekSmallLetterEtaWithPsiliAndOxia_' *could* indeed be a fully
    valid software name; software "electron" in the original spelling anyone? ;-)

    """

    # do the character remapping, return same char by default
    result = ''.join(map(lambda x: STRING_ENCODING_CHARMAP.get(x, x), name))
    return result

def decode_string(name):
    """Decoding function to revert result of encode_string."""
    result = name
    for (char, escaped_char) in STRING_ENCODING_CHARMAP.items():
        result = re.sub(escaped_char, char, result)
    return result

def encode_class_name(name):
    """return encoded version of class name"""
    return EASYBLOCK_CLASS_PREFIX + encode_string(name)

def decode_class_name(name):
    """Return decoded version of class name."""
    if not name.startswith(EASYBLOCK_CLASS_PREFIX):
        # name is not encoded, apparently
        return name
    else:
        name = name[len(EASYBLOCK_CLASS_PREFIX):]
        return decode_string(name)
