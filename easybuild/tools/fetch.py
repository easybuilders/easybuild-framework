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
Set of functions related to fetching/downloading files.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import os
import sys
import urllib
from vsc.utils import fancylogger

from easybuild.tools.build_log import print_msg  # import build_log must stay, to activate use of EasyBuildLog
from easybuild.tools.config import build_option, source_paths
from easybuild.tools.filetools import mkdir, run_cmd


_log = fancylogger.getLogger('fetch', fname=False)


def download_file(filename, url, path):
    """Download a file from the given URL, to the specified path."""

    _log.debug("Downloading %s from %s to %s" % (filename, url, path))

    # make sure directory exists
    basedir = os.path.dirname(path)
    mkdir(basedir, parents=True)

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


def get_paths_for(subdir="easyconfigs", robot_path=None):
    """
    Return a list of absolute paths where the specified subdir can be found, determined by the PYTHONPATH
    """

    paths = []

    # primary search path is robot path
    path_list = []
    if isinstance(robot_path, list):
        path_list = robot_path[:]
    elif robot_path is not None:
        path_list = [robot_path]
    # consider Python search path, e.g. setuptools install path for easyconfigs
    path_list.extend(sys.path)

    # figure out installation prefix, e.g. distutils install path for easyconfigs
    (out, ec) = run_cmd("which eb", simple=False, log_all=False, log_ok=False)
    if ec:
        _log.warning("eb not found (%s), failed to determine installation prefix" % out)
    else:
        # eb should reside in <install_prefix>/bin/eb
        install_prefix = os.path.dirname(os.path.dirname(out))
        path_list.append(install_prefix)
        _log.debug("Also considering installation prefix %s..." % install_prefix)

    # look for desired subdirs
    for path in path_list:
        path = os.path.join(path, "easybuild", subdir)
        _log.debug("Looking for easybuild/%s in path %s" % (subdir, path))
        try:
            if os.path.exists(path):
                paths.append(os.path.abspath(path))
                _log.debug("Added %s to list of paths for easybuild/%s" % (path, subdir))
        except OSError, err:
            _log.error("Error occured while searching for subdir %s in %s: %s" % (subdir, path_list, err))

    return paths


def obtain_file(filename, name, premium_path, source_urls, extension=False, urls=None):
    """
    Locate the file with the given name
    - searches in different subdirectories of source path
    - supports fetching file from the web if path is specified as an url (i.e. starts with "http://:")
    """
    robot_path = build_option('robot_path')
    srcpaths = source_paths()

    # should we download or just try and find it?
    if filename.startswith("http://") or filename.startswith("ftp://"):

        # URL detected, so let's try and download it

        url = filename
        filename = url.split('/')[-1]

        # figure out where to download the file to
        filepath = os.path.join(srcpaths[0], name[0].lower(), name)
        if extension:
            filepath = os.path.join(filepath, "extensions")
        _log.info("Creating path %s to download file to" % filepath)
        mkdir(filepath, parents=True)

        try:
            fullpath = os.path.join(filepath, filename)

            # only download when it's not there yet
            if os.path.exists(fullpath):
                _log.info("Found file %s at %s, no need to download it." % (filename, filepath))
                return fullpath

            else:
                if download_file(filename, url, fullpath):
                    return fullpath

        except IOError, err:
            _log.exception("Downloading file %s from url %s to %s failed: %s" % (filename, url, fullpath, err))

    else:
        # try and find file in various locations
        foundfile = None
        failedpaths = []

        # always look first in the dir of the current eb file
        ebpath = [os.path.dirname(premium_path)]

        # always consider robot + easyconfigs install paths as a fall back (e.g. for patch files, test cases, ...)
        common_filepaths = []
        if robot_path is not None:
            common_filepaths.extend(robot_path)
        common_filepaths.extend(get_paths_for("easyconfigs", robot_path=robot_path))

        for path in ebpath + common_filepaths + srcpaths:
            # create list of candidate filepaths
            namepath = os.path.join(path, name)
            letterpath = os.path.join(path, name.lower()[0], name)

            # most likely paths
            candidate_filepaths = [
                letterpath,  # easyblocks-style subdir
                namepath,  # subdir with software name
                path,  # directly in directory
            ]

            # see if file can be found at that location
            for cfp in candidate_filepaths:

                fullpath = os.path.join(cfp, filename)

                # also check in 'extensions' subdir for extensions
                if extension:
                    fullpaths = [
                        os.path.join(cfp, "extensions", filename),
                        os.path.join(cfp, "packages", filename),  # legacy
                        fullpath
                    ]
                else:
                    fullpaths = [fullpath]

                for fp in fullpaths:
                    if os.path.isfile(fp):
                        _log.info("Found file %s at %s" % (filename, fp))
                        foundfile = os.path.abspath(fp)
                        break  # no need to try further
                    else:
                        failedpaths.append(fp)

            if foundfile:
                break  # no need to try other source paths

        if foundfile:
            return foundfile
        else:
            # try and download source files from specified source URLs
            if urls:
                source_urls.extend(urls)

            targetdir = os.path.join(srcpaths[0], name.lower()[0], name)
            mkdir(targetdir, parents=True)

            for url in source_urls:

                if extension:
                    targetpath = os.path.join(targetdir, "extensions", filename)
                else:
                    targetpath = os.path.join(targetdir, filename)

                if isinstance(url, basestring):
                    if url[-1] in ['=', '/']:
                        fullurl = "%s%s" % (url, filename)
                    else:
                        fullurl = "%s/%s" % (url, filename)
                elif isinstance(url, tuple):
                    # URLs that require a suffix, e.g., SourceForge download links
                    # e.g. http://sourceforge.net/projects/math-atlas/files/Stable/3.8.4/atlas3.8.4.tar.bz2/download
                    fullurl = "%s/%s/%s" % (url[0], filename, url[1])
                else:
                    _log.warning("Source URL %s is of unknown type, so ignoring it." % url)
                    continue

                _log.debug("Trying to download file %s from %s to %s ..." % (filename, fullurl, targetpath))
                downloaded = False
                try:
                    if download_file(filename, fullurl, targetpath):
                        downloaded = True

                except IOError, err:
                    _log.debug("Failed to download %s from %s: %s" % (filename, url, err))
                    failedpaths.append(fullurl)
                    continue

                if downloaded:
                    # if fetching from source URL worked, we're done
                    _log.info("Successfully downloaded source file %s from %s" % (filename, fullurl))
                    return targetpath
                else:
                    failedpaths.append(fullurl)

            _log.error("Couldn't find file %s anywhere, and downloading it didn't work either...\nPaths attempted (in order): %s " % (filename, ', '.join(failedpaths)))


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
        for filename in filenames:
            if not filename.endswith('.eb') or filename == 'TEMPLATE.eb':
                continue

            spec = os.path.join(dirpath, filename)
            _log.debug("Found easyconfig %s" % spec)
            files.append(spec)

        # ignore subdirs specified to be ignored by replacing items in dirnames list used by os.walk
        dirnames[:] = [d for d in dirnames if not d in ignore_dirs]

    return files


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


def search_file(paths, query, short=False, ignore_dirs=None, silent=False):
    """
    Search for a particular file (only prints)
    """
    if ignore_dirs is None:
        ignore_dirs = ['.git', '.svn']
    if not isinstance(ignore_dirs, list):
        _log.error("search_file: ignore_dirs (%s) should be of type list, not %s" % (ignore_dirs, type(ignore_dirs)))

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
