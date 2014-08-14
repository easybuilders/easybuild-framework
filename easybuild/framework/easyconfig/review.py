#!/usr/bin/env python
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
Review module for pull requests on the easyconfigs repo"

@author: Toon Willems (Ghent University)
"""
import os
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.easyconfig import find_related_easyconfigs
from easybuild.tools.github import fetch_easyconfigs_from_pr, download_repo
from easybuild.tools.multi_diff import multi_diff


_log = fancylogger.getLogger('easyconfig.review', fname=False)

def review_pr(pull_request, colored):
    repo_path = os.path.join(download_repo(branch='develop'),'easybuild','easyconfigs')
    pr_files = [path for path in fetch_easyconfigs_from_pr(pull_request) if path.endswith('.eb')]

    for easyconfig in pr_files:
        files = find_related_easyconfigs(repo_path, easyconfig)
        _log.debug("File in pull request %s has these related easyconfigs: %s" % (easyconfig, files))
        for listing in files:
            if listing:
                diff = multi_diff(easyconfig, listing, colored)
                print diff
                break
