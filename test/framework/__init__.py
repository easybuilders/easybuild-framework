##
# Copyright 2012-2026 Ghent University
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
Declares the test.framework namespace.

@author: Toon Willems (Ghent University)
"""

from pathlib import Path
from easybuild.tools.filetools import read_file

TEST_DIR = Path(__file__).parent
REPO_ROOT = TEST_DIR.parent.parent
TEST_MODULES_DIR = TEST_DIR / 'modules'
TEST_ECS_DIR = TEST_DIR / 'easyconfigs' / 'test_ecs'
TOY_EC = TEST_ECS_DIR / 't' / 'toy' / 'toy-0.0.eb'
TOY_EC_TXT: str = read_file(TOY_EC)
