##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
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
EasyBuild support for install the Intel C/C++ compiler suite, implemented as an easyblock
"""

import os
from distutils.version import LooseVersion

from easybuild.easyblocks.intelbase import EB_IntelBase


class EB_icc(EB_IntelBase):
    """Support for installing icc

    - tested with 11.1.046
        - will fail for all older versions (due to newer silent installer)
    """

    def sanitycheck(self):

        if not self.getcfg('sanityCheckPaths'):

            libprefix = ""
            if LooseVersion(self.version()) >= LooseVersion("2011"):
                libprefix = "compiler/lib/intel64/lib"
            else:
                libprefix = "lib/intel64/lib"

            self.setcfg('sanityCheckPaths', {
                                             'files': ["bin/intel64/%s" % x for x in ["icc", "icpc", "idb"]] +
                                                      ["%s%s" % (libprefix, x) for x in ["iomp5.a", "iomp5.so"]],
                                             'dirs': []
                                            })

            self.log.info("Customized sanity check paths: %s" % self.getcfg('sanityCheckPaths'))

        EB_IntelBase.sanitycheck(self)

    def make_module_req_guess(self):
        """Customize paths to check and add in environment.
        """
        if self.getcfg('m32'):
            # 32-bit toolkit
            dirmap = {
                      'PATH': ['bin', 'bin/ia32', 'tbb/bin/ia32'],
                      'LD_LIBRARY_PATH': ['lib', 'lib/ia32'],
                      'MANPATH': ['man', 'share/man', 'man/en_US'],
                      'IDB_HOME': ['bin/intel64']
                     }
        else:
            # 64-bit toolit
            dirmap = {
                      'PATH': ['bin', 'bin/intel64', 'tbb/bin/emt64'],
                      'LD_LIBRARY_PATH': ['lib', 'lib/intel64'],
                      'MANPATH': ['man', 'share/man', 'man/en_US'],
                      'IDB_HOME': ['bin/intel64']
                   }

        # in recent Intel compiler distributions, the actual binaries are
        # in deeper directories, and symlinked in top-level directories
        # however, not all binaries are symlinked (e.g. mcpcom is not)
        if os.path.isdir("%s/composerxe-%s" % (self.installdir, self.version())):
            prefix = "composerxe-%s" % self.version()
            oldmap = dirmap
            dirmap = {}
            for k, vs in oldmap.items():
                dirmap[k] = []
                if k == "LD_LIBRARY_PATH":
                    prefix = "composerxe-%s/compiler" % self.version()
                else:
                    prefix = "composerxe-%s" % self.version()
                for v in vs:
                    v2 = "%s/%s" % (prefix, v)
                    dirmap[k].append(v2)

        elif os.path.isdir("%s/compiler" % (self.installdir)):
            prefix = "compiler"
            oldmap = dirmap
            dirmap = {}
            for k, vs in oldmap.items():
                dirmap[k] = []
                prefix = ''
                if k == "LD_LIBRARY_PATH":
                    prefix = "compiler/"
                for v in vs:
                    v2 = "%s%s" % (prefix, v)
                    dirmap[k].append(v2)

        return dirmap

    def make_module_extra(self):
        """Add extra environment variables for icc, for license file and NLS path."""

        txt = EB_IntelBase.make_module_extra(self)

        txt += "prepend-path\t%s\t\t%s\n" % ('INTEL_LICENSE_FILE', self.license)
        txt += "prepend-path\t%s\t\t$root/%s\n" % ('NLSPATH', 'idb/intel64/locale/%l_%t/%N')

        return txt
