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

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import os
import time

from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.format.one import EB_FORMAT_EXTENSION
from easybuild.framework.easyconfig.format.yeb import YEB_FORMAT_EXTENSION, is_yeb_format
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

    def easyconfig_path_for(self, cfg, name, version, isyeb=None):
        """
        Determine path to easyconfig file for specified software name/version

        :param cfg: full path to easyconfig file to determine path in repository for
        :param name: software name
        :param version: (full) software version
        :param isyeb: whether or not easyconfig file is in .yeb format (if None, will be derived via cfg)
        """
        if isyeb is None:
            isyeb = is_yeb_format(cfg, None)

        if isyeb:
            ext = YEB_FORMAT_EXTENSION
        else:
            ext = EB_FORMAT_EXTENSION

        return os.path.join(self.wc, self.subdir, name, '%s-%s%s' % (name, version, ext))

    def add_easyconfig(self, cfg, name, version, stats, previous, dest=None):
        """
        Add the eb-file for software name and version to the repository.
        stats should be a dict containing statistics.
        if previous is true -> append the statistics to the file
        This will return the path to the created file (for use in subclasses)

        :param cfg: full path to easyconfig file to determine path in repository for
        :param name: software name
        :param version: (full) software version
        :param stats: build stats to include in easyconfig file
        :param previous: previous build stats (if any)
        :param dest: destination for easyconfig file in repository (will be derived if None)
        """
        isyeb = is_yeb_format(cfg, None)

        if dest is None:
            dest = self.easyconfig_path_for(cfg, name, version, isyeb=isyeb)

        txt = "# Built with EasyBuild version %s on %s\n" % (VERBOSE_VERSION, time.strftime("%Y-%m-%d_%H-%M-%S"))

        txt += read_file(cfg)

        # add build stats, taking into account format and possible previous build stats
        statscomment = "\n# Build statistics\n"

        if isyeb:
            statsprefix = "buildstats: ["
        else:
            statsprefix = "buildstats = ["

        statssuffix = "]\n"

        if previous:
            statstxt = statscomment + statsprefix + '\n'
            for entry in previous + [stats]:
                statstxt += stats_to_str(entry, isyeb=isyeb) + ',\n'
            statstxt += statssuffix
        else:
            statstxt = statscomment + statsprefix + stats_to_str(stats, isyeb=isyeb) + statssuffix

        txt += statstxt
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
