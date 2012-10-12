##
# Copyright 2009-2012 Kenneth Hoste
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
EasyBuild support for building and installing flex, implemented as an easyblock
"""

import os

from easybuild.easyblocks.generic.configuremake import ConfigureMake

class EB_flex(ConfigureMake):
    """Support for building and installing flex."""

    def install_step(self):
        """Building was performed in install dir, no explicit install step required."""
        super(EB_flex, self).install_step()

        # create symlinks for lex and lex++, if they're not there
        try:
            for binary in ["lex", "lex++"]:
                binpath = os.path.join(self.installdir, "bin", binary)
                if not os.path.exists(binpath):
                    os.symlink(os.path.join(self.installdir, "bin", "flex"), binpath)

        except OSError, err:
            self.log.error("Failed to symlink binaries: %s" % err)

    def sanity_check_step(self):
        """Custom sanity check for flex"""

        custom_paths =  {
                         'files':["bin/%s" % x for x in ["flex", "lex", "lex++"]] + ["include/FlexLexer.h"] +
                                 ["lib/lib%s.a" % x for x in ["fl", "fl_pic"]],
                         'dirs':[]
                        }

        super(EB_flex, self).sanity_check_step(custom_paths=custom_paths)
