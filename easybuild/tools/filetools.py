# #
# Copyright 2009-2014 Ghent University
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
Set of file tools.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import errno
import os
import re
import shutil
import stat
import time
import urllib
import zlib
from vsc import fancylogger
from vsc.utils.missing import all

import easybuild.tools.environment as env
from easybuild.tools.build_log import print_msg  # import build_log must stay, to activate use of EasyBuildLog
from easybuild.tools import run


_log = fancylogger.getLogger('filetools', fname=False)

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

try:
    # preferred over md5/sha modules, but only available in Python 2.5 and more recent
    import hashlib
    md5_class = hashlib.md5
    sha1_class = hashlib.sha1
except ImportError:
    import md5, sha
    md5_class = md5.md5
    sha1_class = sha.sha

# default checksum for source and patch files
DEFAULT_CHECKSUM = 'md5'

# map of checksum types to checksum functions
CHECKSUM_FUNCTIONS = {
    'md5': lambda p: calc_block_checksum(p, md5_class()),
    'sha1': lambda p: calc_block_checksum(p, sha1_class()),
    'adler32': lambda p: calc_block_checksum(p, ZlibChecksum(zlib.adler32)),
    'crc32': lambda p: calc_block_checksum(p, ZlibChecksum(zlib.crc32)),
    'size': lambda p: os.path.getsize(p),
}


class ZlibChecksum(object):
    """
    wrapper class for adler32 and crc32 checksums to
    match the interface of the hashlib module
    """
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.checksum = algorithm(r'')  # use the same starting point as the module
        self.blocksize = 64  # The same as md5/sha1

    def update(self, data):
        """Calculates a new checksum using the old one and the new data"""
        self.checksum = self.algorithm(data, self.checksum)

    def hexdigest(self):
        """Return hex string of the checksum"""
        return '0x%s' % (self.checksum & 0xffffffff)


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
        # try to create it
        try:
            os.makedirs(dest)
        except OSError, err:
            _log.exception("Can't extract file %s: directory %s can't be created: %err " % (fn, dest, err))

    # use absolute pathnames from now on
    absDest = os.path.abspath(dest)

    # change working directory
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


def det_common_path_prefix(paths):
    """Determine common path prefix for a given list of paths."""
    if not isinstance(paths, list):
        _log.error("det_common_path_prefix: argument must be of type list (got %s: %s)" % (type(paths), paths))
    elif not paths:
        return None

    # initial guess for common prefix
    prefix = paths[0]
    found_common = False
    while not found_common and prefix != os.path.dirname(prefix):
        prefix = os.path.dirname(prefix)
        found_common = all([p.startswith(prefix) for p in paths])

    if found_common:
        # prefix may be empty string for relative paths with a non-common prefix
        return prefix.rstrip(os.path.sep) or None
    else:
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


def find_easyconfigs(path, ignore_dirs=None):
    """
    Find .eb easyconfig files in path
    """
    if os.path.isfile(path):
        return [path]

    if ignore_dirs is None:
        ignore_dirs = []

    # walk through the start directory, retain all files that end in .eb
    files = []
    path = os.path.abspath(path)
    for dirpath, dirnames, filenames in os.walk(path, topdown=True):
        for f in filenames:
            if not f.endswith('.eb') or f == 'TEMPLATE.eb':
                continue

            spec = os.path.join(dirpath, f)
            _log.debug("Found easyconfig %s" % spec)
            files.append(spec)

        # ignore subdirs specified to be ignored by replacing items in dirnames list used by os.walk
        dirnames[:] = [d for d in dirnames if not d in ignore_dirs]

    return files


def search_file(paths, query, build_options=None, short=False):
    """
    Search for a particular file (only prints)
    """
    if build_options is None:
        build_options = {}

    ignore_dirs = build_options.get('ignore_dirs', ['.git', '.svn'])
    if not isinstance(ignore_dirs, list):
        _log.error("search_file: ignore_dirs (%s) should be of type list, not %s" % (ignore_dirs, type(ignore_dirs)))

    silent = build_options.get('silent', False)

    var_lines = []
    hit_lines = []
    var_index = 1
    var = None
    for path in paths:
        hits = []
        hit_in_path = False
        print_msg("Searching (case-insensitive) for '%s' in %s " % (query, path), log=_log, silent=silent)

        query = query.lower()
        for (dirpath, dirnames, filenames) in os.walk(path, topdown=True):
            for filename in filenames:
                filename = os.path.join(dirpath, filename)
                if filename.lower().find(query) != -1:
                    if not hit_in_path:
                        var = "CFGS%d" % var_index
                        var_index += 1
                        hit_in_path = True
                    hits.append(filename)

            # do not consider (certain) hidden directories
            # note: we still need to consider e.g., .local !
            # replace list elements using [:], so os.walk doesn't process deleted directories
            # see http://stackoverflow.com/questions/13454164/os-walk-without-hidden-folders
            dirnames[:] = [d for d in dirnames if not d in ignore_dirs]

        if hits:
            common_prefix = det_common_path_prefix(hits)
            if short and common_prefix is not None and len(common_prefix) > len(var) * 2:
                var_lines.append("%s=%s" % (var, common_prefix))
                hit_lines.extend([" * %s" % os.path.join('$%s' % var, fn[len(common_prefix) + 1:]) for fn in hits])
            else:
                hit_lines.extend([" * %s" % fn for fn in hits])

    for line in var_lines + hit_lines:
        print_msg(line, log=_log, silent=silent, prefix=False)


def compute_checksum(path, checksum_type=DEFAULT_CHECKSUM):
    """
    Compute checksum of specified file.

    @param path: Path of file to compute checksum for
    @param checksum_type: Type of checksum ('adler32', 'crc32', 'md5' (default), 'sha1', 'size')
    """
    if not checksum_type in CHECKSUM_FUNCTIONS:
        _log.error("Unknown checksum type (%s), supported types are: %s" % (checksum_type, CHECKSUM_FUNCTIONS.keys()))

    try:
        checksum = CHECKSUM_FUNCTIONS[checksum_type](path)
    except IOError, err:
        _log.error("Failed to read %s: %s" % (path, err))
    except MemoryError, err:
        _log.warning("A memory error occured when computing the checksum for %s: %s" % (path, err))
        checksum = 'dummy_checksum_due_to_memory_error'

    return checksum


def calc_block_checksum(path, algorithm):
    """Calculate a checksum of a file by reading it into blocks"""
    # We pick a blocksize of 16 MB: it's a multiple of the internal
    # blocksize of md5/sha1 (64) and gave the best speed results
    try:
        # in hashlib, blocksize is a class parameter
        blocksize = algorithm.blocksize * 262144  # 2^18
    except AttributeError, err:
        blocksize = 16777216  # 2^24
    _log.debug("Using blocksize %s for calculating the checksum" % blocksize)

    try:
        f = open(path, 'rb')
        for block in iter(lambda: f.read(blocksize), r''):
            algorithm.update(block)
        f.close()
    except IOError, err:
        _log.error("Failed to read %s: %s" % (path, err))

    return algorithm.hexdigest()


def verify_checksum(path, checksums):
    """
    Verify checksum of specified file.

    @param file: path of file to verify checksum of
    @param checksum: checksum value (and type, optionally, default is MD5), e.g., 'af314', ('sha', '5ec1b')
    """
    # if no checksum is provided, pretend checksum to be valid
    if checksums is None:
        return True

    # make sure we have a list of checksums
    if not isinstance(checksums, list):
        checksums = [checksums]

    for checksum in checksums:
        if isinstance(checksum, basestring):
            # default checksum type unless otherwise specified is MD5 (most common(?))
            typ = DEFAULT_CHECKSUM
        elif isinstance(checksum, tuple) and len(checksum) == 2:
            typ, checksum = checksum
        else:
            _log.error("Invalid checksum spec '%s', should be a string (MD5) or 2-tuple (type, value)." % checksum)

        actual_checksum = compute_checksum(path, typ)
        _log.debug("Computed %s checksum for %s: %s (correct checksum: %s)" % (typ, path, actual_checksum, checksum))

        if actual_checksum != checksum:
            return False

    # if we land here, all checksums have been verified to be correct
    return True


def find_base_dir():
    """
    Try to locate a possible new base directory
    - this is typically a single subdir, e.g. from untarring a tarball
    - when extracting multiple tarballs in the same directory,
      expect only the first one to give the correct path
    """
    def get_local_dirs_purged():
        # e.g. always purge the log directory
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

    # copy missing files
    if copy:
        try:
            shutil.copy2(patchFile, dest)
            _log.debug("Copied patch %s to dir %s" % (patchFile, dest))
            return 'ok'
        except IOError, err:
            _log.error("Failed to copy %s to dir %s: %s" % (patchFile, dest, err))
            return

    # use absolute paths
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
            # locate file by stripping of /
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

        if p is None:  # p can also be zero, so don't use "not p"
            # no match
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
    # no regexps
    charmap = {
        '+': 'plus',
        '-': 'min'
    }
    for ch, new in charmap.items():
        name = name.replace(ch, new)

    if upper:
        return name.upper()
    else:
        return name


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
        _log.error("%.2f%% of permissions/owner operations failed (more than %.2f%%), something must be wrong..." %
                  (100 * fail_ratio, 100 * max_fail_ratio))
    elif fail_cnt > 0:
        _log.debug("%.2f%% of permissions/owner operations failed, ignoring that..." % (100 * fail_ratio))


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
    else:  # not parents
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
    for i in range(0, n):
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


def cleanup(logfile, tempdir, testing):
    """Cleanup the specified log file and the tmp directory"""
    if not testing and logfile is not None:
        os.remove(logfile)
        print_msg('temporary log file %s has been removed.' % (logfile), log=None, silent=testing)

    if not testing and tempdir is not None:
        shutil.rmtree(tempdir, ignore_errors=True)
        print_msg('temporary directory %s has been removed.' % (tempdir), log=None, silent=testing)


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
        WindowsError  # @UndefinedVariable
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


def run_cmd(cmd, log_ok=True, log_all=False, simple=False, inp=None, regexp=True, log_output=False, path=None):
    """Legacy wrapper/placeholder for run.run_cmd"""
    return run.run_cmd(cmd, log_ok=log_ok, log_all=log_all, simple=simple,
                       inp=inp, regexp=regexp, log_output=log_output, path=path)


def run_cmd_qa(cmd, qa, no_qa=None, log_ok=True, log_all=False, simple=False, regexp=True, std_qa=None, path=None):
    """Legacy wrapper/placeholder for run.run_cmd_qa"""
    return run.run_cmd_qa(cmd, qa, no_qa=no_qa, log_ok=log_ok, log_all=log_all,
                          simple=simple, regexp=regexp, std_qa=std_qa, path=path)

def parse_log_for_error(txt, regExp=None, stdout=True, msg=None):
    """Legacy wrapper/placeholder for run.parse_log_for_error"""
    return run.parse_log_for_error(txt, regExp=regExp, stdout=stdout, msg=msg)
