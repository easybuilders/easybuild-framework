##
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
EasyBuild support for building and installing XCrySDen, implemented as an easyblock
"""

import fileinput
import os
import re
import shutil
import sys

from easybuild.framework.application import Application
from easybuild.tools.modules import get_software_root, get_software_version


class EB_XCrySDen(Application):
    """Support for building/installing XCrySDen."""

    def configure(self):
        """
        Check required dependencies, configure XCrySDen build by patching Make.sys file
        and set make target and installation prefix.
        """

        # check dependencies
        deps = ["Mesa", "Tcl", "Tk"]
        for dep in deps:
            if not get_software_root(dep):
                self.log.error("Module for dependency %s not loaded." % dep)

        # copy template Make.sys to patch
        makesys_tpl_file = os.path.join("system", "Make.sys-shared")
        makesys_file = "Make.sys"
        try:
            shutil.copy2(makesys_tpl_file, makesys_file)
        except OSError, err:
            self.log.error("Failed to copy %s: %s" % (makesys_tpl_file, err))

        # patch Make.sys
        settings = {
                    'CFLAGS': os.getenv('CFLAGS'),
                    'CC': os.getenv('CC'),
                    'FFLAGS': os.getenv('F90FLAGS'),
                    'FC': os.getenv('F90'),
                    'TCL_LIB': "-L%s/lib -ltcl%s" % (get_software_root("Tcl"),
                                                     '.'.join(get_software_version("Tcl").split('.')[0:2])),
                    'TCL_INCDIR': "-I%s/include" % get_software_root("Tcl"),
                    'TK_LIB': "-L%s/lib -ltk%s" % (get_software_root("Tk"),
                                                   '.'.join(get_software_version("Tcl").split('.')[0:2])),
                    'TK_INCDIR': "-I%s/include" % get_software_root("Tk"),
                    'GLU_LIB': "-L%s/lib -lGLU" % get_software_root("Mesa"),
                    'GL_LIB': "-L%s/lib -lGL" % get_software_root("Mesa"),
                    'GL_INCDIR': "-I%s/include" % get_software_root("Mesa"),
                    'FFTW3_LIB': "-L%s %s -L%s %s" % (os.getenv('FFTW_LIB_DIR'), os.getenv('LIBFFT'),
                                                      os.getenv('LAPACK_LIB_DIR'), os.getenv('LIBLAPACK_MT')),
                    'FFTW3_INCDIR': "-I%s" % os.getenv('FFTW_INC_DIR'),
                    'COMPILE_TCLTK': 'no',
                    'COMPILE_MESA': 'no',
                    'COMPILE_FFTW': 'no',
                    'COMPILE_MESCHACH': 'no'
                   }

        for line in fileinput.input(makesys_file, inplace=1, backup='.orig'):
            # set config parameters
            for (k, v) in settings.items():
                regexp = re.compile('^%s(\s+=).*'% k)
                if regexp.search(line):
                    line = regexp.sub('%s\\1 %s' % (k, v), line)
                    # remove replaced key/value pairs
                    settings.pop(k)
            sys.stdout.write(line)

        f = open(makesys_file, "a")
        # append remaining key/value pairs
        for (k, v) in settings.items():
            f.write("%s = %s\n" % (k, v))
        f.close()

        self.log.debug("Patched Make.sys: %s" % open(makesys_file, "r").read())

        # set make target to 'xcrysden', such that dependencies are not downloaded/built
        self.updatecfg('makeopts', 'xcrysden')

        # set installation prefix
        self.updatecfg('preinstallopts', 'prefix=%s' % self.installdir)

    # default 'make' and 'make install' should be fine

    def sanitycheck(self):
        """Custom sanity check for XCrySDen."""

        if not self.getcfg('sanityCheckPaths'):

            self.setcfg('sanityCheckPaths',{'files': ["bin/%s" % x for x in ["ptable", "pwi2xsf",
                                                                             "pwo2xsf", "unitconv",
                                                                             "xcrysden"]] +
                                                     ["lib/%s-%s/%s" % (self.name().lower(), self.version(), x)
                                                                        for x in ["atomlab", "calplane",
                                                                                  "cube2xsf", "fhi_coord2xcr",
                                                                                  "fhi_inpini2ftn34", "fracCoor",
                                                                                  "fsReadBXSF", "ftnunit",
                                                                                  "gengeom", "kPath", 
                                                                                  "multislab", "nn", "pwi2xsf",
                                                                                  "pwi2xsf_old", "pwKPath",
                                                                                  "recvec", "savestruct",
                                                                                  "str2xcr", "wn_readbakgen",
                                                                                  "wn_readbands", "xcrys",
                                                                                  "xctclsh", "xsf2xsf"]],
                                            'dirs':[]
                                           })

            self.log.info("Customized sanity check paths: %s" % self.getcfg('sanityCheckPaths'))

        Application.sanitycheck(self)

    def make_module_extra(self):
        """Set extra environment variables in module file."""
        txt = Application.make_module_extra(self)

        for lib in ['Tcl', 'Tk']:
            ver = '.'.join(get_software_version(lib).split('.')[0:2])
            libpath = os.path.join(get_software_root(lib), 'lib', "%s%s" % (lib.lower(), ver))
            txt += self.moduleGenerator.setEnvironment('%s_LIBRARY' % lib.upper(), libpath)

        return txt
