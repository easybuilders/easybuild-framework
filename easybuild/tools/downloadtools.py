##
# Copyright 2015 Ghent University
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
Set of tools to download files.
@author: Jens Timmerman
"""
import os
import shutil
import sys
import urllib2

from vsc.utils import fancylogger

from easybuild.tools import build_log  # import build_log must stay, to activate use of EasyBuildLog
from easybuild.tools.config import build_option
from easybuild.tools.repository.svnrepo import SvnRepository
from easybuild.tools.filetools import make_tarfile, write_file, mkdir


_log = fancylogger.getLogger('filetools', fname=False)

# list of possible protocols we should know how to download
HTTP = 'download_http'
# GIT = download_git
SVN = 'download_svn'
# BZR = download_bzr
FILE = 'download_local_file'
# FTP = download_ftp

# map protocols to things we know how to download
PROTOCOL_MAP = {
    'http': HTTP,
    'https': HTTP,
    # 'http+git': GIT,
    # 'git': GIT,
    # 'bzr': BZR,
    # 'ftp': FTP,
    'svn': SVN,
    'svn+http': SVN,
    'file': FILE,
}


def download_http(filename, url, path, timeout):
    """
    Download a file over the http protocol
    """
    # try downloading, three times max.
    downloaded = False
    max_attempts = 3
    attempt_cnt = 0

    while not downloaded and attempt_cnt < max_attempts:
        try:
            # urllib2 does the right thing for http proxy setups, urllib does not!
            url_fd = urllib2.urlopen(url, timeout=timeout)
            _log.debug('response code for given url %s: %s' % (url, url_fd.getcode()))
            write_file(path, url_fd.read())
            _log.info("Downloaded file %s from url %s to %s" % (filename, url, path))
            downloaded = True
            url_fd.close()
        except urllib2.HTTPError as err:
            if 400 <= err.code <= 499:
                _log.warning("url %s was not found (HTTP response code %s), not trying again" % (url, err.code))
                break
            else:
                _log.warning("HTTPError occured while trying to download %s to %s: %s" % (url, path, err))
                attempt_cnt += 1
        except IOError as err:
            _log.warning("IOError occurred while trying to download %s to %s: %s" % (url, path, err))
            attempt_cnt += 1
        except Exception, err:
            _log.error("Unexpected error occurred when trying to download %s to %s: %s" % (url, path, err))

        if not downloaded and attempt_cnt < max_attempts:
            _log.info("Attempt %d of downloading %s to %s failed, trying again..." % (attempt_cnt, url, path))

    if downloaded:
        _log.info("Successful download of file %s from url %s to path %s" % (filename, url, path))
        return path
    else:
        _log.warning("Download of %s to %s failed, done trying" % (url, path))
        return None


def download_svn(revision, url, path, timeout):
    """
    Download a svn repository and create a tarball out of it in the given path
    timeout is ignored here
    """
    # transform url into something SvnRepository understands
    if url.startswith('svn+'):
        url = url[4:]
    # revision could already be a part of the url, we don't want that
    if url.endswith(str(revision)):
        url = url[:-len(revision)]
    # same for path
    if path.endswith(str(revision)):
        path = path[:-len(revision)]
    path = os.path.join(path, 'repo')
    # svn revisions are digit's so only get these, some packages have version='r1234'
    int_revision = ''.join([x for x in revision if x.isdigit()])

    try:
        svnrepo = SvnRepository(url)
    except AttributeError, err:
        _log.debug('error checkout out svn repo %s', err)
        raise err
    svnrepo.export(path, int_revision)
    # make a tarfile in the directory next to the repo
    tarpath = os.path.join(path, '..', revision)
    make_tarfile(tarpath, path)
    # path will always have '/repo' in it, so the rm should be file
    shutil.rmtree(os.path.join(path))
    return tarpath


def download_local_file(filename, url, path, timeout):
    """
    Dowloading a local file is just copying it
    timeout is ignored here.
    """
    if not url.endswith(filename):
        url = os.path.join(filename)
    if url.startswith('file://'):
        url = url[7:]
    _log.debug("copying %s to %s", url, path)
    try:
        shutil.copy2(url, path)
    except IOError, error:
        if error.errno == 2:  # no such file or directory
            return None
        raise
    return path


def download_file(filename, url, path):
    """
    Download a file from the given url, to the specified path.
    This function will parse the url and try to use the protcol that best matches the url to download it
    if the protocol is a versioning control system it will do a checkout of the repo and use filename as the
    revision to check out instead of the file.
    it will save this to the path as a tarball
    returns the name of the downloaded file/tarball
    """
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

    protocol = url.split(':')[0]
    if protocol not in PROTOCOL_MAP:
        _log.error("Can't handle url: %s, unsupported protocol %s currently only %s are supported" %
                   (url, protocol, PROTOCOL_MAP.keys()))
    _log.debug("Downloading %s from %s to %s using protocol %s", filename, url, path, protocol)
    # call the download_XXX function
    return getattr(sys.modules[__name__], PROTOCOL_MAP[protocol])(filename, url, path, timeout)
