# #
# Copyright 2009-2018 Ghent University
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
Dispatch function for container packages

:author: Shahzeb Siddiqui (Pfizer)
:author: Kenneth Hoste (HPC-UGent)
:author: Mohamed Abidi (Bright Computing)
"""
from vsc.utils import fancylogger

from easybuild.tools.config import CONT_TYPE_SINGULARITY, CONT_TYPE_DOCKER, build_option
from easybuild.tools.build_log import EasyBuildError
from .singularity import singularity as singularity_containerize
from .docker import docker_containerize

_log = fancylogger.getLogger('tools.containers')  # pylint: disable=C0103


def containerize(easyconfigs):
    """
    Generate container recipe + (optionally) image
    """
    _log.experimental("support for generating container recipes and images (--containerize/-C)")

    container_type = build_option('container_type')
    _log.info("Creating %s container", container_type)

    if container_type == CONT_TYPE_SINGULARITY:
        singularity_containerize(easyconfigs)
    elif container_type == CONT_TYPE_DOCKER:
        docker_containerize(easyconfigs)
    else:
        raise EasyBuildError("Unknown container type specified: %s", container_type)
