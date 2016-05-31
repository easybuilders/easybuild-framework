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
Repository tools

Plain filesystem repository

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
@author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import os
import time

from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import stats_to_str
from easybuild.tools.filetools import mkdir, read_file, write_file
from easybuild.tools.repository.repository import Repository
from easybuild.tools.version import VERBOSE_VERSION

class FileRepository(Repository):
    """Class for file repositories."""

    DESCRIPTION = ("A plain flat file repository. "
                   "The 1st argument contains the directory where the files are stored. "
                   "The optional 2nd argument is a subdir in that path.")

    def setup_repo(self):
        """
        for file based repos this will create the repo directory
        if it doesn't exist.

        if a subdir is specified also create the subdir
        """
        mkdir(os.path.join(self.repo, self.subdir), parents=True)

    def create_working_copy(self):
        """ set the working directory to the repo directory """
        # for sake of convenience
        self.wc = self.repo

    def add_easyconfig(self, cfg, name, version, stats, previous):
        """
        Add the eb-file for software name and version to the repository.
        stats should be a dict containing statistics.
        if previous is true -> append the statistics to the file
        This will return the path to the created file (for use in subclasses)
        """
        # create directory for eb file
        full_path = os.path.join(self.wc, self.subdir, name)
        mkdir(full_path, parents=True)

        # destination
        dest = os.path.join(full_path, "%s-%s.eb" % (name, version))

        txt = "# Built with EasyBuild version %s on %s\n" % (VERBOSE_VERSION, time.strftime("%Y-%m-%d_%H-%M-%S"))

        # copy file
        txt += read_file(cfg)

        # append a line to the eb file so that we don't have git merge conflicts
        if not previous:
            statsprefix = "\n# Build statistics\nbuildstats = ["
            statssuffix = "]\n"
        else:
            # statstemplate = "\nbuildstats.append(%s)\n"
            statsprefix = "\nbuildstats.append("
            statssuffix = ")\n"

        txt += statsprefix + stats_to_str(stats) + statssuffix
        write_file(dest, txt)

        return dest

    def get_buildstats(self, name, ec_version):
        """
        return the build statistics
        """
        full_path = os.path.join(self.wc, self.subdir, name)
        if not os.path.isdir(full_path):
            self.log.debug("module (%s) has not been found in the repo" % name)
            return []

        dest = os.path.join(full_path, "%s.eb" % ec_version)
        if not os.path.isfile(dest):
            self.log.debug("version %s for %s has not been found in the repo" % (ec_version, name))
            return []

        eb = EasyConfig(dest, validate=False)
        return eb['buildstats']
