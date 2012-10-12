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
EasyBuild support for installing the Intel MPI library, implemented as an easyblock
"""

import os
from distutils.version import LooseVersion

from easybuild.easyblocks.generic.intelbase import IntelBase
from easybuild.tools.filetools import run_cmd


class EB_impi(IntelBase):
    """
    Support for installing Intel MPI library
    """

    def install_step(self):
        """
        Actual installation
        - create silent cfg file
        - execute command
        """
        if LooseVersion(self.version) >= LooseVersion('4.0.1'):
            #impi starting from version 4.0.1.x uses standard installation procedure.
            super(EB_impi, self).install_step()
            return None
        else:
            #impi up until version 4.0.0.x uses custom installation procedure.
            silent = \
"""
[mpi]
INSTALLDIR=%(ins)s
LICENSEPATH=%(lic)s
INSTALLMODE=NONRPM
INSTALLUSER=NONROOT
UPDATE_LD_SO_CONF=NO
PROCEED_WITHOUT_PYTHON=yes
AUTOMOUNTED_CLUSTER=yes
EULA=accept
[mpi-rt]
INSTALLDIR=%(ins)s
LICENSEPATH=%(lic)s
INSTALLMODE=NONRPM
INSTALLUSER=NONROOT
UPDATE_LD_SO_CONF=NO
PROCEED_WITHOUT_PYTHON=yes
AUTOMOUNTED_CLUSTER=yes
EULA=accept

""" % {'lic':self.license, 'ins':self.installdir}

            # already in correct directory
            silentcfg = os.path.join(os.getcwd(), "silent.cfg")
            try:
                f = open(silentcfg, 'w')
                f.write(silent)
                f.close()
            except:
                self.log.exception("Writing silent cfg file %s failed." % silent)

            tmpdir = os.path.join(os.getcwd(), self.version, 'mytmpdir')
            try:
                os.makedirs(tmpdir)
            except:
                self.log.exception("Directory %s can't be created" % (tmpdir))

            cmd = "./install.sh --tmp-dir=%s --silent=%s" % (tmpdir, silentcfg)
            run_cmd(cmd, log_all=True, simple=True)

    def sanity_check_step(self):
        """Custom sanity check paths for IMPI."""

        suff = "64"
        if self.cfg['m32']:
            suff = ""

        custom_paths = {
                        'files': ["bin/mpi%s" % x for x in ["icc", "icpc", "ifort"]] +
                                 ["include%s/mpi%s.h" % (suff, x) for x in ["cxx", "f", "", "o", "of"]] +
                                 ["include%s/%s" % (suff, x) for x in ["i_malloc.h", "mpi_base.mod",
                                                                       "mpi_constants.mod", "mpi.mod",
                                                                       "mpi_sizeofs.mod"]] +
                                 ["lib%s/libmpi.so" % suff, "lib%s/libmpi.a" % suff],
                        'dirs': []
                       }

        super(EB_impi, self).sanity_check_step(custom_paths=custom_paths)

    def make_module_req_guess(self):
        """
        A dictionary of possible directories to look for
        """
        if self.cfg['m32']:
            return {
                    'PATH':['bin', 'bin/ia32', 'ia32/bin'],
                    'LD_LIBRARY_PATH':['lib', 'lib/ia32', 'ia32/lib'],
                   }
        else:
            return {
                    'PATH':['bin', 'bin/intel64', 'bin64'],
                    'LD_LIBRARY_PATH':['lib', 'lib/em64t', 'lib64'],
                   }

    def make_module_extra(self):
        """Overwritten from Application to add extra txt"""
        txt = super(EB_impi, self).make_module_extra()
        txt += "prepend-path\t%s\t\t%s\n" % ('INTEL_LICENSE_FILE', self.license)
        txt += "setenv\t%s\t\t$root\n" % ('I_MPI_ROOT')

        return txt
