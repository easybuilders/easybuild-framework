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
EasyBuild support for SCOTCH, implemented as an easyblock
"""
import fileinput
import os
import re
import sys
import shutil

import easybuild.tools.toolkit as toolkit
from easybuild.framework.application import Application
from easybuild.tools.filetools import run_cmd, copytree


class EB_SCOTCH(Application):
    """Support for building/installing SCOTCH."""

    def configure(self):
        """Configure SCOTCH build: locate the template makefile, copy it to a general Makefile.inc and patch it."""

        # pick template makefile
        comp_fam = self.toolkit().comp_family()
        if comp_fam == toolkit.INTEL:
            makefilename = 'Makefile.inc.x86-64_pc_linux2.icc'
        elif comp_fam == toolkit.GCC:
            makefilename = 'Makefile.inc.x86-64_pc_linux2'
        else:
            self.log.error("Unknown compiler family used: %s" % comp_fam)

        # create Makefile.inc
        try:
            srcdir = os.path.join(self.getcfg('startfrom'), 'src')
            src = os.path.join(srcdir, 'Make.inc', makefilename)
            dst = os.path.join(srcdir, 'Makefile.inc')
            shutil.copy2(src, dst)
            self.log.debug("Successfully copied Makefile.inc to src dir.")
        except OSError:
            self.log.error("Copying Makefile.inc to src dir failed.")

        # the default behaviour of these makefiles is still wrong
        # e.g., compiler settings, and we need -lpthread
        try:
            for line in fileinput.input(dst, inplace=1, backup='.orig.easybuild'):
                # use $CC and the likes since we're at it.
                line = re.sub(r"^CCS\s*=.*$", "CCS\t= $(CC)", line)
                line = re.sub(r"^CCP\s*=.*$", "CCP\t= $(MPICC)", line)
                line = re.sub(r"^CCD\s*=.*$", "CCD\t= $(MPICC)", line)
                # append -lpthread to LDFLAGS
                line = re.sub(r"^LDFLAGS\s*=(?P<ldflags>.*$)", "LDFLAGS\t=\g<ldflags> -lpthread", line)
                sys.stdout.write(line)
        except IOError, err:
            self.log.error("Can't modify/write Makefile in 'Makefile.inc': %s" % (err))

        # change to src dir for building
        try:
            os.chdir(srcdir)
            self.log.debug("Changing to src dir.")
        except OSError, err:
            self.log.error("Failed to change to src dir: %s" % err)

    def make(self):
        """Build by running make, but with some special options for SCOTCH depending on the compiler."""

        ccs = os.environ['CC']
        ccp = os.environ['MPICC']
        ccd = os.environ['MPICC']

        cflags = "-fPIC -O3 -DCOMMON_FILE_COMPRESS_GZ -DCOMMON_PTHREAD -DCOMMON_RANDOM_FIXED_SEED -DSCOTCH_RENAME"
        if self.toolkit().comp_family() == toolkit.GCC:
            cflags += " -Drestrict=__restrict"
        else:
            cflags += " -restrict -DIDXSIZE64"

        if not self.toolkit().mpi_type() == toolkit.INTEL:
            cflags += " -DSCOTCH_PTHREAD"

        # actually build
        for app in ["scotch", "ptscotch"]:
            cmd = 'make CCS="%s" CCP="%s" CCD="%s" CFLAGS="%s" %s' % (ccs, ccp, ccd, cflags, app)
            run_cmd(cmd, log_all=True, simple=True)

    def make_install(self):
        """Install by copying files and creating group library file."""

        self.log.debug("Installing SCOTCH")

        # copy files to install dir
        regmetis = re.compile(r".*metis.*")
        try:
            for d in ["include", "lib", "bin", "man"]:
                src = os.path.join(self.getcfg('startfrom'), d)
                dst = os.path.join(self.installdir, d)
                # we don't need any metis stuff from scotch!
                copytree(src, dst, ignore=lambda path, files: [x for x in files if regmetis.match(x)])

        except OSError, err:
            self.log.error("Copying %s to installation dir %s failed: %s" % (src, dst, err))

        # create group library file
        scotchlibdir = os.path.join(self.installdir, 'lib')
        scotchgrouplib = os.path.join(scotchlibdir, 'libscotch_group.a')

        try:
            line = ' '.join(os.listdir(scotchlibdir))
            line = "GROUP (%s)" % line

            f = open(scotchgrouplib, 'w')
            f.write(line)
            f.close()
            self.log.info("Successfully written group lib file: %s" % scotchgrouplib)
        except (IOError, OSError), err:
            self.log.error("Can't write to file %s: %s" % (scotchgrouplib, err))

    def sanitycheck(self):
        """Custom sanity check for SCOTCH."""

        if not self.getcfg('sanityCheckPaths'):

            self.setcfg('sanityCheckPaths', {
                                             'files': ['bin/%s' % x for x in ["acpl","amk_fft2","amk_hy",
                                                                              "amk_p2","dggath","dgord",
                                                                              "dgscat","gbase","gmap",
                                                                              "gmk_m2","gmk_msh","gmtst",
                                                                              "gotst","gpart","gtst",
                                                                              "mmk_m2","mord","amk_ccc",
                                                                              "amk_grf","amk_m2","atst",
                                                                              "dgmap","dgpart","dgtst",
                                                                              "gcv","gmk_hy","gmk_m3",
                                                                              "gmk_ub2","gord","gout",
                                                                              "gscat","mcv","mmk_m3",
                                                                              "mtst"]] +
                                                      ['include/%s.h' % x for x in ["esmumps","ptscotchf",
                                                                                    "ptscotch","scotchf",
                                                                                    "scotch"]] +
                                                      ['lib/lib%s.a' % x for x in ["esmumps","ptscotch",
                                                                                   "ptscotcherrexit",
                                                                                   "scotcherr",
                                                                                   "scotch_group",
                                                                                   "ptesmumps",
                                                                                   "ptscotcherr",
                                                                                   "scotch",
                                                                                   "scotcherrexit"]],
                                             'dirs':[]
                                             })

            self.log.info("Customized sanity check paths: %s" % self.getcfg('sanityCheckPaths'))

        Application.sanitycheck(self)
