##
# Copyright 2009-2025 Ghent University
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
##
"""
Module that takes control of versioning.

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
"""
import os
from easybuild.tools import LooseVersion
from socket import gethostname

# note: release candidates should be versioned as a pre-release, e.g. "1.1rc1"
# 1.1-rc1 would indicate a post-release, i.e., and update of 1.1, so beware!
#
# important note: dev versions should follow the 'X.Y.Z.dev0' format
# see https://www.python.org/dev/peps/pep-0440/#developmental-releases
# recent setuptools versions will *TRANSFORM* something like 'X.Y.Zdev' into 'X.Y.Z.dev0', with a warning like
#   UserWarning: Normalizing '2.4.0dev' to '2.4.0.dev0'
# This causes problems further up the dependency chain...
VERSION = LooseVersion('5.1.1.dev0')
UNKNOWN = 'UNKNOWN'
UNKNOWN_EASYBLOCKS_VERSION = '0.0.UNKNOWN.EASYBLOCKS'


def get_git_revision():
    """
    Returns the git revision (e.g. aab4afc016b742c6d4b157427e192942d0e131fe),
    or UNKNOWN is getting the git revision fails

    relies on GitPython (see http://gitorious.org/git-python)
    """
    try:
        from git import Git, GitCommandError
    except ImportError:
        return UNKNOWN
    try:
        path = os.path.dirname(__file__)
        gitrepo = Git(path)
        res = gitrepo.rev_list('HEAD').splitlines()[0]
        # 'encode' may be required to make sure a regular string is returned rather than a unicode string
        # (only needed in Python 2; in Python 3, regular strings are already unicode)
        if not isinstance(res, str):
            res = res.encode('ascii')
    except GitCommandError:
        res = UNKNOWN

    return res


git_rev = get_git_revision()
if git_rev == UNKNOWN:
    VERBOSE_VERSION = VERSION
else:
    VERBOSE_VERSION = LooseVersion("%s-r%s" % (VERSION, get_git_revision()))

# alias
FRAMEWORK_VERSION = VERBOSE_VERSION

# EasyBlock version
try:
    from easybuild.easyblocks import VERBOSE_VERSION as EASYBLOCKS_VERSION
except Exception:
    EASYBLOCKS_VERSION = UNKNOWN_EASYBLOCKS_VERSION  # make sure it is smaller then anything


def this_is_easybuild():
    """Standard starting message"""
    top_version = max(FRAMEWORK_VERSION, LooseVersion(EASYBLOCKS_VERSION))
    msg = "This is EasyBuild %s (framework: %s, easyblocks: %s) on host %s."
    msg = msg % (top_version, FRAMEWORK_VERSION, EASYBLOCKS_VERSION, gethostname())

    # 'encode' may be required to make sure a regular string is returned rather than a unicode string
    # (only needed in Python 2; in Python 3, regular strings are already unicode)
    if not isinstance(msg, str):
        msg = msg.encode('ascii')

    return msg


def different_major_versions(v1, v2):
    """Compare major versions"""
    # Deal with version instances being either strings or LooseVersion
    if isinstance(v1, str):
        v1 = LooseVersion(v1)
    if isinstance(v2, str):
        v2 = LooseVersion(v2)

    return v1.version[0] != v2.version[0]
