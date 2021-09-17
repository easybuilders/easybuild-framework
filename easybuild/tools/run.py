# #
# Copyright 2009-2021 Ghent University
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
# #
"""
Tools to run commands.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
"""
import functools
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime

import easybuild.tools.asyncprocess as asyncprocess
from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, dry_run_msg, print_msg, time_str_since
from easybuild.tools.config import ERROR, IGNORE, WARN, build_option
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.utilities import trace_msg


_log = fancylogger.getLogger('run', fname=False)


errors_found_in_log = 0

# default strictness level
strictness = WARN


CACHED_COMMANDS = [
    "sysctl -n hw.cpufrequency_max",  # used in get_cpu_speed (OS X)
    "sysctl -n hw.memsize",  # used in get_total_memory (OS X)
    "sysctl -n hw.ncpu",  # used in get_avail_core_count (OS X)
    "sysctl -n machdep.cpu.brand_string",  # used in get_cpu_model (OS X)
    "sysctl -n machdep.cpu.vendor",  # used in get_cpu_vendor (OS X)
    "type module",  # used in ModulesTool.check_module_function
    "ulimit -u",  # used in det_parallelism
]


def run_cmd_cache(func):
    """Function decorator to cache (and retrieve cached) results of running commands."""
    cache = {}

    @functools.wraps(func)
    def cache_aware_func(cmd, *args, **kwargs):
        """Retrieve cached result of selected commands, or run specified and collect & cache result."""
        # cache key is combination of command and input provided via stdin
        key = (cmd, kwargs.get('inp', None))
        # fetch from cache if available, cache it if it's not, but only on cmd strings
        if isinstance(cmd, string_type) and key in cache:
            _log.debug("Using cached value for command '%s': %s", cmd, cache[key])
            return cache[key]
        else:
            res = func(cmd, *args, **kwargs)
            if cmd in CACHED_COMMANDS:
                cache[key] = res
            return res

    # expose clear/update methods of cache to wrapped function
    cache_aware_func.clear_cache = cache.clear
    cache_aware_func.update_cache = cache.update

    return cache_aware_func


def get_output_from_process(proc, read_size=None, asynchronous=False):
    """
    Get output from running process (that was opened with subprocess.Popen).

    :param proc: process to get output from
    :param read_size: number of bytes of output to read (if None: read all output)
    :param asynchronous: get output asynchronously
    """

    if asynchronous:
        # e=False is set to avoid raising an exception when command has completed;
        # that's needed to ensure we get all output,
        # see https://github.com/easybuilders/easybuild-framework/issues/3593
        output = asyncprocess.recv_some(proc, e=False)
    elif read_size:
        output = proc.stdout.read(read_size)
    else:
        output = proc.stdout.read()

    # need to be careful w.r.t. encoding since we want to obtain a string value,
    # and the output may include non UTF-8 characters
    # * in Python 2, .decode() returns a value of type 'unicode',
    #   but we really want a regular 'str' value (which is also why we use 'ignore' for encoding errors)
    # * in Python 3, .decode() returns a 'str' value when called on the 'bytes' value obtained from .read()
    output = str(output.decode('ascii', 'ignore'))

    return output


@run_cmd_cache
def run_cmd(cmd, log_ok=True, log_all=False, simple=False, inp=None, regexp=True, log_output=False, path=None,
            force_in_dry_run=False, verbose=True, shell=None, trace=True, stream_output=None, asynchronous=False):
    """
    Run specified command (in a subshell)
    :param cmd: command to run
    :param log_ok: only run output/exit code for failing commands (exit code non-zero)
    :param log_all: always log command output and exit code
    :param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    :param inp: the input given to the command via stdin
    :param regex: regex used to check the output for errors;  if True it will use the default (see parse_log_for_error)
    :param log_output: indicate whether all output of command should be logged to a separate temporary logfile
    :param path: path to execute the command in; current working directory is used if unspecified
    :param force_in_dry_run: force running the command during dry run
    :param verbose: include message on running the command in dry run output
    :param shell: allow commands to not run in a shell (especially useful for cmd lists), defaults to True
    :param trace: print command being executed as part of trace output
    :param stream_output: enable streaming command output to stdout
    :param asynchronous: run command asynchronously (returns subprocess.Popen instance if set to True)
    """
    cwd = os.getcwd()

    if isinstance(cmd, string_type):
        cmd_msg = cmd.strip()
    elif isinstance(cmd, list):
        cmd_msg = ' '.join(cmd)
    else:
        raise EasyBuildError("Unknown command type ('%s'): %s", type(cmd), cmd)

    if shell is None:
        shell = True
        if isinstance(cmd, list):
            raise EasyBuildError("When passing cmd as a list then `shell` must be set explictely! "
                                 "Note that all elements of the list but the first are treated as arguments "
                                 "to the shell and NOT to the command to be executed!")

    if log_output or (trace and build_option('trace')):
        # collect output of running command in temporary log file, if desired
        fd, cmd_log_fn = tempfile.mkstemp(suffix='.log', prefix='easybuild-run_cmd-')
        os.close(fd)
        try:
            cmd_log = open(cmd_log_fn, 'w')
        except IOError as err:
            raise EasyBuildError("Failed to open temporary log file for output of command: %s", err)
        _log.debug('run_cmd: Output of "%s" will be logged to %s' % (cmd, cmd_log_fn))
    else:
        cmd_log_fn, cmd_log = None, None

    # auto-enable streaming of command output under --logtostdout/-l, unless it was disabled explicitely
    if stream_output is None and build_option('logtostdout'):
        _log.info("Auto-enabling streaming output of '%s' command because logging to stdout is enabled", cmd_msg)
        stream_output = True

    if stream_output:
        print_msg("(streaming) output for command '%s':" % cmd_msg)

    start_time = datetime.now()
    if trace:
        trace_txt = "running command:\n"
        trace_txt += "\t[started at: %s]\n" % start_time.strftime('%Y-%m-%d %H:%M:%S')
        trace_txt += "\t[working dir: %s]\n" % (path or os.getcwd())
        if inp:
            trace_txt += "\t[input: %s]\n" % inp
        trace_txt += "\t[output logged in %s]\n" % cmd_log_fn
        trace_msg(trace_txt + '\t' + cmd_msg)

    # early exit in 'dry run' mode, after printing the command that would be run (unless running the command is forced)
    if not force_in_dry_run and build_option('extended_dry_run'):
        if path is None:
            path = cwd
        if verbose:
            dry_run_msg("  running command \"%s\"" % cmd_msg, silent=build_option('silent'))
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
    except OSError as err:
        _log.warning("Failed to change to %s: %s" % (path, err))
        _log.info("running cmd %s in non-existing directory, might fail!", cmd)

    if cmd_log:
        cmd_log.write("# output for command: %s\n\n" % cmd_msg)

    exec_cmd = "/bin/bash"

    if not shell:
        if isinstance(cmd, list):
            exec_cmd = None
            cmd.insert(0, '/usr/bin/env')
        elif isinstance(cmd, string_type):
            cmd = '/usr/bin/env %s' % cmd
        else:
            raise EasyBuildError("Don't know how to prefix with /usr/bin/env for commands of type %s", type(cmd))

    _log.info('running cmd: %s ' % cmd)
    try:
        proc = subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.PIPE, close_fds=True, executable=exec_cmd)
    except OSError as err:
        raise EasyBuildError("run_cmd init cmd %s failed:%s", cmd, err)

    if inp:
        proc.stdin.write(inp.encode())
    proc.stdin.close()

    if asynchronous:
        return (proc, cmd, cwd, start_time, cmd_log)
    else:
        return complete_cmd(proc, cmd, cwd, start_time, cmd_log, log_ok=log_ok, log_all=log_all, simple=simple,
                            regexp=regexp, stream_output=stream_output, trace=trace)


def complete_cmd(proc, cmd, owd, start_time, cmd_log, log_ok=True, log_all=False, simple=False,
                 regexp=True, stream_output=None, trace=True, output=''):
    """
    Complete running of command represented by passed subprocess.Popen instance.

    :param proc: subprocess.Popen instance representing running command
    :param cmd: command being run
    :param owd: original working directory
    :param start_time: start time of command (datetime instance)
    :param cmd_log: log file to print command output to
    :param log_ok: only run output/exit code for failing commands (exit code non-zero)
    :param log_all: always log command output and exit code
    :param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    :param regex: regex used to check the output for errors;  if True it will use the default (see parse_log_for_error)
    :param stream_output: enable streaming command output to stdout
    :param trace: print command being executed as part of trace output
    """
    # use small read size when streaming output, to make it stream more fluently
    # read size should not be too small though, to avoid too much overhead
    if stream_output:
        read_size = 128
    else:
        read_size = 1024 * 8

    stdouterr = output

    ec = proc.poll()
    while ec is None:
        # need to read from time to time.
        # - otherwise the stdout/stderr buffer gets filled and it all stops working
        output = get_output_from_process(proc, read_size=read_size)
        if cmd_log:
            cmd_log.write(output)
        if stream_output:
            sys.stdout.write(output)
        stdouterr += output
        ec = proc.poll()

    # read remaining data (all of it)
    output = get_output_from_process(proc)
    proc.stdout.close()
    if cmd_log:
        cmd_log.write(output)
        cmd_log.close()
    if stream_output:
        sys.stdout.write(output)
    stdouterr += output

    if trace:
        trace_msg("command completed: exit %s, ran in %s" % (ec, time_str_since(start_time)))

    try:
        os.chdir(owd)
    except OSError as err:
        raise EasyBuildError("Failed to return to %s after executing command: %s", owd, err)

    return parse_cmd_output(cmd, stdouterr, ec, simple, log_all, log_ok, regexp)


def run_cmd_qa(cmd, qa, no_qa=None, log_ok=True, log_all=False, simple=False, regexp=True, std_qa=None, path=None,
               maxhits=50, trace=True):
    """
    Run specified interactive command (in a subshell)
    :param cmd: command to run
    :param qa: dictionary which maps question to answers
    :param no_qa: list of patters that are not questions
    :param log_ok: only run output/exit code for failing commands (exit code non-zero)
    :param log_all: always log command output and exit code
    :param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    :param regex: regex used to check the output for errors; if True it will use the default (see parse_log_for_error)
    :param std_qa: dictionary which maps question regex patterns to answers
    :param path: path to execute the command is; current working directory is used if unspecified
    :param maxhits: maximum number of cycles (seconds) without being able to find a known question
    :param trace: print command being executed as part of trace output
    """
    cwd = os.getcwd()

    if not isinstance(cmd, string_type) and len(cmd) > 1:
        # We use shell=True and hence we should really pass the command as a string
        # When using a list then every element past the first is passed to the shell itself, not the command!
        raise EasyBuildError("The command passed must be a string!")

    if log_all or (trace and build_option('trace')):
        # collect output of running command in temporary log file, if desired
        fd, cmd_log_fn = tempfile.mkstemp(suffix='.log', prefix='easybuild-run_cmd_qa-')
        os.close(fd)
        try:
            cmd_log = open(cmd_log_fn, 'w')
        except IOError as err:
            raise EasyBuildError("Failed to open temporary log file for output of interactive command: %s", err)
        _log.debug('run_cmd_qa: Output of "%s" will be logged to %s' % (cmd, cmd_log_fn))
    else:
        cmd_log_fn, cmd_log = None, None

    start_time = datetime.now()
    if trace:
        trace_txt = "running interactive command:\n"
        trace_txt += "\t[started at: %s]\n" % start_time.strftime('%Y-%m-%d %H:%M:%S')
        trace_txt += "\t[working dir: %s]\n" % (path or os.getcwd())
        trace_txt += "\t[output logged in %s]\n" % cmd_log_fn
        trace_msg(trace_txt + '\t' + cmd.strip())

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
    except OSError as err:
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

    split = r'[\s\n]+'
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
        if isinstance(answers, string_type):
            answers = [answers]
        elif not isinstance(answers, list):
            raise EasyBuildError("Invalid type for answer on %s, no string or list: %s (%s)",
                                 question, type(answers), answers)
        # list is manipulated when answering matching question, so return a copy
        return answers[:]

    new_qa = {}
    _log.debug("new_qa: ")
    for question, answers in qa.items():
        answers = check_answers_list(answers)
        (answers, regQ) = process_QA(question, answers)
        new_qa[regQ] = answers
        _log.debug("new_qa[%s]: %s" % (regQ.pattern, new_qa[regQ]))

    new_std_qa = {}
    if std_qa:
        for question, answers in std_qa.items():
            regQ = re.compile(r"" + question + r"[\s\n]*$")
            answers = check_answers_list(answers)
            for i in [idx for idx, a in enumerate(answers) if not a.endswith('\n')]:
                answers[i] += '\n'
            new_std_qa[regQ] = answers
            _log.debug("new_std_qa[%s]: %s" % (regQ.pattern, new_std_qa[regQ]))

    new_no_qa = []
    if no_qa:
        # simple statements, can contain wildcards
        new_no_qa = [re.compile(r"" + x + r"[\s\n]*$") for x in no_qa]

    _log.debug("New noQandA list is: %s" % [x.pattern for x in new_no_qa])

    # Part 2: Run the command and answer questions
    # - this needs asynchronous stdout

    # # Log command output
    if cmd_log:
        cmd_log.write("# output for interactive command: %s\n\n" % cmd)

    try:
        proc = asyncprocess.Popen(cmd, shell=True, stdout=asyncprocess.PIPE, stderr=asyncprocess.STDOUT,
                                  stdin=asyncprocess.PIPE, close_fds=True, executable='/bin/bash')
    except OSError as err:
        raise EasyBuildError("run_cmd_qa init cmd %s failed:%s", cmd, err)

    ec = proc.poll()
    stdout_err = ''
    old_len_out = -1
    hit_count = 0

    while ec is None:
        # need to read from time to time.
        # - otherwise the stdout/stderr buffer gets filled and it all stops working
        try:
            out = get_output_from_process(proc, asynchronous=True)

            if cmd_log:
                cmd_log.write(out)
            stdout_err += out
        # recv_some used by get_output_from_process for getting asynchronous output may throw exception
        except (IOError, Exception) as err:
            _log.debug("run_cmd_qa cmd %s: read failed: %s", cmd, err)
            out = None

        hit = False
        for question, answers in new_qa.items():
            res = question.search(stdout_err)
            if out and res:
                fa = answers[0] % res.groupdict()
                # cycle through list of answers
                last_answer = answers.pop(0)
                answers.append(last_answer)
                _log.debug("List of answers for question %s after cycling: %s", question.pattern, answers)

                _log.debug("run_cmd_qa answer %s question %s out %s", fa, question.pattern, stdout_err[-50:])
                asyncprocess.send_all(proc, fa)
                hit = True
                break
        if not hit:
            for question, answers in new_std_qa.items():
                res = question.search(stdout_err)
                if out and res:
                    fa = answers[0] % res.groupdict()
                    # cycle through list of answers
                    last_answer = answers.pop(0)
                    answers.append(last_answer)
                    _log.debug("List of answers for question %s after cycling: %s", question.pattern, answers)

                    _log.debug("run_cmd_qa answer %s std question %s out %s", fa, question.pattern, stdout_err[-50:])
                    asyncprocess.send_all(proc, fa)
                    hit = True
                    break
            if not hit:
                if len(stdout_err) > old_len_out:
                    old_len_out = len(stdout_err)
                else:
                    noqa = False
                    for r in new_no_qa:
                        if r.search(stdout_err):
                            _log.debug("runqanda: noQandA found for out %s", stdout_err[-50:])
                            noqa = True
                    if not noqa:
                        hit_count += 1
            else:
                hit_count = 0
        else:
            hit_count = 0

        if hit_count > maxhits:
            # explicitly kill the child process before exiting
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                os.kill(proc.pid, signal.SIGKILL)
            except OSError as err:
                _log.debug("run_cmd_qa exception caught when killing child process: %s", err)
            _log.debug("run_cmd_qa: full stdouterr: %s", stdout_err)
            raise EasyBuildError("run_cmd_qa: cmd %s : Max nohits %s reached: end of output %s",
                                 cmd, maxhits, stdout_err[-500:])

        # the sleep below is required to avoid exiting on unknown 'questions' too early (see above)
        time.sleep(1)
        ec = proc.poll()

    # Process stopped. Read all remaining data
    try:
        if proc.stdout:
            out = get_output_from_process(proc)
            stdout_err += out
            if cmd_log:
                cmd_log.write(out)
                cmd_log.close()
    except IOError as err:
        _log.debug("runqanda cmd %s: remaining data read failed: %s", cmd, err)

    if trace:
        trace_msg("interactive command completed: exit %s, ran in %s" % (ec, time_str_since(start_time)))

    try:
        os.chdir(cwd)
    except OSError as err:
        raise EasyBuildError("Failed to return to %s after executing command: %s", cwd, err)

    return parse_cmd_output(cmd, stdout_err, ec, simple, log_all, log_ok, regexp)


def parse_cmd_output(cmd, stdouterr, ec, simple, log_all, log_ok, regexp):
    """
    Parse command output and construct return value.
    :param cmd: executed command
    :param stdouterr: combined stdout/stderr of executed command
    :param ec: exit code of executed command
    :param simple: if True, just return True/False to indicate success, else return a tuple: (output, exit_code)
    :param log_all: always log command output and exit code
    :param log_ok: only run output/exit code for failing commands (exit code non-zero)
    :param regex: regex used to check the output for errors; if True it will use the default (see parse_log_for_error)
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

    if ec and (log_all or log_ok):
        # We don't want to error if the user doesn't care
        if check_ec:
            raise EasyBuildError('cmd "%s" exited with exit code %s and output:\n%s', cmd, ec, stdouterr)
        else:
            _log.warning('cmd "%s" exited with exit code %s and output:\n%s' % (cmd, ec, stdouterr))
    elif not ec:
        if log_all:
            _log.info('cmd "%s" exited with exit code %s and output:\n%s' % (cmd, ec, stdouterr))
        else:
            _log.debug('cmd "%s" exited with exit code %s and output:\n%s' % (cmd, ec, stdouterr))

    # parse the stdout/stderr for errors when strictness dictates this or when regexp is passed in
    if use_regexp or regexp:
        res = parse_log_for_error(stdouterr, regexp, msg="Command used: %s" % cmd)
        if len(res) > 0:
            message = "Found %s errors in command output (output: %s)" % (len(res), "\n\t".join([r[0] for r in res]))
            if use_regexp:
                raise EasyBuildError(message)
            else:
                _log.warning(message)

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

    if regExp and isinstance(regExp, bool):
        regExp = r"(?<![(,-]|\w)(?:error|segmentation fault|failed)(?![(,-]|\.?\w)"
        _log.debug('Using default regular expression: %s' % regExp)
    elif isinstance(regExp, str):
        pass
    else:
        raise EasyBuildError("parse_log_for_error no valid regExp used: %s", regExp)

    reg = re.compile(regExp, re.I)

    res = []
    for line in txt.split('\n'):
        r = reg.search(line)
        if r:
            res.append([line, r.groups()])
            errors_found_in_log += 1

    if stdout and res:
        if msg:
            _log.info("parse_log_for_error msg: %s" % msg)
        _log.info("parse_log_for_error (some may be harmless) regExp %s found:\n%s" %
                  (regExp, '\n'.join([x[0] for x in res])))

    return res


def extract_errors_from_log(log_txt, reg_exps):
    """
    Check provided string (command output) for messages matching specified regular expressions,
    and return 2-tuple with list of warnings and errors.
    :param log_txt: String containing the log, will be split into individual lines
    :param reg_exps: List of: regular expressions (as strings) to error on,
                    or tuple of regular expression and action (any of [IGNORE, WARN, ERROR])
    :return (warnings, errors) as lists of lines containing a match
    """
    actions = (IGNORE, WARN, ERROR)

    # promote single string value to list, since code below expects a list
    if isinstance(reg_exps, string_type):
        reg_exps = [reg_exps]

    re_tuples = []
    for cur in reg_exps:
        try:
            if isinstance(cur, str):
                # use ERROR as default action if only regexp pattern is specified
                reg_exp, action = cur, ERROR
            elif isinstance(cur, tuple) and len(cur) == 2:
                reg_exp, action = cur
            else:
                raise TypeError("Incorrect type of value, expected string or 2-tuple")

            if not isinstance(reg_exp, str):
                raise TypeError("Regular expressions must be passed as string, got %s" % type(reg_exp))
            if action not in actions:
                raise TypeError("action must be one of %s, got %s" % (actions, action))

            re_tuples.append((re.compile(reg_exp), action))
        except Exception as err:
            raise EasyBuildError("Invalid input: No regexp or tuple of regexp and action '%s': %s", str(cur), err)

    warnings = []
    errors = []
    for line in log_txt.split('\n'):
        for reg_exp, action in re_tuples:
            if reg_exp.search(line):
                if action == ERROR:
                    errors.append(line)
                elif action == WARN:
                    warnings.append(line)
                break
    return warnings, errors


def check_log_for_errors(log_txt, reg_exps):
    """
    Check log_txt for messages matching regExps in order and do appropriate action
    :param log_txt: String containing the log, will be split into individual lines
    :param reg_exps: List of: regular expressions (as strings) to error on,
                    or tuple of regular expression and action (any of [IGNORE, WARN, ERROR])
    """
    global errors_found_in_log
    warnings, errors = extract_errors_from_log(log_txt, reg_exps)

    errors_found_in_log += len(warnings) + len(errors)
    if warnings:
        _log.warning("Found %s potential error(s) in command output (output: %s)",
                     len(warnings), "\n\t".join(warnings))
    if errors:
        raise EasyBuildError("Found %s error(s) in command output (output: %s)",
                             len(errors), "\n\t".join(errors))
