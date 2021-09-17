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
Set of file tools.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Sotiris Fragkiskos (NTUA, CERN)
:author: Davide Vanzo (ACCRE, Vanderbilt University)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
:author: Maxime Boissonneault (Compute Canada)
"""
import datetime
import difflib
import glob
import hashlib
import imp
import inspect
import itertools
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import time
import zlib

from easybuild.base import fancylogger
from easybuild.tools import run
# import build_log must stay, to use of EasyBuildLog
from easybuild.tools.build_log import EasyBuildError, dry_run_msg, print_msg, print_warning
from easybuild.tools.config import DEFAULT_WAIT_ON_LOCK_INTERVAL, ERROR, GENERIC_EASYBLOCK_PKG, IGNORE, WARN
from easybuild.tools.config import build_option, install_path
from easybuild.tools.py2vs3 import HTMLParser, std_urllib, string_type
from easybuild.tools.utilities import natural_keys, nub, remove_unwanted_chars

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False

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

PATH_INDEX_FILENAME = '.eb-path-index'

CHECKSUM_TYPE_MD5 = 'md5'
CHECKSUM_TYPE_SHA256 = 'sha256'
DEFAULT_CHECKSUM = CHECKSUM_TYPE_MD5

# map of checksum types to checksum functions
CHECKSUM_FUNCTIONS = {
    'adler32': lambda p: calc_block_checksum(p, ZlibChecksum(zlib.adler32)),
    'crc32': lambda p: calc_block_checksum(p, ZlibChecksum(zlib.crc32)),
    CHECKSUM_TYPE_MD5: lambda p: calc_block_checksum(p, hashlib.md5()),
    'sha1': lambda p: calc_block_checksum(p, hashlib.sha1()),
    CHECKSUM_TYPE_SHA256: lambda p: calc_block_checksum(p, hashlib.sha256()),
    'sha512': lambda p: calc_block_checksum(p, hashlib.sha512()),
    'size': lambda p: os.path.getsize(p),
}
CHECKSUM_TYPES = sorted(CHECKSUM_FUNCTIONS.keys())

EXTRACT_CMDS = {
    # gzipped or gzipped tarball
    '.gtgz': "tar xzf %(filepath)s",
    '.gz': "gunzip -c %(filepath)s > %(target)s",
    '.tar.gz': "tar xzf %(filepath)s",
    '.tgz': "tar xzf %(filepath)s",
    # bzipped or bzipped tarball
    '.bz2': "bunzip2 -c %(filepath)s > %(target)s",
    '.tar.bz2': "tar xjf %(filepath)s",
    '.tb2': "tar xjf %(filepath)s",
    '.tbz': "tar xjf %(filepath)s",
    '.tbz2': "tar xjf %(filepath)s",
    # xzipped or xzipped tarball;
    # need to make sure that $TAPE is not set to avoid 'tar x' command failing,
    # see https://github.com/easybuilders/easybuild-framework/issues/3652
    '.tar.xz': "unset TAPE; unxz %(filepath)s --stdout | tar x",
    '.txz': "unset TAPE; unxz %(filepath)s --stdout | tar x",
    '.xz': "unxz %(filepath)s",
    # tarball
    '.tar': "tar xf %(filepath)s",
    # zip file
    '.zip': "unzip -qq %(filepath)s",
    # iso file
    '.iso': "7z x %(filepath)s",
    # tar.Z: using compress (LZW), but can be handled with gzip so use 'z'
    '.tar.z': "tar xzf %(filepath)s",
    # shell scripts don't need to be unpacked, just copy there
    '.sh': "cp -a %(filepath)s .",
}

# global set of names of locks that were created in this session
global_lock_names = set()


class ZlibChecksum(object):
    """
    wrapper class for adler32 and crc32 checksums to
    match the interface of the hashlib module
    """

    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.checksum = algorithm(b'')  # use the same starting point as the module
        self.blocksize = 64  # The same as md5/sha1

    def update(self, data):
        """Calculates a new checksum using the old one and the new data"""
        self.checksum = self.algorithm(data, self.checksum)

    def hexdigest(self):
        """Return hex string of the checksum"""
        return '0x%s' % (self.checksum & 0xffffffff)


def is_readable(path):
    """Return whether file at specified location exists and is readable."""
    try:
        return os.path.exists(path) and os.access(path, os.R_OK)
    except OSError as err:
        raise EasyBuildError("Failed to check whether %s is readable: %s", path, err)


def open_file(path, mode):
    """Open a (usually) text file. If mode is not binary, then utf-8 encoding will be used for Python 3.x"""
    # This is required for text files in Python 3, especially until Python 3.7 which implements PEP 540.
    # This PEP opens files in UTF-8 mode if the C locale is used, see https://www.python.org/dev/peps/pep-0540
    if sys.version_info[0] >= 3 and 'b' not in mode:
        return open(path, mode, encoding='utf-8')
    else:
        return open(path, mode)


def read_file(path, log_error=True, mode='r'):
    """Read contents of file at given path, in a robust way."""
    txt = None
    try:
        with open_file(path, mode) as handle:
            txt = handle.read()
    except IOError as err:
        if log_error:
            raise EasyBuildError("Failed to read %s: %s", path, err)

    return txt


def write_file(path, data, append=False, forced=False, backup=False, always_overwrite=True, verbose=False):
    """
    Write given contents to file at given path;
    overwrites current file contents without backup by default!

    :param path: location of file
    :param data: contents to write to file. Can be a file-like object of binary data
    :param append: append to existing file rather than overwrite
    :param forced: force actually writing file in (extended) dry run mode
    :param backup: back up existing file before overwriting or modifying it
    :param always_overwrite: don't require --force to overwrite an existing file
    :param verbose: be verbose, i.e. inform where backup file was created
    """
    # early exit in 'dry run' mode
    if not forced and build_option('extended_dry_run'):
        dry_run_msg("file written: %s" % path, silent=build_option('silent'))
        return

    if os.path.exists(path):
        if not append:
            if always_overwrite or build_option('force'):
                _log.info("Overwriting existing file %s", path)
            else:
                raise EasyBuildError("File exists, not overwriting it without --force: %s", path)

        if backup:
            backed_up_fp = back_up_file(path)
            _log.info("Existing file %s backed up to %s", path, backed_up_fp)
            if verbose:
                print_msg("Backup of %s created at %s" % (path, backed_up_fp), silent=build_option('silent'))

    # figure out mode to use for open file handle
    # cfr. https://docs.python.org/3/library/functions.html#open
    mode = 'a' if append else 'w'

    data_is_file_obj = hasattr(data, 'read')

    # special care must be taken with binary data in Python 3
    if sys.version_info[0] >= 3 and (isinstance(data, bytes) or data_is_file_obj):
        mode += 'b'

    # note: we can't use try-except-finally, because Python 2.4 doesn't support it as a single block
    try:
        mkdir(os.path.dirname(path), parents=True)
        with open_file(path, mode) as fh:
            if data_is_file_obj:
                # if a file-like object was provided, use copyfileobj (which reads the file in chunks)
                shutil.copyfileobj(data, fh)
            else:
                fh.write(data)
    except IOError as err:
        raise EasyBuildError("Failed to write to %s: %s", path, err)


def is_binary(contents):
    """
    Check whether given bytestring represents the contents of a binary file or not.
    """
    return isinstance(contents, bytes) and b'\00' in bytes(contents)


def resolve_path(path):
    """
    Return fully resolved path for given path.

    :param path: path that (maybe) contains symlinks
    """
    try:
        resolved_path = os.path.realpath(path)
    except (AttributeError, OSError, TypeError) as err:
        raise EasyBuildError("Resolving path %s failed: %s", path, err)

    return resolved_path


def symlink(source_path, symlink_path, use_abspath_source=True):
    """
    Create a symlink at the specified path to the given path.

    :param source_path: source file path
    :param symlink_path: symlink file path
    :param use_abspath_source: resolves the absolute path of source_path
    """
    if use_abspath_source:
        source_path = os.path.abspath(source_path)

    if os.path.exists(symlink_path):
        abs_source_path = os.path.abspath(source_path)
        symlink_target_path = os.path.abspath(os.readlink(symlink_path))
        if abs_source_path != symlink_target_path:
            raise EasyBuildError("Trying to symlink %s to %s, but the symlink already exists and points to %s.",
                                 source_path, symlink_path, symlink_target_path)
        _log.info("Skipping symlinking %s to %s, link already exists", source_path, symlink_path)
    else:
        try:
            os.symlink(source_path, symlink_path)
            _log.info("Symlinked %s to %s", source_path, symlink_path)
        except OSError as err:
            raise EasyBuildError("Symlinking %s to %s failed: %s", source_path, symlink_path, err)


def remove_file(path):
    """Remove file at specified path."""

    # early exit in 'dry run' mode
    if build_option('extended_dry_run'):
        dry_run_msg("file %s removed" % path, silent=build_option('silent'))
        return

    try:
        # note: file may also be a broken symlink...
        if os.path.exists(path) or os.path.islink(path):
            os.remove(path)
    except OSError as err:
        raise EasyBuildError("Failed to remove file %s: %s", path, err)


def remove_dir(path):
    """Remove directory at specified path."""
    # early exit in 'dry run' mode
    if build_option('extended_dry_run'):
        dry_run_msg("directory %s removed" % path, silent=build_option('silent'))
        return

    if os.path.exists(path):
        ok = False
        errors = []
        # Try multiple times to cater for temporary failures on e.g. NFS mounted paths
        max_attempts = 3
        for i in range(0, max_attempts):
            try:
                shutil.rmtree(path)
                ok = True
                break
            except OSError as err:
                _log.debug("Failed to remove path %s with shutil.rmtree at attempt %d: %s" % (path, i, err))
                errors.append(err)
                time.sleep(2)
                # make sure write permissions are enabled on entire directory
                adjust_permissions(path, stat.S_IWUSR, add=True, recursive=True)
        if ok:
            _log.info("Path %s successfully removed." % path)
        else:
            raise EasyBuildError("Failed to remove directory %s even after %d attempts.\nReasons: %s",
                                 path, max_attempts, errors)


def remove(paths):
    """
    Remove single file/directory or list of files and directories

    :param paths: path(s) to remove
    """
    if isinstance(paths, string_type):
        paths = [paths]

    _log.info("Removing %d files & directories", len(paths))

    for path in paths:
        if os.path.isfile(path):
            remove_file(path)
        elif os.path.isdir(path):
            remove_dir(path)
        else:
            raise EasyBuildError("Specified path to remove is not an existing file or directory: %s", path)


def change_dir(path):
    """
    Change to directory at specified location.

    :param path: location to change to
    :return: previous location we were in
    """
    # determining the current working directory can fail if we're in a non-existing directory
    try:
        cwd = os.getcwd()
    except OSError as err:
        _log.debug("Failed to determine current working directory (but proceeding anyway: %s", err)
        cwd = None

    try:
        os.chdir(path)
    except OSError as err:
        raise EasyBuildError("Failed to change from %s to %s: %s", cwd, path, err)

    return cwd


def extract_file(fn, dest, cmd=None, extra_options=None, overwrite=False, forced=False, change_into_dir=None):
    """
    Extract file at given path to specified directory
    :param fn: path to file to extract
    :param dest: location to extract to
    :param cmd: extract command to use (derived from filename if not specified)
    :param extra_options: extra options to pass to extract command
    :param overwrite: overwrite existing unpacked file
    :param forced: force extraction in (extended) dry run mode
    :param change_into_dir: change into resulting directory;
                          None (current default) implies True, but this is deprecated,
                          this named argument should be set to False or True explicitely
                          (in a future major release, default will be changed to False)
    :return: path to directory (in case of success)
    """
    if change_into_dir is None:
        _log.deprecated("extract_file function was called without specifying value for change_into_dir", '5.0')
        change_into_dir = True

    if not os.path.isfile(fn) and not build_option('extended_dry_run'):
        raise EasyBuildError("Can't extract file %s: no such file", fn)

    mkdir(dest, parents=True)

    # use absolute pathnames from now on
    abs_dest = os.path.abspath(dest)

    # change working directory
    _log.debug("Unpacking %s in directory %s", fn, abs_dest)
    cwd = change_dir(abs_dest)

    if not cmd:
        cmd = extract_cmd(fn, overwrite=overwrite)
    else:
        # complete command template with filename
        cmd = cmd % fn
    if not cmd:
        raise EasyBuildError("Can't extract file %s with unknown filetype", fn)

    if extra_options:
        cmd = "%s %s" % (cmd, extra_options)

    run.run_cmd(cmd, simple=True, force_in_dry_run=forced)

    # note: find_base_dir also changes into the base dir!
    base_dir = find_base_dir()

    # if changing into obtained directory is not desired,
    # change back to where we came from (unless that was a non-existing directory)
    if not change_into_dir:
        if cwd is None:
            raise EasyBuildError("Can't change back to non-existing directory after extracting %s in %s", fn, dest)
        else:
            change_dir(cwd)

    return base_dir


def which(cmd, retain_all=False, check_perms=True, log_ok=True, log_error=None, on_error=None):
    """
    Return (first) path in $PATH for specified command, or None if command is not found

    :param retain_all: returns *all* locations to the specified command in $PATH, not just the first one
    :param check_perms: check whether candidate path has read/exec permissions before accepting it as a match
    :param log_ok: Log an info message where the command has been found (if any)
    :param on_error: What to do if the command was not found, default: WARN. Possible values: IGNORE, WARN, ERROR
    """
    if log_error is not None:
        _log.deprecated("'log_error' named argument in which function has been replaced by 'on_error'", '5.0')
        # If set, make sure on_error is at least WARN
        if log_error and on_error == IGNORE:
            on_error = WARN
        elif not log_error and on_error is None:  # If set to False, use IGNORE unless on_error is also set
            on_error = IGNORE
    # Set default
    # TODO: After removal of log_error from the parameters, on_error=WARN can be used instead of this
    if on_error is None:
        on_error = WARN
    if on_error not in (IGNORE, WARN, ERROR):
        raise EasyBuildError("Invalid value for 'on_error': %s", on_error)

    if retain_all:
        res = []
    else:
        res = None

    paths = os.environ.get('PATH', '').split(os.pathsep)
    for path in paths:
        cmd_path = os.path.join(path, cmd)
        # only accept path if command is there
        if os.path.isfile(cmd_path):
            if log_ok:
                _log.info("Command %s found at %s", cmd, cmd_path)
            if check_perms:
                # check if read/executable permissions are available
                if not os.access(cmd_path, os.R_OK | os.X_OK):
                    _log.info("No read/exec permissions for %s, so continuing search...", cmd_path)
                    continue
            if retain_all:
                res.append(cmd_path)
            else:
                res = cmd_path
                break

    if not res and on_error != IGNORE:
        msg = "Could not find command '%s' (with permissions to read/execute it) in $PATH (%s)" % (cmd, paths)
        if on_error == WARN:
            _log.warning(msg)
        else:
            raise EasyBuildError(msg)
    return res


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
        found_common = all(p.startswith(prefix) for p in paths)

    if found_common:
        # prefix may be empty string for relative paths with a non-common prefix
        return prefix.rstrip(os.path.sep) or None
    else:
        return None


def normalize_path(path):
    """Normalize path removing empty and dot components.

    Similar to os.path.normpath but does not resolve '..' which may return a wrong path when symlinks are used
    """
    # In POSIX 3 or more leading slashes are equivalent to 1
    if path.startswith(os.path.sep):
        if path.startswith(os.path.sep * 2) and not path.startswith(os.path.sep * 3):
            start_slashes = os.path.sep * 2
        else:
            start_slashes = os.path.sep
    else:
        start_slashes = ''

    filtered_comps = (comp for comp in path.split(os.path.sep) if comp and comp != '.')
    return start_slashes + os.path.sep.join(filtered_comps)


def is_alt_pypi_url(url):
    """Determine whether specified URL is already an alternate PyPI URL, i.e. whether it contains a hash."""
    # example: .../packages/5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf/easybuild-2.7.0.tar.gz
    alt_url_regex = re.compile('/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/[^/]+$')
    res = bool(alt_url_regex.search(url))
    _log.debug("Checking whether '%s' is an alternate PyPI URL using pattern '%s'...: %s",
               url, alt_url_regex.pattern, res)
    return res


def pypi_source_urls(pkg_name):
    """
    Fetch list of source URLs (incl. source filename) for specified Python package from PyPI, using 'simple' PyPI API.
    """
    # example: https://pypi.python.org/simple/easybuild
    # see also:
    # - https://www.python.org/dev/peps/pep-0503/
    # - https://wiki.python.org/moin/PyPISimple
    simple_url = 'https://pypi.python.org/simple/%s' % re.sub(r'[-_.]+', '-', pkg_name.lower())

    tmpdir = tempfile.mkdtemp()
    urls_html = os.path.join(tmpdir, '%s_urls.html' % pkg_name)
    if download_file(os.path.basename(urls_html), simple_url, urls_html) is None:
        _log.debug("Failed to download %s to determine available PyPI URLs for %s", simple_url, pkg_name)
        res = []
    else:
        urls_txt = read_file(urls_html)

        res = []

        # note: don't use xml.etree.ElementTree to parse HTML page served by PyPI's simple API
        # cfr. https://github.com/pypa/warehouse/issues/7886
        class HrefHTMLParser(HTMLParser):
            """HTML parser to extract 'href' attribute values from anchor tags (<a href='...'>)."""

            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    attrs = dict(attrs)
                    if 'href' in attrs:
                        res.append(attrs['href'])

        parser = HrefHTMLParser()
        parser.feed(urls_txt)

    # links are relative, transform them into full URLs; for example:
    # from: ../../packages/<dir1>/<dir2>/<hash>/easybuild-<version>.tar.gz#md5=<md5>
    # to: https://pypi.python.org/packages/<dir1>/<dir2>/<hash>/easybuild-<version>.tar.gz#md5=<md5>
    res = [re.sub('.*/packages/', 'https://pypi.python.org/packages/', x) for x in res]

    return res


def derive_alt_pypi_url(url):
    """Derive alternate PyPI URL for given URL."""
    alt_pypi_url = None

    # example input URL: https://pypi.python.org/packages/source/e/easybuild/easybuild-2.7.0.tar.gz
    pkg_name, pkg_source = url.strip().split('/')[-2:]

    cand_urls = pypi_source_urls(pkg_name)

    # md5 for old PyPI, sha256 for new PyPi (Warehouse)
    regex = re.compile('.*/%s(?:#md5=[a-f0-9]{32}|#sha256=[a-f0-9]{64})$' % pkg_source.replace('.', '\\.'), re.M)
    for cand_url in cand_urls:
        res = regex.match(cand_url)
        if res:
            # e.g.: https://pypi.python.org/packages/<dir1>/<dir2>/<hash>/easybuild-<version>.tar.gz#md5=<md5>
            alt_pypi_url = res.group(0).split('#sha256')[0].split('#md5')[0]
            break

    if not alt_pypi_url:
        _log.debug("Failed to extract hash using pattern '%s' from list of URLs: %s", regex.pattern, cand_urls)

    return alt_pypi_url


def parse_http_header_fields_urlpat(arg, urlpat=None, header=None, urlpat_headers_collection=None, maxdepth=3):
    """
    Recurse into multi-line string "[URLPAT::][HEADER:]FILE|FIELD" where FILE may be another such string or file
    containing lines matching the same format, such as "^https://www.example.com::/path/to/headers.txt", and flatten
    the result to dict e.g. {'^https://www.example.com': ['Authorization: Basic token', 'User-Agent: Special Agent']}
    """
    if urlpat_headers_collection is None:
        # this function call is not a recursive call
        urlpat_headers = {}
    else:
        # copy existing header data to avoid modifying it
        urlpat_headers = urlpat_headers_collection.copy()

    # stop infinite recursion that might happen if a file.txt refers to itself
    if maxdepth < 0:
        raise EasyBuildError("Failed to parse_http_header_fields_urlpat (recursion limit)")

    if not isinstance(arg, str):
        raise EasyBuildError("Failed to parse_http_header_fields_urlpat (argument not a string)")

    # HTTP header fields are separated by CRLF but splitting on LF is more convenient
    for argline in arg.split('\n'):
        argline = argline.strip()  # remove optional whitespace (e.g. remaining CR)
        if argline == '' or '#' in argline[0]:
            continue  # permit comment lines: ignore them

        if os.path.isfile(os.path.join(os.getcwd(), argline)):
            # expand existing relative path to absolute
            argline = os.path.join(os.path.join(os.getcwd(), argline))
        if os.path.isfile(argline):
            # argline is a file path, so read that instead
            _log.debug('File included in parse_http_header_fields_urlpat: %s' % argline)
            argline = read_file(argline)
            urlpat_headers = parse_http_header_fields_urlpat(argline, urlpat, header, urlpat_headers, maxdepth - 1)
            continue

        # URL pattern is separated by '::' from a HTTP header field
        if '::' in argline:
            [urlpat, argline] = argline.split('::', 1)  # get the urlpat
            # the remainder may be another parseable argument, recurse with same depth
            urlpat_headers = parse_http_header_fields_urlpat(argline, urlpat, header, urlpat_headers, maxdepth)
            continue

        # Header field has format HEADER: FIELD, and FIELD may be another parseable argument
        # except if FIELD contains colons, then argline is the final HEADER: FIELD to be returned
        if ':' in argline and argline.count(':') == 1:
            [argheader, argline] = argline.split(':', 1)  # get the header and the remainder
            # the remainder may be another parseable argument, recurse with same depth
            # note that argheader would be forgotten in favor of the urlpat_headers returned by recursion,
            # so pass on the header for reconstruction just in case there was nothing to recurse in
            urlpat_headers = parse_http_header_fields_urlpat(argline, urlpat, argheader, urlpat_headers, maxdepth)
            continue

        if header is not None:
            # parent caller didn't want to forget about the header, reconstruct as recursion stops here.
            argline = header.strip() + ':' + argline

        if urlpat is not None:
            if urlpat in urlpat_headers.keys():
                urlpat_headers[urlpat].append(argline)  # add headers to the list
            else:
                urlpat_headers[urlpat] = list([argline])  # new list headers for this urlpat
        else:
            _log.warning("Non-empty argument to http-header-fields-urlpat ignored (missing URL pattern)")

    # return a dict full of {urlpat: [list, of, headers]}
    return urlpat_headers


def download_file(filename, url, path, forced=False):
    """Download a file from the given URL, to the specified path."""

    _log.debug("Trying to download %s from %s to %s", filename, url, path)

    timeout = build_option('download_timeout')
    if timeout is None:
        # default to 10sec timeout if none was specified
        # default system timeout (used is nothing is specified) may be infinite (?)
        timeout = 10
    _log.debug("Using timeout of %s seconds for initiating download" % timeout)

    # parse option HTTP header fields for URLs containing a pattern
    http_header_fields_urlpat = build_option('http_header_fields_urlpat')
    # compile a dict full of {urlpat: [header, list]}
    urlpat_headers = dict()
    if http_header_fields_urlpat is not None:
        # there may be multiple options given, parse them all, while updating urlpat_headers
        for arg in http_header_fields_urlpat:
            urlpat_headers.update(parse_http_header_fields_urlpat(arg))

    # make sure directory exists
    basedir = os.path.dirname(path)
    mkdir(basedir, parents=True)

    # try downloading, three times max.
    downloaded = False
    max_attempts = 3
    attempt_cnt = 0

    # use custom HTTP header
    headers = {'User-Agent': 'EasyBuild', 'Accept': '*/*'}

    # permit additional or override headers via http_headers_fields_urlpat option
    # only append/override HTTP header fields that match current url
    if urlpat_headers is not None:
        for urlpatkey, http_header_fields in urlpat_headers.items():
            if re.search(urlpatkey, url):
                extraheaders = dict(hf.split(':', 1) for hf in http_header_fields)
                for key, val in extraheaders.items():
                    headers[key] = val
                    _log.debug("Custom HTTP header field set: %s (value omitted from log)", key)

    # for backward compatibility, and to avoid relying on 3rd party Python library 'requests'
    url_req = std_urllib.Request(url, headers=headers)
    used_urllib = std_urllib
    switch_to_requests = False

    while not downloaded and attempt_cnt < max_attempts:
        attempt_cnt += 1
        try:
            if used_urllib is std_urllib:
                # urllib2 (Python 2) / urllib.request (Python 3) does the right thing for http proxy setups,
                # urllib does not!
                url_fd = std_urllib.urlopen(url_req, timeout=timeout)
                status_code = url_fd.getcode()
            else:
                response = requests.get(url, headers=headers, stream=True, timeout=timeout)
                status_code = response.status_code
                response.raise_for_status()
                url_fd = response.raw
                url_fd.decode_content = True
            _log.debug('response code for given url %s: %s' % (url, status_code))
            # note: we pass the file object to write_file rather than reading the file first,
            # to ensure the data is read in chunks (which prevents problems in Python 3.9+);
            # cfr. https://github.com/easybuilders/easybuild-framework/issues/3455
            # and https://bugs.python.org/issue42853
            write_file(path, url_fd, forced=forced, backup=True)
            _log.info("Downloaded file %s from url %s to %s" % (filename, url, path))
            downloaded = True
            url_fd.close()
        except used_urllib.HTTPError as err:
            if used_urllib is std_urllib:
                status_code = err.code
            if status_code == 403 and attempt_cnt == 1:
                switch_to_requests = True
            elif 400 <= status_code <= 499:
                _log.warning("URL %s was not found (HTTP response code %s), not trying again" % (url, status_code))
                break
            else:
                _log.warning("HTTPError occurred while trying to download %s to %s: %s" % (url, path, err))
        except IOError as err:
            _log.warning("IOError occurred while trying to download %s to %s: %s" % (url, path, err))
            error_re = re.compile(r"<urlopen error \[Errno 1\] _ssl.c:.*: error:.*:"
                                  "SSL routines:SSL23_GET_SERVER_HELLO:sslv3 alert handshake failure>")
            if error_re.match(str(err)):
                switch_to_requests = True
        except Exception as err:
            raise EasyBuildError("Unexpected error occurred when trying to download %s to %s: %s", url, path, err)

        if not downloaded and attempt_cnt < max_attempts:
            _log.info("Attempt %d of downloading %s to %s failed, trying again..." % (attempt_cnt, url, path))
            if used_urllib is std_urllib and switch_to_requests:
                if not HAVE_REQUESTS:
                    raise EasyBuildError("SSL issues with urllib2. If you are using RHEL/CentOS 6.x please "
                                         "install the python-requests and pyOpenSSL RPM packages and try again.")
                _log.info("Downloading using requests package instead of urllib2")
                used_urllib = requests

    if downloaded:
        _log.info("Successful download of file %s from url %s to path %s" % (filename, url, path))
        return path
    else:
        _log.warning("Download of %s to %s failed, done trying" % (url, path))
        return None


def create_index(path, ignore_dirs=None):
    """
    Create index for files in specified path.
    """
    if ignore_dirs is None:
        ignore_dirs = []

    index = set()

    if not os.path.exists(path):
        raise EasyBuildError("Specified path does not exist: %s", path)
    elif not os.path.isdir(path):
        raise EasyBuildError("Specified path is not a directory: %s", path)

    for (dirpath, dirnames, filenames) in os.walk(path, topdown=True, followlinks=True):
        for filename in filenames:
            # use relative paths in index
            rel_dirpath = os.path.relpath(dirpath, path)
            # avoid that relative paths start with './'
            if rel_dirpath == '.':
                rel_dirpath = ''
            index.add(os.path.join(rel_dirpath, filename))

        # do not consider (certain) hidden directories
        # note: we still need to consider e.g., .local !
        # replace list elements using [:], so os.walk doesn't process deleted directories
        # see https://stackoverflow.com/questions/13454164/os-walk-without-hidden-folders
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]

    return index


def dump_index(path, max_age_sec=None):
    """
    Create index for files in specified path, and dump it to file (alphabetically sorted).
    """
    if max_age_sec is None:
        max_age_sec = build_option('index_max_age')

    index_fp = os.path.join(path, PATH_INDEX_FILENAME)
    index_contents = create_index(path)

    curr_ts = datetime.datetime.now()
    if max_age_sec == 0:
        end_ts = datetime.datetime.max
    else:
        end_ts = curr_ts + datetime.timedelta(0, max_age_sec)

    lines = [
        "# created at: %s" % str(curr_ts),
        "# valid until: %s" % str(end_ts),
    ]
    lines.extend(sorted(index_contents))

    write_file(index_fp, '\n'.join(lines), always_overwrite=False)

    return index_fp


def load_index(path, ignore_dirs=None):
    """
    Load index for specified path, and return contents (or None if no index exists).
    """
    if ignore_dirs is None:
        ignore_dirs = []

    index_fp = os.path.join(path, PATH_INDEX_FILENAME)
    index = set()

    if build_option('ignore_index'):
        _log.info("Ignoring index for %s...", path)

    elif os.path.exists(index_fp):
        lines = read_file(index_fp).splitlines()

        valid_ts_regex = re.compile("^# valid until: (.*)", re.M)
        valid_ts = None

        for line in lines:

            # extract "valid until" timestamp, so we can check whether index is still valid
            if valid_ts is None:
                res = valid_ts_regex.match(line)
            else:
                res = None

            if res:
                valid_ts = res.group(1)
                try:
                    valid_ts = datetime.datetime.strptime(valid_ts, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError as err:
                    raise EasyBuildError("Failed to parse timestamp '%s' for index at %s: %s", valid_ts, path, err)

            elif line.startswith('#'):
                _log.info("Ignoring unknown header line '%s' in index for %s", line, path)

            else:
                # filter out files that are in an ignored directory
                path_dirs = line.split(os.path.sep)[:-1]
                if not any(d in path_dirs for d in ignore_dirs):
                    index.add(line)

        # check whether index is still valid
        if valid_ts:
            curr_ts = datetime.datetime.now()
            if curr_ts > valid_ts:
                print_warning("Index for %s is no longer valid (too old), so ignoring it...", path)
                index = None
            else:
                print_msg("found valid index for %s, so using it...", path)

    return index or None


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


def locate_files(files, paths, ignore_subdirs=None):
    """
    Determine full path for list of files, in given list of paths (directories).
    """
    # determine which files need to be found, if any
    files_to_find = []
    for idx, filepath in enumerate(files):
        if filepath == os.path.basename(filepath) and not os.path.exists(filepath):
            files_to_find.append((idx, filepath))
    _log.debug("List of files to find: %s", files_to_find)

    # find missing easyconfigs by walking paths in robot search path
    for path in paths:

        # skip non-existing paths
        if not os.path.exists(path):
            _log.debug("%s does not exist, skipping it...", path)
            continue

        _log.debug("Looking for missing files (%d left) in %s...", len(files_to_find), path)

        # try to load index for current path, or create one
        path_index = load_index(path, ignore_dirs=ignore_subdirs)
        if path_index is None or build_option('ignore_index'):
            _log.info("No index found for %s, creating one (in memory)...", path)
            path_index = create_index(path, ignore_dirs=ignore_subdirs)
        else:
            _log.info("Index found for %s, so using it...", path)

        for filepath in path_index:
            for idx, file_to_find in files_to_find[:]:
                if os.path.basename(filepath) == file_to_find:
                    full_path = os.path.join(path, filepath)
                    _log.info("Found %s in %s: %s", file_to_find, path, full_path)
                    files[idx] = full_path
                    # if file was found, stop looking for it (first hit wins)
                    files_to_find.remove((idx, file_to_find))

            # stop as soon as we have all we need (path index loop)
            if not files_to_find:
                break

        # stop as soon as we have all we need (paths loop)
        if not files_to_find:
            break

    if files_to_find:
        filenames = ', '.join([f for (_, f) in files_to_find])
        paths = ', '.join(paths)
        raise EasyBuildError("One or more files not found: %s (search paths: %s)", filenames, paths)

    return [os.path.abspath(f) for f in files]


def find_glob_pattern(glob_pattern, fail_on_no_match=True):
    """Find unique file/dir matching glob_pattern (raises error if more than one match is found)"""
    if build_option('extended_dry_run'):
        return glob_pattern
    res = glob.glob(glob_pattern)
    if len(res) == 0 and not fail_on_no_match:
        return None
    if len(res) != 1:
        raise EasyBuildError("Was expecting exactly one match for '%s', found %d: %s", glob_pattern, len(res), res)
    return res[0]


def search_file(paths, query, short=False, ignore_dirs=None, silent=False, filename_only=False, terse=False,
                case_sensitive=False):
    """
    Search for files using in specified paths using specified search query (regular expression)

    :param paths: list of paths to search in
    :param query: search query to use (regular expression); will be used case-insensitive
    :param short: figure out common prefix of hits, use variable to factor it out
    :param ignore_dirs: list of directories to ignore (default: ['.git', '.svn'])
    :param silent: whether or not to remain silent (don't print anything)
    :param filename_only: only return filenames, not file paths
    :param terse: stick to terse (machine-readable) output, as opposed to pretty-printing
    """
    if ignore_dirs is None:
        ignore_dirs = ['.git', '.svn']
    if not isinstance(ignore_dirs, list):
        raise EasyBuildError("search_file: ignore_dirs (%s) should be of type list, not %s",
                             ignore_dirs, type(ignore_dirs))

    # escape some special characters in query that may also occur in actual software names: +
    # do not use re.escape, since that breaks queries with genuine regex characters like ^ or .*
    query = re.sub('([+])', r'\\\1', query)

    # compile regex, case-insensitive
    try:
        if case_sensitive:
            query = re.compile(query)
        else:
            # compile regex, case-insensitive
            query = re.compile(query, re.I)
    except re.error as err:
        raise EasyBuildError("Invalid search query: %s", err)

    var_defs = []
    hits = []
    var_index = 1
    var = None
    for path in paths:
        path_hits = []
        if not terse:
            print_msg("Searching (case-insensitive) for '%s' in %s " % (query.pattern, path), log=_log, silent=silent)

        if build_option('ignore_index'):
            path_index = None
        else:
            path_index = load_index(path, ignore_dirs=ignore_dirs)
        if path_index is None:
            if os.path.exists(path):
                _log.info("No index found for %s, creating one...", path)
                path_index = create_index(path, ignore_dirs=ignore_dirs)
            else:
                path_index = []
        else:
            _log.info("Index found for %s, so using it...", path)

        for filepath in path_index:
            filename = os.path.basename(filepath)
            if query.search(filename):
                if not path_hits:
                    var = "CFGS%d" % var_index
                    var_index += 1
                if filename_only:
                    path_hits.append(filename)
                else:
                    path_hits.append(os.path.join(path, filepath))

        path_hits = sorted(path_hits, key=natural_keys)

        if path_hits:
            if not terse and short:
                common_prefix = det_common_path_prefix(path_hits)
                if common_prefix is not None and len(common_prefix) > len(var) * 2:
                    var_defs.append((var, common_prefix))
                    var_spec = '$' + var
                    # Replace the common prefix by var_spec
                    path_hits = (var_spec + fn[len(common_prefix):] for fn in path_hits)
            hits.extend(path_hits)

    return var_defs, hits


def dir_contains_files(path, recursive=True):
    """
    Return True if the given directory does contain any file

    :recursive If False only the path itself is considered, else all subdirectories are also searched
    """
    if recursive:
        return any(files for _root, _dirs, files in os.walk(path))
    else:
        return any(os.path.isfile(os.path.join(path, x)) for x in os.listdir(path))


def find_eb_script(script_name):
    """Find EasyBuild script with given name (in easybuild/scripts subdirectory)."""
    filetools, eb_dir = __file__, None
    if os.path.isabs(filetools):
        eb_dir = os.path.dirname(os.path.dirname(filetools))
    else:
        # go hunting for absolute path to filetools module via sys.path;
        # we can't rely on os.path.abspath or os.path.realpath, since they leverage os.getcwd()...
        for path in sys.path:
            path = os.path.abspath(path)
            if os.path.exists(os.path.join(path, filetools)):
                eb_dir = os.path.dirname(os.path.dirname(os.path.join(path, filetools)))
                break

    if eb_dir is None:
        raise EasyBuildError("Failed to find parent directory for 'easybuild/scripts' subdirectory")

    script_loc = os.path.join(eb_dir, 'scripts', script_name)
    if not os.path.exists(script_loc):
        prev_script_loc = script_loc

        # fallback mechanism: check in location relative to location of 'eb'
        eb_path = os.getenv('EB_SCRIPT_PATH') or which('eb')
        if eb_path is None:
            _log.warning("'eb' not found in $PATH, failed to determine installation prefix")
        else:
            install_prefix = os.path.dirname(os.path.dirname(resolve_path(eb_path)))
            script_loc = os.path.join(install_prefix, 'easybuild', 'scripts', script_name)

        if not os.path.exists(script_loc):
            raise EasyBuildError("Script '%s' not found at expected location: %s or %s",
                                 script_name, prev_script_loc, script_loc)

    return script_loc


def compute_checksum(path, checksum_type=DEFAULT_CHECKSUM):
    """
    Compute checksum of specified file.

    :param path: Path of file to compute checksum for
    :param checksum_type: type(s) of checksum ('adler32', 'crc32', 'md5' (default), 'sha1', 'sha256', 'sha512', 'size')
    """
    if checksum_type not in CHECKSUM_FUNCTIONS:
        raise EasyBuildError("Unknown checksum type (%s), supported types are: %s",
                             checksum_type, CHECKSUM_FUNCTIONS.keys())

    try:
        checksum = CHECKSUM_FUNCTIONS[checksum_type](path)
    except IOError as err:
        raise EasyBuildError("Failed to read %s: %s", path, err)
    except MemoryError as err:
        _log.warning("A memory error occurred when computing the checksum for %s: %s" % (path, err))
        checksum = 'dummy_checksum_due_to_memory_error'

    return checksum


def calc_block_checksum(path, algorithm):
    """Calculate a checksum of a file by reading it into blocks"""
    # We pick a blocksize of 16 MB: it's a multiple of the internal
    # blocksize of md5/sha1 (64) and gave the best speed results
    try:
        # in hashlib, blocksize is a class parameter
        blocksize = algorithm.blocksize * 262144  # 2^18
    except AttributeError:
        blocksize = 16777216  # 2^24
    _log.debug("Using blocksize %s for calculating the checksum" % blocksize)

    try:
        with open(path, 'rb') as fh:
            for block in iter(lambda: fh.read(blocksize), b''):
                algorithm.update(block)
    except IOError as err:
        raise EasyBuildError("Failed to read %s: %s", path, err)

    return algorithm.hexdigest()


def verify_checksum(path, checksums):
    """
    Verify checksum of specified file.

    :param file: path of file to verify checksum of
    :param checksum: checksum value (and type, optionally, default is MD5), e.g., 'af314', ('sha', '5ec1b')
    """

    filename = os.path.basename(path)

    # if no checksum is provided, pretend checksum to be valid, unless presence of checksums to verify is enforced
    if checksums is None:
        if build_option('enforce_checksums'):
            raise EasyBuildError("Missing checksum for %s", filename)
        else:
            return True

    # make sure we have a list of checksums
    if not isinstance(checksums, list):
        checksums = [checksums]

    for checksum in checksums:
        if isinstance(checksum, dict):
            if filename in checksum:
                # Set this to a string-type checksum
                checksum = checksum[filename]
            elif build_option('enforce_checksums'):
                raise EasyBuildError("Missing checksum for %s", filename)
            else:
                # Set to None and allow to fail elsewhere
                checksum = None

        if isinstance(checksum, string_type):
            # if no checksum type is specified, it is assumed to be MD5 (32 characters) or SHA256 (64 characters)
            if len(checksum) == 64:
                typ = CHECKSUM_TYPE_SHA256
            elif len(checksum) == 32:
                typ = CHECKSUM_TYPE_MD5
            else:
                raise EasyBuildError("Length of checksum '%s' (%d) does not match with either MD5 (32) or SHA256 (64)",
                                     checksum, len(checksum))

        elif isinstance(checksum, tuple):
            # if checksum is specified as a tuple, it could either be specifying:
            # * the type of checksum + the checksum value
            # * a set of alternative valid checksums to consider => recursive call
            if len(checksum) == 2 and checksum[0] in CHECKSUM_FUNCTIONS:
                typ, checksum = checksum
            else:
                _log.info("Found %d alternative checksums for %s, considering them one-by-one...", len(checksum), path)
                for cand_checksum in checksum:
                    if verify_checksum(path, cand_checksum):
                        _log.info("Found matching checksum for %s: %s", path, cand_checksum)
                        return True
                    else:
                        _log.info("Ignoring non-matching checksum for %s (%s)...", path, cand_checksum)
        else:
            raise EasyBuildError("Invalid checksum spec '%s', should be a string (MD5) or 2-tuple (type, value).",
                                 checksum)

        actual_checksum = compute_checksum(path, typ)
        _log.debug("Computed %s checksum for %s: %s (correct checksum: %s)" % (typ, path, actual_checksum, checksum))

        if actual_checksum != checksum:
            return False

    # if we land here, all checksums have been verified to be correct
    return True


def is_sha256_checksum(value):
    """Check whether provided string is a SHA256 checksum."""
    res = False
    if isinstance(value, string_type):
        if re.match('^[0-9a-f]{64}$', value):
            res = True
            _log.debug("String value '%s' has the correct format to be a SHA256 checksum", value)
        else:
            _log.debug("String value '%s' does NOT have the correct format to be a SHA256 checksum", value)
    else:
        _log.debug("Non-string value %s is not a SHA256 checksum", value)

    return res


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

        change_dir(new_dir)
        lst = get_local_dirs_purged()

    # make sure it's a directory, and not a (single) file that was in a tarball for example
    while not os.path.isdir(new_dir):
        new_dir = os.path.dirname(new_dir)

    _log.debug("Last dir list %s" % lst)
    _log.debug("Possible new dir %s found" % new_dir)
    return new_dir


def find_extension(filename):
    """Find best match for filename extension."""
    # sort by length, so longest file extensions get preference
    suffixes = sorted(EXTRACT_CMDS.keys(), key=len, reverse=True)
    pat = r'(?P<ext>%s)$' % '|'.join([s.replace('.', '\\.') for s in suffixes])
    res = re.search(pat, filename, flags=re.IGNORECASE)
    if res:
        ext = res.group('ext')
    else:
        raise EasyBuildError('Unknown file type for file %s', filename)

    return ext


def extract_cmd(filepath, overwrite=False):
    """
    Determines the file type of file at filepath, returns extract cmd based on file suffix
    """
    filename = os.path.basename(filepath)
    ext = find_extension(filename)
    target = filename[:-len(ext)]

    cmd_tmpl = EXTRACT_CMDS[ext.lower()]
    if overwrite:
        if 'unzip -qq' in cmd_tmpl:
            cmd_tmpl = cmd_tmpl.replace('unzip -qq', 'unzip -qq -o')

    return cmd_tmpl % {'filepath': filepath, 'target': target}


def is_patch_file(path):
    """Determine whether file at specified path is a patch file (based on +++ and --- lines being present)."""
    txt = read_file(path)
    return bool(re.search(r'^\+{3}\s', txt, re.M) and re.search(r'^-{3}\s', txt, re.M))


def det_patched_files(path=None, txt=None, omit_ab_prefix=False, github=False, filter_deleted=False):
    """
    Determine list of patched files from a patch.
    It searches for "+++ path/to/patched/file" lines to determine the patched files.
    Note: does not correctly handle filepaths with spaces.

    :param path: the path to the diff
    :param txt: the contents of the diff (either path or txt should be give)
    :param omit_ab_prefix: ignore the a/ or b/ prefix of the files
    :param github: only consider lines that start with 'diff --git' to determine list of patched files
    :param filter_deleted: filter out all files that were deleted by the patch
    """
    if github:
        patched_regex = r"^diff --git (?:a/)?\S+\s*(?P<ab_prefix>b/)?(?P<file>\S+)"
    else:
        patched_regex = r"^\s*\+{3}\s+(?P<ab_prefix>[ab]/)?(?P<file>\S+)"
    patched_regex = re.compile(patched_regex, re.M)

    if path is not None:
        # take into account that file may contain non-UTF-8 characters;
        # so, read a byte string, and decode to UTF-8 string (ignoring any non-UTF-8 characters);
        txt = read_file(path, mode='rb').decode('utf-8', 'replace')
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


def apply_patch(patch_file, dest, fn=None, copy=False, level=None, use_git_am=False, use_git=False):
    """
    Apply a patch to source code in directory dest
    - assume unified diff created with "diff -ru old new"

    Raises EasyBuildError on any error and returns True on success
    """

    if use_git_am:
        _log.deprecated("'use_git_am' named argument in apply_patch function has been renamed to 'use_git'", '5.0')
        use_git = True

    if build_option('extended_dry_run'):
        # skip checking of files in dry run mode
        patch_filename = os.path.basename(patch_file)
        dry_run_msg("* applying patch file %s" % patch_filename, silent=build_option('silent'))

    elif not os.path.isfile(patch_file):
        raise EasyBuildError("Can't find patch %s: no such file", patch_file)

    elif fn and not os.path.isfile(fn):
        raise EasyBuildError("Can't patch file %s: no such file", fn)

    # copy missing files
    if copy:
        if build_option('extended_dry_run'):
            dry_run_msg("  %s copied to %s" % (patch_file, dest), silent=build_option('silent'))
        else:
            copy_file(patch_file, dest)
            _log.debug("Copied patch %s to dir %s" % (patch_file, dest))

        # early exit, work is done after copying
        return True

    elif not os.path.isdir(dest):
        raise EasyBuildError("Can't patch directory %s: no such directory", dest)

    # use absolute paths
    abs_patch_file = os.path.abspath(patch_file)
    abs_dest = os.path.abspath(dest)

    # Attempt extracting the patch if it ends in .patch.gz, .patch.bz2, .patch.xz
    # split in stem (filename w/o extension) + extension
    patch_stem, patch_extension = os.path.splitext(os.path.split(abs_patch_file)[1])
    # Supports only bz2, gz and xz. zip can be archives which are not supported.
    if patch_extension in ['.gz', '.bz2', '.xz']:
        # split again to get the second extension
        patch_subextension = os.path.splitext(patch_stem)[1]
        if patch_subextension == ".patch":
            workdir = tempfile.mkdtemp(prefix='eb-patch-')
            _log.debug("Extracting the patch to: %s", workdir)
            # extracting the patch
            extracted_dir = extract_file(abs_patch_file, workdir, change_into_dir=False)
            abs_patch_file = os.path.join(extracted_dir, patch_stem)

    if use_git:
        verbose = '--verbose ' if build_option('debug') else ''
        patch_cmd = "git apply %s%s" % (verbose, abs_patch_file)
    else:
        if level is None and build_option('extended_dry_run'):
            level = '<derived>'

        elif level is None:
            # guess value for -p (patch level)
            # - based on +++ lines
            # - first +++ line that matches an existing file determines guessed level
            # - we will try to match that level from current directory
            patched_files = det_patched_files(path=abs_patch_file)

            if not patched_files:
                raise EasyBuildError("Can't guess patchlevel from patch %s: no testfile line found in patch",
                                     abs_patch_file)

            level = guess_patch_level(patched_files, abs_dest)

            if level is None:  # level can also be 0 (zero), so don't use "not level"
                # no match
                raise EasyBuildError("Can't determine patch level for patch %s from directory %s", patch_file, abs_dest)
            else:
                _log.debug("Guessed patch level %d for patch %s" % (level, patch_file))

        else:
            _log.debug("Using specified patch level %d for patch %s" % (level, patch_file))

        patch_cmd = "patch -b -p%s -i %s" % (level, abs_patch_file)

    out, ec = run.run_cmd(patch_cmd, simple=False, path=abs_dest, log_ok=False, trace=False)

    if ec:
        raise EasyBuildError("Couldn't apply patch file %s. Process exited with code %s: %s", patch_file, ec, out)
    return True


def apply_regex_substitutions(paths, regex_subs, backup='.orig.eb', on_missing_match=None):
    """
    Apply specified list of regex substitutions.

    :param paths: list of paths to files to patch (or just a single filepath)
    :param regex_subs: list of substitutions to apply, specified as (<regexp pattern>, <replacement string>)
    :param backup: create backup of original file with specified suffix (no backup if value evaluates to False)
    :param on_missing_match: Define what to do when no match was found in the file.
                             Can be 'error' to raise an error, 'warn' to print a warning or 'ignore' to do nothing
                             Defaults to the value of --strict
    """
    if on_missing_match is None:
        on_missing_match = build_option('strict')
    allowed_values = (ERROR, IGNORE, WARN)
    if on_missing_match not in allowed_values:
        raise EasyBuildError('Invalid value passed to on_missing_match: %s (allowed: %s)',
                             on_missing_match, ', '.join(allowed_values))

    if isinstance(paths, string_type):
        paths = [paths]

    # only report when in 'dry run' mode
    if build_option('extended_dry_run'):
        paths_str = ', '.join(paths)
        dry_run_msg("applying regex substitutions to file(s): %s" % paths_str, silent=build_option('silent'))
        for regex, subtxt in regex_subs:
            dry_run_msg("  * regex pattern '%s', replacement string '%s'" % (regex, subtxt))

    else:
        _log.info("Applying following regex substitutions to %s: %s", paths, regex_subs)

        compiled_regex_subs = [(re.compile(regex), subtxt) for (regex, subtxt) in regex_subs]

        for path in paths:
            try:
                # make sure that file can be opened in text mode;
                # it's possible this fails with UnicodeDecodeError when running EasyBuild with Python 3
                try:
                    with open_file(path, 'r') as fp:
                        txt_utf8 = fp.read()
                except UnicodeDecodeError as err:
                    _log.info("Encountered UnicodeDecodeError when opening %s in text mode: %s", path, err)
                    path_backup = back_up_file(path)
                    _log.info("Editing %s to strip out non-UTF-8 characters (backup at %s)", path, path_backup)
                    txt = read_file(path, mode='rb')
                    txt_utf8 = txt.decode(encoding='utf-8', errors='replace')
                    del txt
                    write_file(path, txt_utf8)

                if backup:
                    copy_file(path, path + backup)
                replacement_msgs = []
                with open_file(path, 'w') as out_file:
                    lines = txt_utf8.split('\n')
                    del txt_utf8
                    for line_id, line in enumerate(lines):
                        for regex, subtxt in compiled_regex_subs:
                            match = regex.search(line)
                            if match:
                                origtxt = match.group(0)
                                replacement_msgs.append("Replaced in line %d: '%s' -> '%s'" %
                                                        (line_id + 1, origtxt, subtxt))
                                line = regex.sub(subtxt, line)
                                lines[line_id] = line
                    out_file.write('\n'.join(lines))
                if replacement_msgs:
                    _log.info('Applied the following substitutions to %s:\n%s', path, '\n'.join(replacement_msgs))
                else:
                    msg = 'Nothing found to replace in %s' % path
                    if on_missing_match == ERROR:
                        raise EasyBuildError(msg)
                    elif on_missing_match == WARN:
                        _log.warning(msg)
                    else:
                        _log.info(msg)

            except (IOError, OSError) as err:
                raise EasyBuildError("Failed to patch %s: %s", path, err)


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


def adjust_permissions(provided_path, permission_bits, add=True, onlyfiles=False, onlydirs=False, recursive=True,
                       group_id=None, relative=True, ignore_errors=False, skip_symlinks=None):
    """
    Change permissions for specified path, using specified permission bits

    :param add: add permissions relative to current permissions (only relevant if 'relative' is set to True)
    :param onlyfiles: only change permissions on files (not directories)
    :param onlydirs: only change permissions on directories (not files)
    :param recursive: change permissions recursively (only makes sense if path is a directory)
    :param group_id: also change group ownership to group with this group ID
    :param relative: add/remove permissions relative to current permissions (if False, hard set specified permissions)
    :param ignore_errors: ignore errors that occur when changing permissions
                          (up to a maximum ratio specified by --max-fail-ratio-adjust-permissions configuration option)

    Add or remove (if add is False) permission_bits from all files (if onlydirs is False)
    and directories (if onlyfiles is False) in path
    """

    if skip_symlinks is not None:
        depr_msg = "Use of 'skip_symlinks' argument for 'adjust_permissions' is deprecated "
        depr_msg += "(symlinks are never followed anymore)"
        _log.deprecated(depr_msg, '4.0')

    provided_path = os.path.abspath(provided_path)

    if recursive:
        _log.info("Adjusting permissions recursively for %s", provided_path)
        allpaths = [provided_path]
        for root, dirs, files in os.walk(provided_path):
            paths = []
            if not onlydirs:
                paths.extend(files)
            if not onlyfiles:
                # os.walk skips symlinked dirs by default, i.e., no special handling needed here
                paths.extend(dirs)

            for path in paths:
                allpaths.append(os.path.join(root, path))

    else:
        _log.info("Adjusting permissions for %s (no recursion)", provided_path)
        allpaths = [provided_path]

    failed_paths = []
    fail_cnt = 0
    err_msg = None
    for path in allpaths:
        try:
            # don't change permissions if path is a symlink, since we're not checking where the symlink points to
            # this is done because of security concerns (symlink may point out of installation directory)
            # (note: os.lchmod is not supported on Linux)
            if os.path.islink(path):
                _log.debug("Not changing permissions for %s, since it's a symlink", path)
            else:
                # determine current permissions
                current_perms = os.lstat(path)[stat.ST_MODE]
                _log.debug("Current permissions for %s: %s", path, oct(current_perms))

                if relative:
                    # relative permissions (add or remove)
                    if add:
                        _log.debug("Adding permissions for %s: %s", path, oct(permission_bits))
                        new_perms = current_perms | permission_bits
                    else:
                        _log.debug("Removing permissions for %s: %s", path, oct(permission_bits))
                        new_perms = current_perms & ~permission_bits
                else:
                    # hard permissions bits (not relative)
                    new_perms = permission_bits
                    _log.debug("Hard setting permissions for %s: %s", path, oct(new_perms))

                # only actually do chmod if current permissions are not correct already
                # (this is important because chmod requires that files are owned by current user)
                if new_perms == current_perms:
                    _log.debug("Current permissions for %s are already OK: %s", path, oct(current_perms))
                else:
                    _log.debug("Changing permissions for %s to %s", path, oct(new_perms))
                    os.chmod(path, new_perms)

            if group_id:
                # only change the group id if it the current gid is different from what we want
                cur_gid = os.lstat(path).st_gid
                if cur_gid == group_id:
                    _log.debug("Group id of %s is already OK (%s)", path, group_id)
                else:
                    _log.debug("Changing group id of %s to %s", path, group_id)
                    os.lchown(path, -1, group_id)

        except OSError as err:
            if ignore_errors:
                # ignore errors while adjusting permissions (for example caused by bad links)
                _log.info("Failed to chmod/chown %s (but ignoring it): %s", path, err)
                fail_cnt += 1
            else:
                failed_paths.append(path)
                err_msg = err

    if failed_paths:
        raise EasyBuildError("Failed to chmod/chown several paths: %s (last error: %s)", failed_paths, err_msg)

    # we ignore some errors, but if there are to many, something is definitely wrong
    fail_ratio = fail_cnt / float(len(allpaths))
    max_fail_ratio = float(build_option('max_fail_ratio_adjust_permissions'))
    if fail_ratio > max_fail_ratio:
        raise EasyBuildError("%.2f%% of permissions/owner operations failed (more than %.2f%%), "
                             "something must be wrong...", 100 * fail_ratio, 100 * max_fail_ratio)
    elif fail_cnt > 0:
        _log.debug("%.2f%% of permissions/owner operations failed, ignoring that...", 100 * fail_ratio)


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


def set_gid_sticky_bits(path, set_gid=None, sticky=None, recursive=False):
    """Set GID/sticky bits on specified path."""
    if set_gid is None:
        set_gid = build_option('set_gid_bit')
    if sticky is None:
        sticky = build_option('sticky_bit')

    bits = 0
    if set_gid:
        bits |= stat.S_ISGID
    if sticky:
        bits |= stat.S_ISVTX
    if bits:
        try:
            adjust_permissions(path, bits, add=True, relative=True, recursive=recursive, onlydirs=True)
        except OSError as err:
            raise EasyBuildError("Failed to set groud ID/sticky bit: %s", err)


def mkdir(path, parents=False, set_gid=None, sticky=None):
    """
    Create a directory
    Directory is the path to create

    :param parents: create parent directories if needed (mkdir -p)
    :param set_gid: set group ID bit, to make subdirectories and files inherit group
    :param sticky: set the sticky bit on this directory (a.k.a. the restricted deletion flag),
                   to avoid users can removing/renaming files in this directory
    """
    if not os.path.isabs(path):
        path = os.path.abspath(path)

    # exit early if path already exists
    if not os.path.exists(path):
        if set_gid is None:
            set_gid = build_option('set_gid_bit')
        if sticky is None:
            sticky = build_option('sticky_bit')

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
        except OSError as err:
            raise EasyBuildError("Failed to create directory %s: %s", path, err)

        # set group ID and sticky bits, if desired
        new_subdir = path[len(existing_parent_path):].lstrip(os.path.sep)
        new_path = os.path.join(existing_parent_path, new_subdir.split(os.path.sep)[0])
        set_gid_sticky_bits(new_path, set_gid, sticky, recursive=True)
    else:
        _log.debug("Not creating existing path %s" % path)


def det_lock_path(lock_name):
    """
    Determine full path for lock with specifed name.
    """
    locks_dir = build_option('locks_dir') or os.path.join(install_path('software'), '.locks')
    return os.path.join(locks_dir, lock_name + '.lock')


def create_lock(lock_name):
    """Create lock with specified name."""

    lock_path = det_lock_path(lock_name)
    _log.info("Creating lock at %s...", lock_path)
    try:
        # we use a directory as a lock, since that's atomically created
        mkdir(lock_path, parents=True)
        global_lock_names.add(lock_name)
    except EasyBuildError as err:
        # clean up the error message a bit, get rid of the "Failed to create directory" part + quotes
        stripped_err = str(err).split(':', 1)[1].strip().replace("'", '').replace('"', '')
        raise EasyBuildError("Failed to create lock %s: %s", lock_path, stripped_err)
    _log.info("Lock created: %s", lock_path)


def check_lock(lock_name):
    """
    Check whether a lock with specified name already exists.

    If it exists, either wait until it's released, or raise an error
    (depending on --wait-on-lock configuration option).
    """
    lock_path = det_lock_path(lock_name)
    if os.path.exists(lock_path):
        _log.info("Lock %s exists!", lock_path)

        wait_interval = build_option('wait_on_lock_interval')
        wait_limit = build_option('wait_on_lock_limit')

        # --wait-on-lock is deprecated, should use --wait-on-lock-limit and --wait-on-lock-interval instead
        wait_on_lock = build_option('wait_on_lock')
        if wait_on_lock is not None:
            depr_msg = "Use of --wait-on-lock is deprecated, use --wait-on-lock-limit and --wait-on-lock-interval"
            _log.deprecated(depr_msg, '5.0')

            # if --wait-on-lock-interval has default value and --wait-on-lock is specified too, the latter wins
            # (required for backwards compatibility)
            if wait_interval == DEFAULT_WAIT_ON_LOCK_INTERVAL and wait_on_lock > 0:
                wait_interval = wait_on_lock

            # if --wait-on-lock-limit is not specified we need to wait indefinitely if --wait-on-lock is specified,
            # since the original semantics of --wait-on-lock was that it specified the waiting time interval (no limit)
            if not wait_limit:
                wait_limit = -1

        # wait limit could be zero (no waiting), -1 (no waiting limit) or non-zero value (waiting limit in seconds)
        if wait_limit != 0:
            wait_time = 0
            while os.path.exists(lock_path) and (wait_limit == -1 or wait_time < wait_limit):
                print_msg("lock %s exists, waiting %d seconds..." % (lock_path, wait_interval),
                          silent=build_option('silent'))
                time.sleep(wait_interval)
                wait_time += wait_interval

            if os.path.exists(lock_path) and wait_limit != -1 and wait_time >= wait_limit:
                error_msg = "Maximum wait time for lock %s to be released reached: %s sec >= %s sec"
                raise EasyBuildError(error_msg, lock_path, wait_time, wait_limit)
            else:
                _log.info("Lock %s was released!", lock_path)
        else:
            raise EasyBuildError("Lock %s already exists, aborting!", lock_path)
    else:
        _log.info("Lock %s does not exist", lock_path)


def remove_lock(lock_name):
    """
    Remove lock with specified name.
    """
    lock_path = det_lock_path(lock_name)
    _log.info("Removing lock %s...", lock_path)
    remove_dir(lock_path)
    if lock_name in global_lock_names:
        global_lock_names.remove(lock_name)
    _log.info("Lock removed: %s", lock_path)


def clean_up_locks():
    """
    Clean up all still existing locks that were created in this session.
    """
    for lock_name in list(global_lock_names):
        remove_lock(lock_name)


def clean_up_locks_signal_handler(signum, frame):
    """
    Signal handler, cleans up locks & exits with received signal number.
    """

    if not build_option('silent'):
        print_warning("signal received (%s), cleaning up locks (%s)..." % (signum, ', '.join(global_lock_names)))
    clean_up_locks()

    # by default, a KeyboardInterrupt is raised with SIGINT, so keep doing so
    if signum == signal.SIGINT:
        raise KeyboardInterrupt("keyboard interrupt")
    else:
        sys.exit(signum)


def register_lock_cleanup_signal_handlers():
    """
    Register signal handler for signals that cancel the current EasyBuild session,
    so we can clean up the locks that were created first.
    """
    signums = [
        signal.SIGABRT,
        signal.SIGINT,  # Ctrl-C
        signal.SIGTERM,  # signal 15, soft kill (like when Slurm job is cancelled or received timeout)
        signal.SIGQUIT,  # kinda like Ctrl-C
    ]
    for signum in signums:
        signal.signal(signum, clean_up_locks_signal_handler)


def expand_glob_paths(glob_paths):
    """Expand specified glob paths to a list of unique non-glob paths to only files."""
    paths = []
    for glob_path in glob_paths:
        add_paths = [f for f in glob.glob(os.path.expanduser(glob_path)) if os.path.isfile(f)]
        if add_paths:
            paths.extend(add_paths)
        else:
            raise EasyBuildError("No files found using glob pattern '%s'", glob_path)

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

    _log.deprecated("Use 'remove_dir' rather than 'rmtree2'", '5.0')
    remove_dir(path)


def find_backup_name_candidate(src_file):
    """Returns a non-existing file to be used as destination for backup files"""

    # e.g. 20170817234510 on Aug 17th 2017 at 23:45:10
    timestamp = datetime.datetime.now()
    dst_file = '%s_%s_%s' % (src_file, timestamp.strftime('%Y%m%d%H%M%S'), os.getpid())
    while os.path.exists(dst_file):
        _log.debug("Backup of %s at %s already found at %s, trying again in a second...", src_file, dst_file, timestamp)
        time.sleep(1)
        timestamp = datetime.datetime.now()
        dst_file = '%s_%s_%s' % (src_file, timestamp.strftime('%Y%m%d%H%M%S'), os.getpid())

    return dst_file


def back_up_file(src_file, backup_extension='bak', hidden=False, strip_fn=None):
    """
    Backs up a file appending a backup extension and timestamp to it (if there is already an existing backup).

    :param src_file: file to be back up
    :param backup_extension: extension to use for the backup file (can be empty or None)
    :param hidden: make backup hidden (leading dot in filename)
    :param strip_fn: strip specified trailing substring from filename of backup
    :return: location of backed up file
    """
    fn_prefix, fn_suffix = '', ''
    if hidden:
        fn_prefix = '.'
    if backup_extension:
        fn_suffix = '.%s' % backup_extension

    src_dir, src_fn = os.path.split(src_file)
    if strip_fn and src_fn.endswith(strip_fn):
        src_fn = src_fn[:-len(strip_fn)]

    backup_fp = find_backup_name_candidate(os.path.join(src_dir, fn_prefix + src_fn + fn_suffix))

    copy_file(src_file, backup_fp)
    _log.info("File %s backed up in %s", src_file, backup_fp)

    return backup_fp


def move_logs(src_logfile, target_logfile):
    """Move log file(s)."""

    zip_log_cmd = build_option('zip_logs')

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
                back_up_file(new_log_path)

            # move log to target path
            move_file(app_log, new_log_path)
            _log.info("Moved log file %s to %s" % (src_logfile, new_log_path))

            if zip_log_cmd:
                run.run_cmd("%s %s" % (zip_log_cmd, new_log_path))
                _log.info("Zipped log %s using '%s'", new_log_path, zip_log_cmd)

    except (IOError, OSError) as err:
        raise EasyBuildError("Failed to move log file(s) %s* to new log file %s*: %s",
                             src_logfile, target_logfile, err)


def cleanup(logfile, tempdir, testing, silent=False):
    """
    Cleanup the specified log file and the tmp directory, if desired.

    :param logfile: path to log file to clean up
    :param tempdir: path to temporary directory to clean up
    :param testing: are we in testing mode? if so, don't actually clean up anything
    :param silent: be silent (don't print anything to stdout)
    """

    if build_option('cleanup_tmpdir') and not testing:
        if logfile is not None:
            try:
                for log in [logfile] + glob.glob('%s.[0-9]*' % logfile):
                    os.remove(log)
            except OSError as err:
                raise EasyBuildError("Failed to remove log file(s) %s*: %s", logfile, err)
            print_msg("Temporary log file(s) %s* have been removed." % (logfile), log=None, silent=testing or silent)

        if tempdir is not None:
            try:
                shutil.rmtree(tempdir, ignore_errors=True)
            except OSError as err:
                raise EasyBuildError("Failed to remove temporary directory %s: %s", tempdir, err)
            print_msg("Temporary directory %s has been removed." % tempdir, log=None, silent=testing or silent)

    else:
        msg = "Keeping temporary log file(s) %s* and directory %s." % (logfile, tempdir)
        print_msg(msg, log=None, silent=testing or silent)


def copytree(src, dst, symlinks=False, ignore=None):
    """DEPRECATED and removed. Use copy_dir"""
    _log.deprecated("Use 'copy_dir' rather than 'copytree'", '4.0')


def encode_string(name):
    """
    This encoding function handles funky software names ad infinitum, like:
      example: '0_foo+0x0x#-$__'
      becomes: '0_underscore_foo_plus_0x0x_hash__minus__dollar__underscore__underscore_'
    The intention is to have a robust escaping mechanism for names like c++, C# et al

    It has been inspired by the concepts seen at, but in lowercase style:
    * http://fossies.org/dox/netcdf-4.2.1.1/escapes_8c_source.html
    * http://celldesigner.org/help/CDH_Species_01.html
    * http://research.cs.berkeley.edu/project/sbp/darcsrepo-no-longer-updated/src/edu/berkeley/sbp/misc/ReflectiveWalker.java  # noqa
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
    except OSError as err:
        _log.warn("Could not determine install size: %s" % err)

    return installsize


def find_flexlm_license(custom_env_vars=None, lic_specs=None):
    """
    Find FlexLM license.

    Considered specified list of environment variables;
    checks for path to existing license file or valid license server specification;
    duplicate paths are not retained in the returned list of license specs.

    If no license is found through environment variables, also consider 'lic_specs'.

    :param custom_env_vars: list of environment variables to considered (if None, only consider $LM_LICENSE_FILE)
    :param lic_specs: list of license specifications
    :return: tuple with list of valid license specs found and name of first valid environment variable
    """
    valid_lic_specs = []
    lic_env_var = None

    # regex for license server spec; format: <port>@<server>
    server_port_regex = re.compile(r'^[0-9]+@\S+$')

    # always consider $LM_LICENSE_FILE
    lic_env_vars = ['LM_LICENSE_FILE']
    if isinstance(custom_env_vars, string_type):
        lic_env_vars.insert(0, custom_env_vars)
    elif custom_env_vars is not None:
        lic_env_vars = custom_env_vars + lic_env_vars

    # grab values for defined environment variables
    cand_lic_specs = {}
    for env_var in lic_env_vars:
        if env_var in os.environ:
            cand_lic_specs[env_var] = nub(os.environ[env_var].split(os.pathsep))

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
                        # just try to open file for reading, no need to actually read it
                        open(lic_file, 'rb').close()
                        valid_lic_specs.append(lic_file)
                    except IOError as err:
                        _log.warning("License file %s found, but failed to open it for reading: %s", lic_file, err)

        # stop after finding valid license specs, filter out duplicates
        if valid_lic_specs:
            valid_lic_specs = nub(valid_lic_specs)
            lic_env_var = env_var
            break

    if lic_env_var:
        via_msg = '$%s' % lic_env_var
    else:
        via_msg = "provided license spec"

    _log.info("Found valid license specs via %s: %s", via_msg, valid_lic_specs)

    return (valid_lic_specs, lic_env_var)


def copy_file(path, target_path, force_in_dry_run=False):
    """
    Copy a file from specified location to specified location

    :param path: the original filepath
    :param target_path: path to copy the file to
    :param force_in_dry_run: force copying of file during dry run
    """
    if not force_in_dry_run and build_option('extended_dry_run'):
        dry_run_msg("copied file %s to %s" % (path, target_path))
    else:
        try:
            target_exists = os.path.exists(target_path)
            if target_exists and os.path.samefile(path, target_path):
                _log.debug("Not copying %s to %s since files are identical", path, target_path)
            # if target file exists and is owned by someone else than the current user,
            # try using shutil.copyfile to just copy the file contents
            # since shutil.copy2 will fail when trying to copy over file metadata (since chown requires file ownership)
            elif target_exists and os.stat(target_path).st_uid != os.getuid():
                shutil.copyfile(path, target_path)
                _log.info("Copied contents of file %s to %s", path, target_path)
            else:
                mkdir(os.path.dirname(target_path), parents=True)
                if os.path.exists(path):
                    shutil.copy2(path, target_path)
                elif os.path.islink(path):
                    # special care for copying broken symlinks
                    link_target = os.readlink(path)
                    symlink(link_target, target_path)
                _log.info("%s copied to %s", path, target_path)
        except (IOError, OSError, shutil.Error) as err:
            raise EasyBuildError("Failed to copy file %s to %s: %s", path, target_path, err)


def copy_files(paths, target_path, force_in_dry_run=False, target_single_file=False, allow_empty=True, verbose=False):
    """
    Copy list of files to specified target path.
    Target directory is created if it doesn't exist yet.

    :param paths: list of filepaths to copy
    :param target_path: path to copy files to
    :param force_in_dry_run: force copying of files during dry run
    :param target_single_file: if there's only a single file to copy, copy to a file at target path (not a directory)
    :param allow_empty: allow empty list of paths to copy as input (if False: raise error on empty input list)
    :param verbose: print a message to report copying of files
    """
    # dry run: just report copying, don't actually copy
    if not force_in_dry_run and build_option('extended_dry_run'):
        if len(paths) == 1:
            dry_run_msg("copied %s to %s" % (paths[0], target_path))
        else:
            dry_run_msg("copied %d files to %s" % (len(paths), target_path))

    # special case: single file to copy and target_single_file is True => copy to file
    elif len(paths) == 1 and target_single_file:
        copy_file(paths[0], target_path)
        if verbose:
            print_msg("%s copied to %s" % (paths[0], target_path), prefix=False)

    elif paths:
        # check target path: if it exists it should be a directory; if it doesn't exist, we create it
        if os.path.exists(target_path):
            if os.path.isdir(target_path):
                _log.info("Copying easyconfigs into existing directory %s...", target_path)
            else:
                raise EasyBuildError("%s exists but is not a directory", target_path)
        else:
            mkdir(target_path, parents=True)

        for path in paths:
            copy_file(path, target_path)

        if verbose:
            print_msg("%d file(s) copied to %s" % (len(paths), target_path), prefix=False)

    elif not allow_empty:
        raise EasyBuildError("One or more files to copy should be specified!")


def has_recursive_symlinks(path):
    """
    Check the given directory for recursive symlinks.

    That means symlinks to folders inside the path which would cause infinite loops when traversed regularily.

    :param path: Path to directory to check
    """
    for dirpath, dirnames, filenames in os.walk(path, followlinks=True):
        for name in itertools.chain(dirnames, filenames):
            fullpath = os.path.join(dirpath, name)
            if os.path.islink(fullpath):
                linkpath = os.path.realpath(fullpath)
                fullpath += os.sep  # To catch the case where both are equal
                if fullpath.startswith(linkpath + os.sep):
                    _log.info("Recursive symlink detected at %s", fullpath)
                    return True
    return False


def copy_dir(path, target_path, force_in_dry_run=False, dirs_exist_ok=False, check_for_recursive_symlinks=True,
             **kwargs):
    """
    Copy a directory from specified location to specified location

    :param path: the original directory path
    :param target_path: path to copy the directory to
    :param force_in_dry_run: force running the command during dry run
    :param dirs_exist_ok: boolean indicating whether it's OK if the target directory already exists
    :param check_for_recursive_symlinks: If symlink arg is not given or False check for recursive symlinks first

    shutil.copytree is used if the target path does not exist yet;
    if the target path already exists, the 'copy' function will be used to copy the contents of
    the source path to the target path

    Additional specified named arguments are passed down to shutil.copytree/copy if used.
    """
    if not force_in_dry_run and build_option('extended_dry_run'):
        dry_run_msg("copied directory %s to %s" % (path, target_path))
    else:
        try:
            if check_for_recursive_symlinks and not kwargs.get('symlinks'):
                if has_recursive_symlinks(path):
                    raise EasyBuildError("Recursive symlinks detected in %s. "
                                         "Will not try copying this unless `symlinks=True` is passed",
                                         path)
                else:
                    _log.debug("No recursive symlinks in %s", path)
            if not dirs_exist_ok and os.path.exists(target_path):
                raise EasyBuildError("Target location %s to copy %s to already exists", target_path, path)

            # note: in Python >= 3.8 shutil.copytree works just fine thanks to the 'dirs_exist_ok' argument,
            # but since we need to be more careful in earlier Python versions we use our own implementation
            # in case the target directory exists and 'dirs_exist_ok' is enabled
            if dirs_exist_ok and os.path.exists(target_path):
                # if target directory already exists (and that's allowed via dirs_exist_ok),
                # we need to be more careful, since shutil.copytree will fail (in Python < 3.8)
                # if target directory already exists;
                # so, recurse via 'copy' function to copy files/dirs in source path to target path
                # (NOTE: don't use distutils.dir_util.copy_tree here, see
                # https://github.com/easybuilders/easybuild-framework/issues/3306)

                entries = os.listdir(path)

                # take into account 'ignore' function that is supported by shutil.copytree
                # (but not by 'copy_file' function used by 'copy')
                ignore = kwargs.get('ignore')
                if ignore:
                    ignored_entries = ignore(path, entries)
                    entries = [x for x in entries if x not in ignored_entries]

                # determine list of paths to copy
                paths_to_copy = [os.path.join(path, x) for x in entries]

                copy(paths_to_copy, target_path,
                     force_in_dry_run=force_in_dry_run, dirs_exist_ok=dirs_exist_ok,
                     check_for_recursive_symlinks=False,  # Don't check again
                     **kwargs)

            else:
                # if dirs_exist_ok is not enabled or target directory doesn't exist, just use shutil.copytree
                shutil.copytree(path, target_path, **kwargs)

            _log.info("%s copied to %s", path, target_path)
        except (IOError, OSError, shutil.Error) as err:
            raise EasyBuildError("Failed to copy directory %s to %s: %s", path, target_path, err)


def copy(paths, target_path, force_in_dry_run=False, **kwargs):
    """
    Copy single file/directory or list of files and directories to specified location

    :param paths: path(s) to copy
    :param target_path: target location
    :param force_in_dry_run: force running the command during dry run
    :param kwargs: additional named arguments to pass down to copy_dir
    """
    if isinstance(paths, string_type):
        paths = [paths]

    _log.info("Copying %d files & directories to %s", len(paths), target_path)

    for path in paths:
        full_target_path = os.path.join(target_path, os.path.basename(path))
        mkdir(os.path.dirname(full_target_path), parents=True)

        # copy broken symlinks only if 'symlinks=True' is used
        if os.path.isfile(path) or (os.path.islink(path) and kwargs.get('symlinks')):
            copy_file(path, full_target_path, force_in_dry_run=force_in_dry_run)
        elif os.path.isdir(path):
            copy_dir(path, full_target_path, force_in_dry_run=force_in_dry_run, **kwargs)
        else:
            raise EasyBuildError("Specified path to copy is not an existing file or directory: %s", path)


def get_source_tarball_from_git(filename, targetdir, git_config):
    """
    Downloads a git repository, at a specific tag or commit, recursively or not, and make an archive with it

    :param filename: name of the archive to save the code to (must be .tar.gz)
    :param targetdir: target directory where to save the archive to
    :param git_config: dictionary containing url, repo_name, recursive, and one of tag or commit
    """
    # sanity check on git_config value being passed
    if not isinstance(git_config, dict):
        raise EasyBuildError("Found unexpected type of value for 'git_config' argument: %s" % type(git_config))

    # Making a copy to avoid modifying the object with pops
    git_config = git_config.copy()
    tag = git_config.pop('tag', None)
    url = git_config.pop('url', None)
    repo_name = git_config.pop('repo_name', None)
    commit = git_config.pop('commit', None)
    recursive = git_config.pop('recursive', False)
    keep_git_dir = git_config.pop('keep_git_dir', False)

    # input validation of git_config dict
    if git_config:
        raise EasyBuildError("Found one or more unexpected keys in 'git_config' specification: %s", git_config)

    if not repo_name:
        raise EasyBuildError("repo_name not specified in git_config parameter")

    if not tag and not commit:
        raise EasyBuildError("Neither tag nor commit found in git_config parameter")

    if tag and commit:
        raise EasyBuildError("Tag and commit are mutually exclusive in git_config parameter")

    if not url:
        raise EasyBuildError("url not specified in git_config parameter")

    if not filename.endswith('.tar.gz'):
        raise EasyBuildError("git_config currently only supports filename ending in .tar.gz")

    # prepare target directory and clone repository
    mkdir(targetdir, parents=True)
    targetpath = os.path.join(targetdir, filename)

    # compose 'git clone' command, and run it
    clone_cmd = ['git', 'clone']

    if not keep_git_dir:
        # Speed up cloning by only fetching the most recent commit, not the whole history
        # When we don't want to keep the .git folder there won't be a difference in the result
        clone_cmd.extend(['--depth', '1'])

    if tag:
        clone_cmd.extend(['--branch', tag])
        if recursive:
            clone_cmd.append('--recursive')
    else:
        # checkout is done separately below for specific commits
        clone_cmd.append('--no-checkout')

    clone_cmd.append('%s/%s.git' % (url, repo_name))

    tmpdir = tempfile.mkdtemp()
    cwd = change_dir(tmpdir)
    run.run_cmd(' '.join(clone_cmd), log_all=True, simple=True, regexp=False)

    # if a specific commit is asked for, check it out
    if commit:
        checkout_cmd = ['git', 'checkout', commit]
        if recursive:
            checkout_cmd.extend(['&&', 'git', 'submodule', 'update', '--init', '--recursive'])

        run.run_cmd(' '.join(checkout_cmd), log_all=True, simple=True, regexp=False, path=repo_name)

    elif not build_option('extended_dry_run'):
        # If we wanted to get a tag make sure we actually got a tag and not a branch with the same name
        # This doesn't make sense in dry-run mode as we don't have anything to check
        cmd = 'git describe --exact-match --tags HEAD'
        # Note: Disable logging to also disable the error handling in run_cmd
        (out, ec) = run.run_cmd(cmd, log_ok=False, log_all=False, regexp=False, path=repo_name)
        if ec != 0 or tag not in out.splitlines():
            print_warning('Tag %s was not downloaded in the first try due to %s/%s containing a branch'
                          ' with the same name. You might want to alert the maintainers of %s about that issue.',
                          tag, url, repo_name, repo_name)
            cmds = []

            if not keep_git_dir:
                # make the repo unshallow first;
                # this is equivalent with 'git fetch -unshallow' in Git 1.8.3+
                # (first fetch seems to do nothing, unclear why)
                cmds.append('git fetch --depth=2147483647 && git fetch --depth=2147483647')

            cmds.append('git checkout refs/tags/' + tag)
            # Clean all untracked files, e.g. from left-over submodules
            cmds.append('git clean --force -d -x')
            if recursive:
                cmds.append('git submodule update --init --recursive')
            for cmd in cmds:
                run.run_cmd(cmd, log_all=True, simple=True, regexp=False, path=repo_name)

    # create an archive and delete the git repo directory
    if keep_git_dir:
        tar_cmd = ['tar', 'cfvz', targetpath, repo_name]
    else:
        tar_cmd = ['tar', 'cfvz', targetpath, '--exclude', '.git', repo_name]
    run.run_cmd(' '.join(tar_cmd), log_all=True, simple=True, regexp=False)

    # cleanup (repo_name dir does not exist in dry run mode)
    change_dir(cwd)
    remove(tmpdir)

    return targetpath


def move_file(path, target_path, force_in_dry_run=False):
    """
    Move a file from path to target_path

    :param path: the original filepath
    :param target_path: path to move the file to
    :param force_in_dry_run: force running the command during dry run
    """
    if not force_in_dry_run and build_option('extended_dry_run'):
        dry_run_msg("moved file %s to %s" % (path, target_path))
    else:
        # remove first to ensure portability (shutil.move might fail when overwriting files in some systems)
        remove_file(target_path)
        try:
            mkdir(os.path.dirname(target_path), parents=True)
            shutil.move(path, target_path)
            _log.info("%s moved to %s", path, target_path)
        except (IOError, OSError) as err:
            raise EasyBuildError("Failed to move %s to %s: %s", path, target_path, err)


def diff_files(path1, path2):
    """
    Return unified diff between two files
    """
    file1_lines = ['%s\n' % line for line in read_file(path1).split('\n')]
    file2_lines = ['%s\n' % line for line in read_file(path2).split('\n')]
    return ''.join(difflib.unified_diff(file1_lines, file2_lines, fromfile=path1, tofile=path2))


def install_fake_vsc():
    """
    Put fake 'vsc' Python package in place, to catch easyblocks/scripts that still import from vsc.* namespace
    (vsc-base & vsc-install were ingested into the EasyBuild framework for EasyBuild 4.0,
     see https://github.com/easybuilders/easybuild-framework/pull/2708)
    """
    # note: install_fake_vsc is called before parsing configuration, so avoid using functions that use build_option,
    # like mkdir, write_file, ...
    fake_vsc_path = os.path.join(tempfile.mkdtemp(prefix='fake_vsc_'))

    fake_vsc_init = '\n'.join([
        'import os',
        'import sys',
        'import inspect',
        '',
        'stack = inspect.stack()',
        'filename, lineno = "UNKNOWN", "UNKNOWN"',
        '',
        'for frame in stack[1:]:',
        '    _, cand_filename, cand_lineno, _, code_context, _ = frame',
        '    if code_context:',
        '        filename, lineno = cand_filename, cand_lineno',
        '        break',
        '',
        '# ignore imports from pkgutil.py (part of Python standard library)',
        '# or from pkg_resources/__init__.py (setuptools),',
        '# which may happen due to a system-wide installation of vsc-base',
        '# even if it is not actually actively used...',
        'if os.path.basename(filename) != "pkgutil.py" and not filename.endswith("pkg_resources/__init__.py"):',
        '    error_msg = "\\nERROR: Detected import from \'vsc\' namespace in %s (line %s)\\n" % (filename, lineno)',
        '    error_msg += "vsc-base & vsc-install were ingested into the EasyBuild framework in EasyBuild v4.0\\n"',
        '    error_msg += "The functionality you need may be available in the \'easybuild.base.*\' namespace.\\n"',
        '    sys.stderr.write(error_msg)',
        '    sys.exit(1)',
    ])

    fake_vsc_init_path = os.path.join(fake_vsc_path, 'vsc', '__init__.py')
    if not os.path.exists(os.path.dirname(fake_vsc_init_path)):
        os.makedirs(os.path.dirname(fake_vsc_init_path))
    with open_file(fake_vsc_init_path, 'w') as fp:
        fp.write(fake_vsc_init)

    sys.path.insert(0, fake_vsc_path)

    return fake_vsc_path


def get_easyblock_class_name(path):
    """Make sure file is an easyblock and get easyblock class name"""
    fn = os.path.basename(path).split('.')[0]
    mod = imp.load_source(fn, path)
    clsmembers = inspect.getmembers(mod, inspect.isclass)
    for cn, co in clsmembers:
        if co.__module__ == mod.__name__:
            ancestors = inspect.getmro(co)
            if any(a.__name__ == 'EasyBlock' for a in ancestors):
                return cn
    return None


def is_generic_easyblock(easyblock):
    """Return whether specified easyblock name is a generic easyblock or not."""

    return easyblock and not easyblock.startswith(EASYBLOCK_CLASS_PREFIX)


def copy_easyblocks(paths, target_dir):
    """ Find right location for easyblock file and copy it there"""
    file_info = {
        'eb_names': [],
        'paths_in_repo': [],
        'new': [],
    }

    subdir = os.path.join('easybuild', 'easyblocks')
    if os.path.exists(os.path.join(target_dir, subdir)):
        for path in paths:
            cn = get_easyblock_class_name(path)
            if not cn:
                raise EasyBuildError("Could not determine easyblock class from file %s" % path)

            eb_name = remove_unwanted_chars(decode_class_name(cn).replace('-', '_')).lower()

            if is_generic_easyblock(cn):
                pkgdir = GENERIC_EASYBLOCK_PKG
            else:
                pkgdir = eb_name[0]

            target_path = os.path.join(subdir, pkgdir, eb_name + '.py')

            full_target_path = os.path.join(target_dir, target_path)
            file_info['eb_names'].append(eb_name)
            file_info['paths_in_repo'].append(full_target_path)
            file_info['new'].append(not os.path.exists(full_target_path))
            copy_file(path, full_target_path, force_in_dry_run=True)

    else:
        raise EasyBuildError("Could not find %s subdir in %s", subdir, target_dir)

    return file_info


def copy_framework_files(paths, target_dir):
    """ Find right location for framework file and copy it there"""
    file_info = {
        'paths_in_repo': [],
        'new': [],
    }

    paths = [os.path.abspath(path) for path in paths]

    framework_topdir = 'easybuild-framework'

    for path in paths:
        target_path = None
        dirnames = os.path.dirname(path).split(os.path.sep)

        if framework_topdir in dirnames:
            # construct subdirectory by grabbing last entry in dirnames until we hit 'easybuild-framework' dir
            subdirs = []
            while(dirnames[-1] != framework_topdir):
                subdirs.insert(0, dirnames.pop())

            parent_dir = os.path.join(*subdirs) if subdirs else ''
            target_path = os.path.join(target_dir, parent_dir, os.path.basename(path))
        else:
            raise EasyBuildError("Specified path '%s' does not include a '%s' directory!", path, framework_topdir)

        if target_path:
            file_info['paths_in_repo'].append(target_path)
            file_info['new'].append(not os.path.exists(target_path))
            copy_file(path, target_path)
        else:
            raise EasyBuildError("Couldn't find parent folder of updated file: %s", path)

    return file_info


def create_unused_dir(parent_folder, name):
    """
    Create a new folder in parent_folder using name as the name.
    When a folder of that name already exists, '_0' is appended which is retried for increasing numbers until
    an unused name was found
    """
    if not os.path.isabs(parent_folder):
        parent_folder = os.path.abspath(parent_folder)

    start_path = os.path.join(parent_folder, name)
    for number in range(-1, 10000):  # Start with no suffix and limit the number of attempts
        if number < 0:
            path = start_path
        else:
            path = start_path + '_' + str(number)
        try:
            os.mkdir(path)
            break
        except OSError as err:
            # Distinguish between error due to existing folder and anything else
            if not os.path.exists(path):
                raise EasyBuildError("Failed to create directory %s: %s", path, err)

    # set group ID and sticky bits, if desired
    set_gid_sticky_bits(path, recursive=True)

    return path
