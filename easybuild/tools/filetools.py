# #
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
@author: Fotis Georgatos (Uni.Lu, NTUA)
@author: Sotiris Fragkiskos (NTUA, CERN)
"""
import fileinput
import glob
import hashlib
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib2
import zlib
from vsc.utils import fancylogger
from vsc.utils.missing import nub
from xml.etree import ElementTree

# import build_log must stay, to use of EasyBuildLog
from easybuild.tools.build_log import EasyBuildError, dry_run_msg, print_msg
from easybuild.tools.config import build_option
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


# default checksum for source and patch files
DEFAULT_CHECKSUM = 'md5'

# map of checksum types to checksum functions
CHECKSUM_FUNCTIONS = {
    'md5': lambda p: calc_block_checksum(p, hashlib.md5()),
    'sha1': lambda p: calc_block_checksum(p, hashlib.sha1()),
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
    txt = None
    try:
        with open(path, 'r') as handle:
            txt = handle.read()
    except IOError, err:
        if log_error:
            raise EasyBuildError("Failed to read %s: %s", path, err)

    return txt


def write_file(path, txt, append=False, forced=False):
    """Write given contents to file at given path (overwrites current file contents!)."""

    # early exit in 'dry run' mode
    if not forced and build_option('extended_dry_run'):
        dry_run_msg("file written: %s" % path, silent=build_option('silent'))
        return

    # note: we can't use try-except-finally, because Python 2.4 doesn't support it as a single block
    try:
        mkdir(os.path.dirname(path), parents=True)
        with open(path, 'a' if append else 'w') as handle:
            handle.write(txt)
    except IOError, err:
        raise EasyBuildError("Failed to write to %s: %s", path, err)


def remove_file(path):
    """Remove file at specified path."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError, err:
        raise EasyBuildError("Failed to remove %s: %s", path, err)


def extract_file(fn, dest, cmd=None, extra_options=None, overwrite=False):
    """
    Given filename fn, try to extract in directory dest
    - returns the directory name in case of success
    """
    if not os.path.isfile(fn) and not build_option('extended_dry_run'):
        raise EasyBuildError("Can't extract file %s: no such file", fn)

    mkdir(dest, parents=True)

    # use absolute pathnames from now on
    abs_dest = os.path.abspath(dest)

    # change working directory
    try:
        _log.debug("Unpacking %s in directory %s.", fn, abs_dest)
        os.chdir(abs_dest)
    except OSError, err:
        raise EasyBuildError("Can't change to directory %s: %s", abs_dest, err)

    if not cmd:
        cmd = extract_cmd(fn, overwrite=overwrite)
    else:
        # complete command template with filename
        cmd = cmd % fn
    if not cmd:
        raise EasyBuildError("Can't extract file %s with unknown filetype", fn)

    if extra_options:
        cmd = "%s %s" % (cmd, extra_options)

    run.run_cmd(cmd, simple=True)

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
        raise EasyBuildError("det_common_path_prefix: argument must be of type list (got %s: %s)", type(paths), paths)
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


def is_alt_pypi_url(url):
    """Determine whether specified URL is already an alternate PyPI URL, i.e. whether it contains a hash."""
    # example: .../packages/5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf/easybuild-2.7.0.tar.gz
    alt_url_regex = re.compile('/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/[^/]+$')
    res = bool(alt_url_regex.search(url))
    _log.debug("Checking whether '%s' is an alternate PyPI URL using pattern '%s'...: %s",
               url, alt_url_regex.pattern, res)
    return res


def derive_alt_pypi_url(url):
    """Derive alternate PyPI URL for given URL, using 'simple' PyPI API."""
    # see also https://www.python.org/dev/peps/pep-0503/
    alt_pypi_url = None

    # example input URL: https://pypi.python.org/packages/source/e/easybuild/easybuild-2.7.0.tar.gz
    pkg_name, pkg_source = url.strip().split('/')[-2:]

    # e.g. https://pypi.python.org/simple/easybuild
    # cfr. https://wiki.python.org/moin/PyPISimple
    simple_url = 'https://pypi.python.org/simple/%s' % re.sub(r'[-_.]+', '-', pkg_name.lower())

    tmpdir = tempfile.mkdtemp()
    links_html = os.path.join(tmpdir, '%s_links.html' % pkg_name)
    res = download_file(os.path.basename(links_html), simple_url, links_html)
    if res is None:
        _log.debug("Failed to download %s to determine alternate PyPI URL for %s", simple_url, pkg_source)
    else:
        parsed_html = ElementTree.parse(links_html)
        if hasattr(parsed_html, 'iter'):
            links = [a.attrib['href'] for a in parsed_html.iter('a')]
        else:
            links = [a.attrib['href'] for a in parsed_html.getiterator('a')]

        regex = re.compile('.*/packages/(?P<hash>[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60})/%s#md5.*' % pkg_source, re.M)
        for link in links:
            res = regex.match(link)
            if res:
                # e.g. .../5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf/easybuild-2.7.0.tar.gz
                alt_pypi_url = 'https://pypi.python.org/packages/%s/%s' % (res.group('hash'), pkg_source)
                break

        if not alt_pypi_url:
            _log.debug("Failed to extract hash using pattern '%s' from list of links: %s", regex.pattern, links)

    return alt_pypi_url


def download_file(filename, url, path, forced=False):
    """Download a file from the given URL, to the specified path."""

    _log.debug("Trying to download %s from %s to %s", filename, url, path)

    timeout = build_option('download_timeout')
    if timeout is None:
        # default to 10sec timeout if none was specified
        # default system timeout (used is nothing is specified) may be infinite (?)
        timeout = 10
    _log.debug("Using timeout of %s seconds for initiating download" % timeout)

    # make sure directory exists
    basedir = os.path.dirname(path)
    mkdir(basedir, parents=True)

    # try downloading, three times max.
    downloaded = False
    max_attempts = 3
    attempt_cnt = 0
    while not downloaded and attempt_cnt < max_attempts:
        try:
            # urllib2 does the right thing for http proxy setups, urllib does not!
            url_fd = urllib2.urlopen(url, timeout=timeout)
            _log.debug('response code for given url %s: %s' % (url, url_fd.getcode()))
            write_file(path, url_fd.read(), forced=forced)
            _log.info("Downloaded file %s from url %s to %s" % (filename, url, path))
            downloaded = True
            url_fd.close()
        except urllib2.HTTPError as err:
            if 400 <= err.code <= 499:
                _log.warning("URL %s was not found (HTTP response code %s), not trying again" % (url, err.code))
                break
            else:
                _log.warning("HTTPError occured while trying to download %s to %s: %s" % (url, path, err))
                attempt_cnt += 1
        except IOError as err:
            _log.warning("IOError occurred while trying to download %s to %s: %s" % (url, path, err))
            attempt_cnt += 1
        except Exception, err:
            raise EasyBuildError("Unexpected error occurred when trying to download %s to %s: %s", url, path, err)

        if not downloaded and attempt_cnt < max_attempts:
            _log.info("Attempt %d of downloading %s to %s failed, trying again..." % (attempt_cnt, url, path))

    if downloaded:
        _log.info("Successful download of file %s from url %s to path %s" % (filename, url, path))
        return path
    else:
        _log.warning("Download of %s to %s failed, done trying" % (url, path))
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
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]

    return files


def search_file(paths, query, short=False, ignore_dirs=None, silent=False, filename_only=False, terse=False):
    """
    Search for a particular file (only prints)
    """
    if ignore_dirs is None:
        ignore_dirs = ['.git', '.svn']
    if not isinstance(ignore_dirs, list):
        raise EasyBuildError("search_file: ignore_dirs (%s) should be of type list, not %s",
                             ignore_dirs, type(ignore_dirs))

    # compile regex, case-insensitive
    query = re.compile(query, re.I)

    var_lines = []
    hit_lines = []
    var_index = 1
    var = None
    for path in paths:
        hits = []
        hit_in_path = False
        if not terse:
            print_msg("Searching (case-insensitive) for '%s' in %s " % (query.pattern, path), log=_log, silent=silent)

        for (dirpath, dirnames, filenames) in os.walk(path, topdown=True):
            for filename in filenames:
                if query.search(filename):
                    if not hit_in_path:
                        var = "CFGS%d" % var_index
                        var_index += 1
                        hit_in_path = True
                    if filename_only:
                        hits.append(filename)
                    else:
                        hits.append(os.path.join(dirpath, filename))

            # do not consider (certain) hidden directories
            # note: we still need to consider e.g., .local !
            # replace list elements using [:], so os.walk doesn't process deleted directories
            # see http://stackoverflow.com/questions/13454164/os-walk-without-hidden-folders
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs]

        hits = sorted(hits)

        if hits and not terse:
            common_prefix = det_common_path_prefix(hits)
            if short and common_prefix is not None and len(common_prefix) > len(var) * 2:
                var_lines.append("%s=%s" % (var, common_prefix))
                hit_lines.extend([" * %s" % os.path.join('$%s' % var, fn[len(common_prefix) + 1:]) for fn in hits])
            else:
                hit_lines.extend([" * %s" % fn for fn in hits])

    if terse:
        for line in hits:
            print(line)
    else:
        for line in var_lines + hit_lines:
            print_msg(line, log=_log, silent=silent, prefix=False)


def compute_checksum(path, checksum_type=DEFAULT_CHECKSUM):
    """
    Compute checksum of specified file.

    @param path: Path of file to compute checksum for
    @param checksum_type: Type of checksum ('adler32', 'crc32', 'md5' (default), 'sha1', 'size')
    """
    if checksum_type not in CHECKSUM_FUNCTIONS:
        raise EasyBuildError("Unknown checksum type (%s), supported types are: %s",
                             checksum_type, CHECKSUM_FUNCTIONS.keys())

    try:
        checksum = CHECKSUM_FUNCTIONS[checksum_type](path)
    except IOError, err:
        raise EasyBuildError("Failed to read %s: %s", path, err)
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
        raise EasyBuildError("Failed to read %s: %s", path, err)

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
            raise EasyBuildError("Invalid checksum spec '%s', should be a string (MD5) or 2-tuple (type, value).",
                                 checksum)

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
        # and hidden directories
        ignoredirs = ["easybuild"]

        lst = os.listdir(os.getcwd())
        lst = [d for d in lst if not d.startswith('.') and d not in ignoredirs]
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
            raise EasyBuildError("Changing to dir %s from current dir %s failed: %s", new_dir, os.getcwd(), err)
        lst = get_local_dirs_purged()

    # make sure it's a directory, and not a (single) file that was in a tarball for example
    while not os.path.isdir(new_dir):
        new_dir = os.path.dirname(new_dir)

    _log.debug("Last dir list %s" % lst)
    _log.debug("Possible new dir %s found" % new_dir)
    return new_dir


def extract_cmd(filepath, overwrite=False):
    """
    Determines the file type of file at filepath, returns extract cmd based on file suffix
    """
    filename = os.path.basename(filepath)

    extract_cmds = {
        # gzipped or gzipped tarball
        '.gtgz':    "tar xzf %(filepath)s",
        '.gz':      "gunzip -c %(filepath)s > %(target)s",
        '.tar.gz':  "tar xzf %(filepath)s",
        '.tgz':     "tar xzf %(filepath)s",
        # bzipped or bzipped tarball
        '.bz2':     "bunzip2 %(filepath)s",
        '.tar.bz2': "tar xjf %(filepath)s",
        '.tb2':     "tar xjf %(filepath)s",
        '.tbz':     "tar xjf %(filepath)s",
        '.tbz2':    "tar xjf %(filepath)s",
        # xzipped or xzipped tarball
        '.tar.xz':  "unxz %(filepath)s --stdout | tar x",
        '.txz':     "unxz %(filepath)s --stdout | tar x",
        '.xz':      "unxz %(filepath)s",
        # tarball
        '.tar':     "tar xf %(filepath)s",
        # zip file
        '.zip':     "unzip -qq -o %(filepath)s" if overwrite else "unzip -qq %(filepath)s",
        # iso file
        '.iso':     "7z x %(filepath)s",
        # tar.Z: using compress (LZW)
        '.tar.z':   "tar xZf %(filepath)s",
    }

    suffixes = sorted(extract_cmds.keys(), key=len, reverse=True)
    pat = r'(?P<ext>%s)$' % '|'.join([ext.replace('.', '\\.') for ext in suffixes])
    res = re.search(pat, filename, flags=re.IGNORECASE)
    if res:
        ext = res.group('ext')
    else:
        raise EasyBuildError('Unknown file type for file %s', filename)

    target = filename.rstrip(ext)

    cmd_tmpl = extract_cmds[ext.lower()]

    return cmd_tmpl % {'filepath': filepath, 'target': target}


def det_patched_files(path=None, txt=None, omit_ab_prefix=False, github=False, filter_deleted=False):
    """
    Determine list of patched files from a patch.
    It searches for "+++ path/to/patched/file" lines to determine
    the patched files.
    @param path: the path to the diff
    @param txt: the contents of the diff (either path or txt should be give)
    @param omit_ab_prefix: ignore the a/ or b/ prefix of the files
    @param github: only consider lines that start with 'diff --git' to determine list of patched files
    @param filter_deleted: filter out all files that were deleted by the patch
    """
    if github:
        patched_regex = r"^diff --git (?P<ab_prefix>[ab]/)?(?P<file>\S+)"
    else:
        patched_regex = r"^\s*\+{3}\s+(?P<ab_prefix>[ab]/)?(?P<file>\S+)"
    patched_regex = re.compile(patched_regex, re.M)

    if path is not None:
        txt = read_file(path)
    elif txt is None:
        raise EasyBuildError("Either a file path or a string representing a patch should be supplied")

    patched_files = []
    for match in patched_regex.finditer(txt):
        patched_file = match.group('file')
        if not omit_ab_prefix and match.group('ab_prefix') is not None:
            patched_file = match.group('ab_prefix') + patched_file

        delete_regex = re.compile(r"%s\ndeleted file" % re.escape(os.path.basename(patched_file)), re.M)
        if patched_file in ['/dev/null']:
            _log.debug("Ignoring patched file %s", patched_file)

        elif filter_deleted and delete_regex.search(txt):
            _log.debug("Filtering out deleted file %s", patched_file)
        else:
            patched_files.append(patched_file)

    return patched_files


def guess_patch_level(patched_files, parent_dir):
    """Guess patch level based on list of patched files and specified directory."""
    patch_level = None
    for patched_file in patched_files:
        # locate file by stripping of directories
        tf2 = patched_file.split(os.path.sep)
        n_paths = len(tf2)
        path_found = False
        level = None
        for level in range(n_paths):
            if os.path.isfile(os.path.join(parent_dir, *tf2[level:])):
                path_found = True
                break
        if path_found:
            patch_level = level
            break
        else:
            _log.debug('No match found for %s, trying next patched file...' % patched_file)

    return patch_level


def apply_patch(patch_file, dest, fn=None, copy=False, level=None):
    """
    Apply a patch to source code in directory dest
    - assume unified diff created with "diff -ru old new"
    """

    if build_option('extended_dry_run'):
        # skip checking of files in dry run mode
        patch_filename = os.path.basename(patch_file)
        dry_run_msg("* applying patch file %s" % patch_filename, silent=build_option('silent'))

    elif not os.path.isfile(patch_file):
        raise EasyBuildError("Can't find patch %s: no such file", patch_file)

    elif fn and not os.path.isfile(fn):
        raise EasyBuildError("Can't patch file %s: no such file", fn)

    elif not os.path.isdir(dest):
        raise EasyBuildError("Can't patch directory %s: no such directory", dest)

    # copy missing files
    if copy:
        if build_option('extended_dry_run'):
            dry_run_msg("  %s copied to %s" % (patch_file, dest), silent=build_option('silent'))
        else:
            try:
                shutil.copy2(patch_file, dest)
                _log.debug("Copied patch %s to dir %s" % (patch_file, dest))
                # early exit, work is done after copying
                return True
            except IOError, err:
                raise EasyBuildError("Failed to copy %s to dir %s: %s", patch_file, dest, err)

    # use absolute paths
    apatch = os.path.abspath(patch_file)
    adest = os.path.abspath(dest)

    if level is None and build_option('extended_dry_run'):
        level = '<derived>'

    elif level is None:
        # guess value for -p (patch level)
        # - based on +++ lines
        # - first +++ line that matches an existing file determines guessed level
        # - we will try to match that level from current directory
        patched_files = det_patched_files(path=apatch)

        if not patched_files:
            raise EasyBuildError("Can't guess patchlevel from patch %s: no testfile line found in patch", apatch)
            return

        level = guess_patch_level(patched_files, adest)

        if level is None:  # level can also be 0 (zero), so don't use "not level"
            # no match
            raise EasyBuildError("Can't determine patch level for patch %s from directory %s", patch_file, adest)
        else:
            _log.debug("Guessed patch level %d for patch %s" % (level, patch_file))

    else:
        _log.debug("Using specified patch level %d for patch %s" % (level, patch_file))

    patch_cmd = "patch -b -p%s -i %s" % (level, apatch)
    result = run.run_cmd(patch_cmd, simple=True, path=adest)
    if not result:
        raise EasyBuildError("Patching with patch %s failed", patch_file)

    return result


def apply_regex_substitutions(path, regex_subs):
    """
    Apply specified list of regex substitutions.

    @param path: path to file to patch
    @param regex_subs: list of substitutions to apply, specified as (<regexp pattern>, <replacement string>)
    """
    # only report when in 'dry run' mode
    if build_option('extended_dry_run'):
        dry_run_msg("applying regex substitutions to file %s" % path, silent=build_option('silent'))
        for regex, subtxt in regex_subs:
            dry_run_msg("  * regex pattern '%s', replacement string '%s'" % (regex, subtxt))

    else:
        _log.debug("Applying following regex substitutions to %s: %s", path, regex_subs)

        for i, (regex, subtxt) in enumerate(regex_subs):
            regex_subs[i] = (re.compile(regex), subtxt)

        for line in fileinput.input(path, inplace=1, backup='.orig.eb'):
            for regex, subtxt in regex_subs:
                line = regex.sub(subtxt, line)
            sys.stdout.write(line)


def modify_env(old, new):
    """NO LONGER SUPPORTED: use modify_env from easybuild.tools.environment instead"""
    _log.nosupport("moved modify_env to easybuild.tools.environment", "2.0")


def convert_name(name, upper=False):
    """
    Converts name so it can be used as variable name
    """
    # no regexps
    charmap = {
        '+': 'plus',
        '-': 'min',
        '.': '',
    }
    for ch, new in charmap.items():
        name = name.replace(ch, new)

    if upper:
        return name.upper()
    else:
        return name


def adjust_permissions(name, permissionBits, add=True, onlyfiles=False, onlydirs=False, recursive=True,
                       group_id=None, relative=True, ignore_errors=False, skip_symlinks=True):
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
                if skip_symlinks:
                    for path in files:
                        if os.path.islink(os.path.join(root, path)):
                            _log.debug("Not adjusting permissions for symlink %s", path)
                        else:
                            paths.append(path)
                else:
                    paths.extend(files)
            if not onlyfiles:
                # os.walk skips symlinked dirs by default, i.e., no special handling needed here
                paths.extend(dirs)

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
        raise EasyBuildError("Failed to chmod/chown several paths: %s (last error: %s)", failed_paths, err)

    # we ignore some errors, but if there are to many, something is definitely wrong
    fail_ratio = fail_cnt / float(len(allpaths))
    max_fail_ratio = 0.5
    if fail_ratio > max_fail_ratio:
        raise EasyBuildError("%.2f%% of permissions/owner operations failed (more than %.2f%%), "
                             "something must be wrong...", 100 * fail_ratio, 100 * max_fail_ratio)
    elif fail_cnt > 0:
        _log.debug("%.2f%% of permissions/owner operations failed, ignoring that..." % (100 * fail_ratio))


def patch_perl_script_autoflush(path):
    # patch Perl script to enable autoflush,
    # so that e.g. run_cmd_qa receives all output to answer questions

    # only report when in 'dry run' mode
    if build_option('extended_dry_run'):
        dry_run_msg("Perl script patched: %s" % path, silent=build_option('silent'))

    else:
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


def mkdir(path, parents=False, set_gid=None, sticky=None):
    """
    Create a directory
    Directory is the path to create

    @param parents: create parent directories if needed (mkdir -p)
    @param set_gid: set group ID bit, to make subdirectories and files inherit group
    @param sticky: set the sticky bit on this directory (a.k.a. the restricted deletion flag),
                   to avoid users can removing/renaming files in this directory
    """
    if set_gid is None:
        set_gid = build_option('set_gid_bit')
    if sticky is None:
        sticky = build_option('sticky_bit')

    if not os.path.isabs(path):
        path = os.path.abspath(path)

    # exit early if path already exists
    if not os.path.exists(path):
        _log.info("Creating directory %s (parents: %s, set_gid: %s, sticky: %s)", path, parents, set_gid, sticky)
        # set_gid and sticky bits are only set on new directories, so we need to determine the existing parent path
        existing_parent_path = os.path.dirname(path)
        try:
            if parents:
                # climb up until we hit an existing path or the empty string (for relative paths)
                while existing_parent_path and not os.path.exists(existing_parent_path):
                    existing_parent_path = os.path.dirname(existing_parent_path)
                os.makedirs(path)
            else:
                os.mkdir(path)
        except OSError, err:
            raise EasyBuildError("Failed to create directory %s: %s", path, err)

        # set group ID and sticky bits, if desired
        bits = 0
        if set_gid:
            bits |= stat.S_ISGID
        if sticky:
            bits |= stat.S_ISVTX
        if bits:
            try:
                new_subdir = path[len(existing_parent_path):].lstrip(os.path.sep)
                new_path = os.path.join(existing_parent_path, new_subdir.split(os.path.sep)[0])
                adjust_permissions(new_path, bits, add=True, relative=True, recursive=True, onlydirs=True)
            except OSError, err:
                raise EasyBuildError("Failed to set groud ID/sticky bit: %s", err)
    else:
        _log.debug("Not creating existing path %s" % path)


def expand_glob_paths(glob_paths):
    """Expand specified glob paths to a list of unique non-glob paths to only files."""
    paths = []
    for glob_path in glob_paths:
        paths.extend([f for f in glob.glob(glob_path) if os.path.isfile(f)])

    return nub(paths)


def weld_paths(path1, path2):
    """Weld two paths together, taking into account overlap between tail of 1st path with head of 2nd path."""
    # strip path1 for use in comparisons
    path1s = path1.rstrip(os.path.sep)

    # init part2 head/tail/parts
    path2_head = path2.rstrip(os.path.sep)
    path2_tail = ''
    path2_parts = path2.split(os.path.sep)
    # if path2 is an absolute path, make sure it stays that way
    if path2_parts[0] == '':
        path2_parts[0] = os.path.sep

    while path2_parts and not path1s.endswith(path2_head):
        path2_tail = os.path.join(path2_parts.pop(), path2_tail)
        if path2_parts:
            # os.path.join requires non-empty list
            path2_head = os.path.join(*path2_parts)
        else:
            path2_head = None

    return os.path.join(path1, path2_tail)


def symlink(source_path, symlink_path):
    """Create a symlink at the specified path to the given path."""
    try:
        os.symlink(os.path.abspath(source_path), symlink_path)
        _log.info("Symlinked %s to %s", source_path, symlink_path)
    except OSError as err:
        raise EasyBuildError("Symlinking %s to %s failed: %s", source_path, symlink_path, err)


def path_matches(path, paths):
    """Check whether given path matches any of the provided paths."""
    if not os.path.exists(path):
        return False
    for somepath in paths:
        if os.path.exists(somepath) and os.path.samefile(path, somepath):
            return True
    return False


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

            # make sure write permissions are enabled on entire directory
            adjust_permissions(path, stat.S_IWUSR, add=True, recursive=True)
    if not ok:
        raise EasyBuildError("Failed to remove path %s with shutil.rmtree, even after %d attempts.", path, n)
    else:
        _log.info("Path %s successfully removed." % path)


def move_logs(src_logfile, target_logfile):
    """Move log file(s)."""
    mkdir(os.path.dirname(target_logfile), parents=True)
    src_logfile_len = len(src_logfile)
    try:

        # there may be multiple log files, due to log rotation
        app_logs = glob.glob('%s*' % src_logfile)
        for app_log in app_logs:
            # retain possible suffix
            new_log_path = target_logfile + app_log[src_logfile_len:]

            # retain old logs
            if os.path.exists(new_log_path):
                i = 0
                oldlog_backup = "%s_%d" % (new_log_path, i)
                while os.path.exists(oldlog_backup):
                    i += 1
                    oldlog_backup = "%s_%d" % (new_log_path, i)
                shutil.move(new_log_path, oldlog_backup)
                _log.info("Moved existing log file %s to %s" % (new_log_path, oldlog_backup))

            # move log to target path
            shutil.move(app_log, new_log_path)
            _log.info("Moved log file %s to %s" % (src_logfile, new_log_path))

    except (IOError, OSError), err:
        raise EasyBuildError("Failed to move log file(s) %s* to new log file %s*: %s",
                             src_logfile, target_logfile, err)


def cleanup(logfile, tempdir, testing, silent=False):
    """
    Cleanup the specified log file and the tmp directory, if desired.

    @param logfile: path to log file to clean up
    @param tempdir: path to temporary directory to clean up
    @param testing: are we in testing mode? if so, don't actually clean up anything
    @param silent: be silent (don't print anything to stdout)
    """

    if build_option('cleanup_tmpdir') and not testing:
        if logfile is not None:
            try:
                for log in [logfile] + glob.glob('%s.[0-9]*' % logfile):
                    os.remove(log)
            except OSError, err:
                raise EasyBuildError("Failed to remove log file(s) %s*: %s", logfile, err)
            print_msg("Temporary log file(s) %s* have been removed." % (logfile), log=None, silent=testing or silent)

        if tempdir is not None:
            try:
                shutil.rmtree(tempdir, ignore_errors=True)
            except OSError, err:
                raise EasyBuildError("Failed to remove temporary directory %s: %s", tempdir, err)
            print_msg("Temporary directory %s has been removed." % tempdir, log=None, silent=testing or silent)

    else:
        msg = "Keeping temporary log file(s) %s* and directory %s." % (logfile, tempdir)
        print_msg(msg, log=None, silent=testing or silent)


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
        raise Error(errors)


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
    """NO LONGER SUPPORTED: use run_cmd from easybuild.tools.run instead"""
    _log.nosupport("run_cmd was moved from easybuild.tools.filetools to easybuild.tools.run", '2.0')


def run_cmd_qa(cmd, qa, no_qa=None, log_ok=True, log_all=False, simple=False, regexp=True, std_qa=None, path=None):
    """NO LONGER SUPPORTED: use run_cmd_qa from easybuild.tools.run instead"""
    _log.nosupport("run_cmd_qa was moved from easybuild.tools.filetools to easybuild.tools.run", '2.0')


def parse_log_for_error(txt, regExp=None, stdout=True, msg=None):
    """NO LONGER SUPPORTED: use parse_log_for_error from easybuild.tools.run instead"""
    _log.nosupport("parse_log_for_error was moved from easybuild.tools.filetools to easybuild.tools.run", '2.0')


def det_size(path):
    """
    Determine total size of given filepath (in bytes).
    """
    installsize = 0
    try:

        # walk install dir to determine total size
        for (dirpath, _, filenames) in os.walk(path):
            for filename in filenames:
                fullpath = os.path.join(dirpath, filename)
                if os.path.exists(fullpath):
                    installsize += os.path.getsize(fullpath)
    except OSError, err:
        _log.warn("Could not determine install size: %s" % err)

    return installsize


def find_flexlm_license(custom_env_vars=None, lic_specs=None):
    """
    Find FlexLM license.

    Considered specified list of environment variables;
    checks for path to existing license file or valid license server specification.

    If no license is found through environment variables, also consider 'lic_specs'.

    @param custom_env_vars: list of environment variables to considered (if None, only consider $LM_LICENSE_FILE)
    @param lic_specs: list of license specifications
    @return: tuple with list of valid license specs found and name of first valid environment variable
    """
    valid_lic_specs = []
    lic_env_var = None

    # regex for license server spec; format: <port>@<server>
    server_port_regex = re.compile(r'^[0-9]+@\S+$')

    # always consider $LM_LICENSE_FILE
    lic_env_vars = ['LM_LICENSE_FILE']
    if isinstance(custom_env_vars, basestring):
        lic_env_vars.insert(0, custom_env_vars)
    elif custom_env_vars is not None:
        lic_env_vars = custom_env_vars + lic_env_vars

    # grab values for defined environment variables
    cand_lic_specs = {}
    for env_var in lic_env_vars:
        if env_var in os.environ:
            cand_lic_specs[env_var] = os.environ[env_var].split(os.pathsep)

    # also consider provided license spec (last)
    # use None as key to indicate that these license specs do not have an environment variable associated with them
    if lic_specs:
        cand_lic_specs[None] = lic_specs

    _log.debug("Candidate license specs: %s", cand_lic_specs)

    # check for valid license specs
    # order matters, so loop over original list of environment variables to consider
    valid_lic_specs = []
    for env_var in lic_env_vars + [None]:
        # obtain list of values to consider
        # take into account that some keys may be missing, and that individual values may be None
        values = [val for val in cand_lic_specs.get(env_var, None) or [] if val]
        _log.info("Considering %s to find FlexLM license specs: %s", env_var, values)

        for value in values:

            # license files to consider
            lic_files = None
            if os.path.isfile(value):
                lic_files = [value]
            elif os.path.isdir(value):
                # consider all *.dat and *.lic files in specified directory
                lic_files = sorted(glob.glob(os.path.join(value, '*.dat')) + glob.glob(os.path.join(value, '*.lic')))

            # valid license server spec
            elif server_port_regex.match(value):
                valid_lic_specs.append(value)

            # check whether license files are readable before retaining them
            if lic_files:
                for lic_file in lic_files:
                    try:
                        open(lic_file, 'r')
                        valid_lic_specs.append(lic_file)
                    except IOError as err:
                        _log.warning("License file %s found, but failed to open it for reading: %s", lic_file, err)

        # stop after finding valid license specs
        if valid_lic_specs:
            lic_env_var = env_var
            break

    if lic_env_var:
        via_msg = '$%s' % lic_env_var
    else:
        via_msg = "provided license spec"

    _log.info("Found valid license specs via %s: %s", via_msg, valid_lic_specs)

    return (valid_lic_specs, lic_env_var)
