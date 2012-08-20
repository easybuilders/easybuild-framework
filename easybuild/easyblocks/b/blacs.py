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
EasyBuild support for building and installing BLACS, implemented as an easyblock
"""

import glob
import re
import os
import shutil

import easybuild.tools.toolkit as toolkit
from easybuild.framework.application import Application
from easybuild.tools.filetools import run_cmd
from easybuild.tools.modules import get_software_root


# also used by ScaLAPACK
def det_interface(log, path):
    """Determine interface through 'xintface' heuristic tool"""

    (out, _) = run_cmd(os.path.join(path,"xintface"), log_all=True, simple=False)

    intregexp = re.compile(".*INTFACE\s*=\s*-D(\S+)\s*")
    res = intregexp.search(out)
    if res:
        return res.group(1)
    else:
        log.error("Failed to determine interface, output for xintface: %s" % out)


class EB_BLACS(Application):
    """
    Support for building/installing BLACS
    - configure: symlink BMAKES/Bmake.MPI-LINUX to Bmake.inc
    - make install: copy files
    """

    def configure(self):
        """Configure BLACS build by copying Bmake.inc file."""

        src = os.path.join(self.getcfg('startfrom'), 'BMAKES', 'Bmake.MPI-LINUX')
        dest = os.path.join(self.getcfg('startfrom'), 'Bmake.inc')

        if not os.path.isfile(src):
            self.log.error("Can't find source file %s" % src)

        if os.path.exists(dest):
            self.log.error("Destination file %s exists" % dest)

        try:
            shutil.copy(src, dest)
        except OSError, err:
            self.log.error("Copying %s to % failed: %s" % (src, dest, err))

    def make(self):
        """Build BLACS using make, after figuring out the make options based on the heuristic tools available."""

        # determine MPI base dir and lib
        known_mpis = {
                      toolkit.OPENMPI: "-L$(MPILIBdir) -lmpi_f77",
                      toolkit.MVAPICH2: "$(MPILIBdir)/libmpich.a $(MPILIBdir)/libfmpich.a " + \
                                        "$(MPILIBdir)/libmpl.a -lpthread"
                     }

        mpi_type = self.toolkit().mpi_type()

        base, mpilib = None, None
        if mpi_type in known_mpis.keys():
            base = get_software_root(mpi_type)
            mpilib = known_mpis[mpi_type]

        else:
            self.log.error("Unknown MPI lib %s used (known MPI libs: %s)" % (mpi_type, known_mpis.keys()))

        opts = {
                'mpicc': "%s %s" % (os.getenv('MPICC'), os.getenv('CFLAGS')),
                'mpif77': "%s %s" % (os.getenv('MPIF77'), os.getenv('FFLAGS')),
                'f77': os.getenv('F77'),
                'cc': os.getenv('CC'),
                'builddir': os.getcwd(),
                'base': base,
                'mpilib': mpilib
               }

        # determine interface and transcomm settings
        comm = ''
        interface = 'UNKNOWN'
        try:
            cwd = os.getcwd()
            os.chdir('INSTALL')

            # need to build
            cmd = "make"
            cmd += " CC='%(mpicc)s' F77='%(mpif77)s -I$(MPIINCdir)'  MPIdir=%(base)s" \
                   " MPILIB='%(mpilib)s' BTOPdir=%(builddir)s INTERFACE=NONE" % opts

            # determine interface using xintface
            run_cmd("%s xintface" % cmd, log_all=True, simple=True)

            interface = det_interface(self.log, "./EXE")

            # try and determine transcomm using xtc_CsameF77 and xtc_UseMpich
            if not comm:

                run_cmd("%s xtc_CsameF77" % cmd, log_all=True, simple=True)
                (out, _) = run_cmd("mpirun -np 2 ./EXE/xtc_CsameF77", log_all=True, simple=False)

                # get rid of first two lines, that inform about how to use this tool
                out = '\n'.join(out.split('\n')[2:])

                notregexp = re.compile("_NOT_")

                if not notregexp.search(out):
                    # if it doesn't say '_NOT_', set it
                    comm = "TRANSCOMM='-DCSameF77'"

                else:
                    (_, ec) = run_cmd("%s xtc_UseMpich" % cmd, log_all=False, log_ok=False, simple=False)
                    if ec == 0:

                        (out, _) = run_cmd("mpirun -np 2 ./EXE/xtc_UseMpich", log_all=True, simple=False)

                        if not notregexp.search(out):

                            commregexp = re.compile('Set TRANSCOMM\s*=\s*(.*)$')

                            res = commregexp.search(out)
                            if res:
                                # found how to set TRANSCOMM, so set it
                                comm = "TRANSCOMM='%s'" % res.group(1)
                            else:
                                # no match, set empty TRANSCOMM
                                comm = "TRANSCOMM=''"
                    else:
                        # if it fails to compile, set empty TRANSCOMM
                        comm = "TRANSCOMM=''"

            os.chdir(cwd)
        except OSError, err:
            self.log.error("Failed to determine interface and transcomm settings: %s" % err)

        opts.update({
                     'comm': comm,
                     'int': interface,
                     'base': base
                    })

        add_makeopts = ' MPICC="%(mpicc)s" MPIF77="%(mpif77)s" %(comm)s ' % opts
        add_makeopts += ' INTERFACE=%(int)s MPIdir=%(base)s BTOPdir=%(builddir)s mpi ' % opts

        self.updatecfg('makeopts', add_makeopts)

        Application.make(self)

    def make_install(self):
        """Install by copying files to install dir."""

        # include files and libraries
        for (srcdir, destdir, ext) in [
                                       (os.path.join("SRC", "MPI"), "include", ".h"),  # include files
                                       ("LIB", "lib", ".a"),  # libraries
                                       ]:

            src = os.path.join(self.getcfg('startfrom'), srcdir)
            dest = os.path.join(self.installdir, destdir)

            try:
                os.makedirs(dest)
                os.chdir(src)

                for lib in glob.glob('*%s' % ext):

                    # copy file
                    shutil.copy2(os.path.join(src, lib), dest)

                    self.log.debug("Copied %s to %s" % (lib, dest))

                    if destdir == 'lib':
                        # create symlink with more standard name for libraries
                        symlink_name = "lib%s.a" % lib.split('_')[0]
                        os.symlink(os.path.join(dest, lib), os.path.join(dest, symlink_name))
                        self.log.debug("Symlinked %s/%s to %s" % (dest, lib, symlink_name))

            except OSError, err:
                self.log.error("Copying %s/*.%s to installation dir %s failed: %s"%(src, ext, dest, err))

        # utilities
        src = os.path.join(self.getcfg('startfrom'), 'INSTALL', 'EXE', 'xintface')
        dest = os.path.join(self.installdir, 'bin')

        try:
            os.makedirs(dest)

            shutil.copy2(src, dest)

            self.log.debug("Copied %s to %s" % (src, dest))

        except OSError, err:
            self.log.error("Copying %s to installation dir %s failed: %s" % (src, dest, err))

    def sanitycheck(self):
        """Custom sanity check for BLACS."""

        if not self.getcfg('sanityCheckPaths'):
            self.setcfg('sanityCheckPaths',{
                                            'files': [fil for filptrn in ["blacs", "blacsCinit", "blacsF77init"]
                                                          for fil in ["lib/lib%s.a" % filptrn,
                                                                      "lib/%s_MPI-LINUX-0.a" % filptrn]] +
                                                     ["bin/xintface"],
                                            'dirs': []
                                           })

            self.log.info("Customized sanity check paths: %s" % self.getcfg('sanityCheckPaths'))

        Application.sanitycheck(self)
