# Copyright 2012 Kenneth Hoste
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
EasyBuild support for MTL4, implemented as an easyblock
"""
import os

from easybuild.easyblocks.generic.tarball import Tarball


class EB_MTL4(Tarball):
    """Support for installing MTL4."""

    def sanity_check_step(self):
        """Custom sanity check for MTL4."""

        incpref = os.path.join('include', 'boost', 'numeric')

        custom_paths = {
                        'files':[],
                        'dirs':[os.path.join(incpref, x) for x in ["itl", "linear_algebra",
                                                                   "meta_math", "mtl"]]
                     }

        super(EB_MTL4, self).sanity_check_step(custom_paths=custom_paths)

    def make_module_req_guess(self):
        """Adjust CPATH for MTL4."""

        guesses = super(EB_MTL4, self).make_module_req_guess()
        guesses.update({'CPATH': 'include'})

        return guesses
