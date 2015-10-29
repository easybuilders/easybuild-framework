# #
# Copyright 2009-2015 Ghent University
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
# #
"""
Tools to run commands.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import os
import re
import signal
import subprocess
import tempfile
import time

from vsc.utils import fancylogger

from easybuild.tools.asyncprocess import PIPE, STDOUT, Popen, recv_some, send_all
from easybuild.tools.config import build_option
from easybuild.tools.build_log import EasyBuildError, dry_run_msg


_log = fancylogger.getLogger('run', fname=False)


errors_found_in_log = 0

# constants for strictness levels
IGNORE = 'ignore'
WARN = 'warn'
ERROR = 'error'

# default strictness level
strictness = WARN

def run_cmd(cmd, log_ok=True, log_all=False, simple=False, inp=None, regexp=True, log_output=False, path=None,
            force_in_dry_run=False, verbose=True):
    """
    Run specified command (in a subshell)
    @param cmd: command to run
    @param log_ok: only run output/exit code for failing commands (exit code non-zero)
    @param log_all: always log command output and exit code
    @param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    @param inp: the input given to the command via stdin
    @param regex: regex used to check the output for errors;  if True it will use the default (see parse_log_for_error)
    @param log_output: indicate whether all output of command should be logged to a separate tempoary logfile
    @param path: path to execute the command in; current working directory is used if unspecified
    @param force_in_dry_run: force running the command during dry run
    @param verbose: include message on running the command in dry run output
    """
    cwd = os.getcwd()

    # early exit in 'dry run' mode, after printing the command that would be run (unless running the command is forced)
    if not force_in_dry_run and build_option('extended_dry_run'):
        if path is None:
            path = cwd
        if verbose:
            dry_run_msg("  running command \"%s\"" % cmd, silent=build_option('silent'))
            dry_run_msg("  (in %s)" % path, silent=build_option('silent'))

        # make sure we get the type of the return value right
        if simple:
            return True
        else:
            # output, exit code
            return ('', 0)

    try:
        if path:
            os.chdir(path)

        _log.debug("run_cmd: running cmd %s (in %s)" % (cmd, os.getcwd()))
    except OSError, err:
        _log.warning("Failed to change to %s: %s" % (path, err))
        _log.info("running cmd %s in non-existing directory, might fail!" % cmd)

    # # Log command output
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
        raise EasyBuildError("run_cmd init cmd %s failed:%s", cmd, err)
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

    # # Command log output
    if log_output:
        runLog.close()

    try:
        os.chdir(cwd)
    except OSError, err:
        raise EasyBuildError("Failed to return to %s after executing command: %s", cwd, err)

    return parse_cmd_output(cmd, stdouterr, ec, simple, log_all, log_ok, regexp)


def run_cmd_qa(cmd, qa, no_qa=None, log_ok=True, log_all=False, simple=False, regexp=True, std_qa=None, path=None, maxhits=50):
    """
    Run specified interactive command (in a subshell)
    @param cmd: command to run
    @param qa: dictionary which maps question to answers
    @param no_qa: list of patters that are not questions
    @param log_ok: only run output/exit code for failing commands (exit code non-zero)
    @param log_all: always log command output and exit code
    @param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    @param regex: regex used to check the output for errors; if True it will use the default (see parse_log_for_error)
    @param std_qa: dictionary which maps question regex patterns to answers
    @param path: path to execute the command is; current working directory is used if unspecified
    """
    cwd = os.getcwd()

    # early exit in 'dry run' mode, after printing the command that would be run
    if build_option('extended_dry_run'):
        if path is None:
            path = cwd
        dry_run_msg("  running interactive command \"%s\"" % cmd, silent=build_option('silent'))
        dry_run_msg("  (in %s)" % path, silent=build_option('silent'))
        if simple:
            return True
        else:
            # output, exit code
            return ('', 0)

    try:
        if path:
            os.chdir(path)

        _log.debug("run_cmd_qa: running cmd %s (in %s)" % (cmd, os.getcwd()))
    except OSError, err:
        _log.warning("Failed to change to %s: %s" % (path, err))
        _log.info("running cmd %s in non-existing directory, might fail!" % cmd)

    # Part 1: process the QandA dictionary
    # given initial set of Q and A (in dict), return dict of reg. exp. and A
    #
    # make regular expression that matches the string with
    # - replace whitespace
    # - replace newline

    def escape_special(string):
        return re.sub(r"([\+\?\(\)\[\]\*\.\\\$])", r"\\\1", string)

    split = '[\s\n]+'
    regSplit = re.compile(r"" + split)

    def process_QA(q, a_s):
        splitq = [escape_special(x) for x in regSplit.split(q)]
        regQtxt = split.join(splitq) + split.rstrip('+') + "*$"
        # add optional split at the end
        for i in [idx for idx, a in enumerate(a_s) if not a.endswith('\n')]:
            a_s[i] += '\n'
        regQ = re.compile(r"" + regQtxt)
        if regQ.search(q):
            return (a_s, regQ)
        else:
            raise EasyBuildError("runqanda: Question %s converted in %s does not match itself", q, regQtxt)

    def check_answers_list(answers):
        """Make sure we have a list of answers (as strings)."""
        if isinstance(answers, basestring):
            answers = [answers]
        elif not isinstance(answers, list):
            raise EasyBuildError("Invalid type for answer on %s, no string or list: %s (%s)",
                                 question, type(answers), answers)
        # list is manipulated when answering matching question, so return a copy
        return answers[:]

    newQA = {}
    _log.debug("newQA: ")
    for question, answers in qa.items():
        answers = check_answers_list(answers)
        (answers, regQ) = process_QA(question, answers)
        newQA[regQ] = answers
        _log.debug("newqa[%s]: %s" % (regQ.pattern, newQA[regQ]))

    newstdQA = {}
    if std_qa:
        for question, answers in std_qa.items():
            regQ = re.compile(r"" + question + r"[\s\n]*$")
            answers = check_answers_list(answers)
            for i in [idx for idx, a in enumerate(answers) if not a.endswith('\n')]:
                answers[i] += '\n'
            newstdQA[regQ] = answers
            _log.debug("newstdQA[%s]: %s" % (regQ.pattern, newstdQA[regQ]))

    new_no_qa = []
    if no_qa:
        # simple statements, can contain wildcards
        new_no_qa = [re.compile(r"" + x + r"[\s\n]*$") for x in no_qa]

    _log.debug("New noQandA list is: %s" % [x.pattern for x in new_no_qa])

    # Part 2: Run the command and answer questions
    # - this needs asynchronous stdout

    # # Log command output
    if log_all:
        try:
            runLog = tempfile.NamedTemporaryFile(suffix='.log', prefix='easybuild-cmdqa-')
            _log.debug('run_cmd_qa: Command output will be logged to %s' % runLog.name)
            runLog.write(cmd + "\n\n")
        except IOError, err:
            raise EasyBuildError("Opening log file for Q&A failed: %s", err)
    else:
        runLog = None

    try:
        p = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT, stdin=PIPE, close_fds=True, executable="/bin/bash")
    except OSError, err:
        raise EasyBuildError("run_cmd_qa init cmd %s failed:%s", cmd, err)

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
        for question, answers in newQA.items():
            res = question.search(stdoutErr)
            if tmpOut and res:
                fa = answers[0] % res.groupdict()
                # cycle through list of answers
                last_answer = answers.pop(0)
                answers.append(last_answer)
                _log.debug("List of answers for question %s after cycling: %s" % (question.pattern, answers))

                _log.debug("run_cmd_qa answer %s question %s out %s" % (fa, question.pattern, stdoutErr[-50:]))
                send_all(p, fa)
                hit = True
                break
        if not hit:
            for question, answers in newstdQA.items():
                res = question.search(stdoutErr)
                if tmpOut and res:
                    fa = answers[0] % res.groupdict()
                    # cycle through list of answers
                    last_answer = answers.pop(0)
                    answers.append(last_answer)
                    _log.debug("List of answers for question %s after cycling: %s" % (question.pattern, answers))

                    _log.debug("run_cmd_qa answer %s std question %s out %s" % (fa, question.pattern, stdoutErr[-50:]))
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

        if hitCount > maxhits:
            # explicitly kill the child process before exiting
            try:
                os.killpg(p.pid, signal.SIGKILL)
                os.kill(p.pid, signal.SIGKILL)
            except OSError, err:
                _log.debug("run_cmd_qa exception caught when killing child process: %s" % err)
            _log.debug("run_cmd_qa: full stdouterr: %s" % stdoutErr)
            raise EasyBuildError("run_cmd_qa: cmd %s : Max nohits %s reached: end of output %s",
                                 cmd, maxhits, stdoutErr[-500:])

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

    try:
        os.chdir(cwd)
    except OSError, err:
        raise EasyBuildError("Failed to return to %s after executing command: %s", cwd, err)

    return parse_cmd_output(cmd, stdoutErr, ec, simple, log_all, log_ok, regexp)


def parse_cmd_output(cmd, stdouterr, ec, simple, log_all, log_ok, regexp):
    """
    Parse command output and construct return value.
    @param cmd: executed command
    @param stdouterr: combined stdout/stderr of executed command
    @param ec: exit code of executed command
    @param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    @param log_all: always log command output and exit code
    @param log_ok: only run output/exit code for failing commands (exit code non-zero)
    @param regex: regex used to check the output for errors; if True it will use the default (see parse_log_for_error)
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
        raise EasyBuildError("invalid strictness setting: %s", strictness)

    # allow for overriding the regexp setting
    if not regexp:
        use_regexp = False

    _log.debug('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))

    if ec and (log_all or log_ok):
        # We don't want to error if the user doesn't care
        if check_ec:
            raise EasyBuildError('cmd "%s" exited with exitcode %s and output:\n%s', cmd, ec, stdouterr)
        else:
            _log.warn('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))
    elif not ec:
        if log_all:
            _log.info('cmd "%s" exited with exitcode %s and output:\n%s' % (cmd, ec, stdouterr))

    # parse the stdout/stderr for errors when strictness dictates this or when regexp is passed in
    if use_regexp or regexp:
        res = parse_log_for_error(stdouterr, regexp, msg="Command used: %s" % cmd)
        if len(res) > 0:
            message = "Found %s errors in command output (output: %s)" % (len(res), ", ".join([r[0] for r in res]))
            if use_regexp:
                raise EasyBuildError(message)
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


def parse_log_for_error(txt, regExp=None, stdout=True, msg=None):
    """
    txt is multiline string.
    - in memory
    regExp is a one-line regular expression
    - default
    """
    global errors_found_in_log

    if regExp and type(regExp) == bool:
        regExp = r"(?<![(,-]|\w)(?:error|segmentation fault|failed)(?![(,-]|\.?\w)"
        _log.debug('Using default regular expression: %s' % regExp)
    elif type(regExp) == str:
        pass
    else:
        raise EasyBuildError("parse_log_for_error no valid regExp used: %s", regExp)

    reg = re.compile(regExp, re.I)

    res = []
    for l in txt.split('\n'):
        r = reg.search(l)
        if r:
            res.append([l, r.groups()])
            errors_found_in_log += 1

    if stdout and res:
        if msg:
            _log.info("parse_log_for_error msg: %s" % msg)
        _log.info("parse_log_for_error (some may be harmless) regExp %s found:\n%s" %
                  (regExp, '\n'.join([x[0] for x in res])))

    return res


