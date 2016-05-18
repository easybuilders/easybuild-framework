##
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
##
"""
Module that takes control of versioning.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
"""
import os
from distutils.version import LooseVersion
from socket import gethostname

# note: release candidates should be versioned as a pre-release, e.g. "1.1rc1"
# 1.1-rc1 would indicate a post-release, i.e., and update of 1.1, so beware!
#
# important note: dev versions should follow the 'X.Y.Z.dev0' format
# see https://www.python.org/dev/peps/pep-0440/#developmental-releases
# recent setuptools versions will *TRANSFORM* something like 'X.Y.Zdev' into 'X.Y.Z.dev0', with a warning like
#   UserWarning: Normalizing '2.4.0dev' to '2.4.0.dev0'
# This causes problems further up the dependency chain...
VERSION = LooseVersion('2.8.0')
UNKNOWN = 'UNKNOWN'

def get_git_revision():
    """
    Returns the git revision (e.g. aab4afc016b742c6d4b157427e192942d0e131fe),
    or UNKNOWN is getting the git revision fails

    relies on GitPython (see http://gitorious.org/git-python)
    """
    try:
        import git
    except ImportError:
        return UNKNOWN
    try:
        path = os.path.dirname(__file__)
        gitrepo = git.Git(path)
        return gitrepo.rev_list("HEAD").splitlines()[0]
    except git.GitCommandError:
        return UNKNOWN

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
except:
    EASYBLOCKS_VERSION = '0.0.UNKNOWN.EASYBLOCKS'  # make sure it is smaller then anything

def this_is_easybuild():
    """Standard starting message"""
    top_version = max(FRAMEWORK_VERSION, EASYBLOCKS_VERSION)
    # !!! bootstrap_eb.py script checks hard on the string below, so adjust with sufficient care !!!
    msg = "This is EasyBuild %s (framework: %s, easyblocks: %s) on host %s." \
         % (top_version, FRAMEWORK_VERSION, EASYBLOCKS_VERSION, gethostname())

    return msg
