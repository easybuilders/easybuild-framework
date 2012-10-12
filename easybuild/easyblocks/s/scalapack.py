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
EasyBuild support for building and installing ScaLAPACK, implemented as an easyblock
"""

import glob
import os
import shutil
from distutils.version import LooseVersion

import easybuild.tools.toolkit as toolchain
from easybuild.easyblocks.blacs import det_interface  #@UnresolvedImport
from easybuild.easyblocks.generic.configuremake import ConfigureMake
from easybuild.easyblocks.lapack import get_blas_lib  #@UnresolvedImport
from easybuild.tools.modules import get_software_root


class EB_ScaLAPACK(ConfigureMake):
    """
    Support for building and installing ScaLAPACK, both versions 1.x and 2.x
    """

    def configure_step(self):
        """Configure ScaLAPACK build by copying SLmake.inc.example to SLmake.inc and checking dependencies."""

        src = os.path.join(self.cfg['start_dir'], 'SLmake.inc.example')
        dest = os.path.join(self.cfg['start_dir'], 'SLmake.inc')

        if not os.path.isfile(src):
            self.log.error("Can't fin source file %s" % src)

        if os.path.exists(dest):
            self.log.error("Destination file %s exists" % dest)

        try:
            shutil.copy(src, dest)
        except OSError, err:
            self.log.error("Symlinking %s to % failed: %s" % (src, dest, err))

        self.loosever = LooseVersion(self.version)

        # make sure required dependencies are available
        deps = ["LAPACK"]
        # BLACS is only a dependency for ScaLAPACK versions prior to v2.0.0
        if self.loosever < LooseVersion("2.0.0"):
            deps.append("BLACS")
        for dep in deps:
            if not get_software_root(dep):
                self.log.error("Dependency %s not available/loaded." % dep)

    def build_step(self):
        """Build ScaLAPACK using make after setting make options."""

        # MPI compiler commands
        if os.getenv('MPICC') and os.getenv('MPIF77') and os.getenv('MPIF90'):
            mpicc = os.getenv('MPICC')
            mpif77 = os.getenv('MPIF77')
            mpif90 = os.getenv('MPIF90')
        elif self.toolchain.mpi_type() in [toolchain.OPENMPI, toolchain.MVAPICH2]:
            mpicc = 'mpicc'
            mpif77 = 'mpif77'
            mpif90 = 'mpif90'
        else:
            self.log.error("Don't know which compiler commands to use.")

        # set BLAS and LAPACK libs
        extra_makeopts = [
                          'BLASLIB="%s -lpthread"' % get_blas_lib(self.log),
                          'LAPACKLIB=%s/lib/liblapack.a' % get_software_root('LAPACK')
                         ]

        # build procedure changed in v2.0.0
        if self.loosever < LooseVersion("2.0.0"):

            blacs = get_software_root('BLACS')

            # determine interface
            interface = det_interface(self.log, os.path.join(blacs, 'bin'))

            # set build and BLACS dir correctly
            extra_makeopts.append('home=%s BLACSdir=%s' % (self.cfg['start_dir'], blacs))

            # set BLACS libs correctly
            for (var, lib) in [
                               ('BLACSFINIT', "F77init"),
                               ('BLACSCINIT', "Cinit"),
                               ('BLACSLIB', "")
                              ]:
                extra_makeopts.append('%s=%s/lib/libblacs%s.a' % (var, blacs, lib))

            # set compilers and options
            noopt = ''
            if self.toolchain.opts['noopt']:
                noopt += " -O0"
            if self.toolchain.opts['pic']:
                noopt += " -fPIC"
            extra_makeopts += [
                               'F77="%s"' % mpif77,
                               'CC="%s"' % mpicc,
                               'NOOPT="%s"' % noopt,
                               'CCFLAGS="-O3 %s"' % os.getenv('CFLAGS')
                              ]

            # set interface
            extra_makeopts.append("CDEFS='-D%s -DNO_IEEE $(USEMPI)'" % interface)

        else:

            # determine interface
            if self.toolchain.mpi_type() in [toolchain.OPENMPI, toolchain.MVAPICH2]:
                interface = 'Add_'
            else:
                self.log.error("Don't know which interface to pick for the MPI library being used.")

            # set compilers and options
            extra_makeopts += [
                               'FC="%s"' % mpif90,
                               'CC="%s"' % mpicc
                              ]

            # set interface
            extra_makeopts.append('CDEFS="-D%s"' % interface)

        # update make opts, and build_step
        self.cfg.update('makeopts', ' '.join(extra_makeopts))

        super(EB_ScaLAPACK, self).build_step()

    def install_step(self):
        """Install by copying files to install dir."""

        # include files and libraries
        for (srcdir, destdir, ext) in [
                                       ("SRC", "include", ".h"), # include files
                                       ("", "lib", ".a"), # libraries
                                       ]:

            src = os.path.join(self.cfg['start_dir'], srcdir)
            dest = os.path.join(self.installdir, destdir)

            try:
                os.makedirs(dest)
                os.chdir(src)

                for lib in glob.glob('*%s' % ext):

                    # copy file
                    shutil.copy2(os.path.join(src, lib), dest)

                    self.log.debug("Copied %s to %s" % (lib, dest))

            except OSError, err:
                self.log.error("Copying %s/*.%s to installation dir %s failed: %s" % (src, ext, dest, err))

    def sanity_check_step(self):
        """Custom sanity check for ScaLAPACK."""

        custom_paths = {
                        'files': ["lib/libscalapack.a"],
                        'dirs': []
                       }

        super(EB_ScaLAPACK, self).sanity_check_step(custom_paths=custom_paths)
