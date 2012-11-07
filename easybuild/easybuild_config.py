##
# Copyright 2009-2012 Ghent University
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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
EasyBuild configuration file.
"""

import os
import tempfile

from easybuild.tools.build_log import get_log
import easybuild.tools.config as config

log = get_log('easybuild_config')

# build_path possibly overridden by EASYBUILDBUILDPATH
# install_path possibly overridden by EASYBUILDINSTALLPATH

# this should result in a MODULEPATH=($HOME/.local/easybuild|$EASYBUILDPREFIX)/install/modules/all
build_dir = 'build'
install_dir = ''
source_dir = 'sources'

if os.getenv('EASYBUILDPREFIX'):
    prefix = os.getenv('EASYBUILDPREFIX')
else:
    prefix = os.path.join(os.getenv('HOME'), ".local", "easybuild")

if not prefix:
    prefix = "/tmp/easybuild"

build_path = os.path.join(prefix, build_dir)
install_path = os.path.join(prefix, install_dir)
source_path = os.path.join(prefix, source_dir)

# repository for eb files
## Currently, EasyBuild supports the following repository types:

## * `FileRepository`: a plain flat file repository. In this case, the `repositoryPath` contains the directory where the files are stored,
## * `GitRepository`: a _non-empty_ **bare** git repository (created with `git init --bare` or `git clone --bare`).
##   Here, the `repositoryPath` contains the git repository location, which can be a directory or an URL.
## * `SvnRepository`: an SVN repository. In this case, the `repositoryPath` contains the subversion repository location, again, this can be a directory or an URL.

## you have to set the `repository` variable inside the config like so:
## `repository = FileRepository(repositoryPath)`

## optionally a subdir argument can be specified:
## `repository = FileRepository(repositoryPath, subdir)`
repository_path = os.path.join(prefix, 'ebfiles_repo')
repository = FileRepository(repository_path)  #@UndefinedVariable (this file gets exec'ed, so ignore this)

# log format: (dir, filename template)
# supported in template: name, version, data, time
log_format = ("easybuild", "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log")

# set the path where log files will be stored
log_dir = tempfile.gettempdir()

# general cleanliness
del os, get_log, config, log, prefix, build_dir, install_dir, source_dir
