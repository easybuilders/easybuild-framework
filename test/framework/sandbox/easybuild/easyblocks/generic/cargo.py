##
# Copyright 2009-2024 Ghent University
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
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM


class Cargo(EasyBlock):
    """Generic support for building/installing cargo crates."""

    @staticmethod
    def extra_options():
        """Custom easyconfig parameters for bar."""
        extra_vars = {
            'crates': [[], "List of (crate, version, [repo, rev]) tuples to use", CUSTOM],
        }
        return EasyBlock.extra_options(extra_vars)

    def __init__(self, *args, **kwargs):
        """Constructor for Cargo easyblock."""
        super(Cargo, self).__init__(*args, **kwargs)

        # Populate sources from "crates" list of tuples
        # For simplicity just assume (name,version.ext) tuples
        sources = ['%s-%s' % crate_info for crate_info in self.cfg['crates']]

        # copy EasyConfig instance before we make changes to it
        self.cfg = self.cfg.copy()

        self.cfg.update('sources', sources)
