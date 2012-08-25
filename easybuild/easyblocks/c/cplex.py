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
EasyBuild support for CPLEX, implemented as an easyblock
"""
import glob
import os
import stat

import easybuild.tools.environment as env
from easybuild.easyblocks.binary import EB_Binary
from easybuild.tools.filetools import run_cmd_qa


class EB_CPLEX(EB_Binary):
    """
    Support for installing CPLEX.
    Version 12.2 has a self-extracting package with a Java installer
    """

    def __init__(self, *args, **kwargs):
        """Initialize CPLEX-specific variables."""

        EB_Binary.__init__(self, *args, **kwargs)
        self.bindir = None

    def make_install(self):
        """CPLEX has an interactive installer, so use Q&A"""

        tmpdir = os.path.join(self.builddir, 'tmp')
        try:
            os.chdir(self.builddir)
            os.makedirs(tmpdir)

        except OSError, err:
            self.log.exception("Failed to prepare for installation: %s" % err)

        env.set('IATEMPDIR', tmpdir)
        dst = os.path.join(self.builddir, self.src[0]['name'])

        # Run the source
        cmd = "%s -i console" % dst

        qanda = {
                 "PRESS <ENTER> TO CONTINUE:":"",
                 'Press Enter to continue viewing the license agreement, or enter' \
                 ' "1" to accept the agreement, "2" to decline it, "3" to print it,' \
                 ' or "99" to go back to the previous screen.:':'1',
                 'ENTER AN ABSOLUTE PATH, OR PRESS <ENTER> TO ACCEPT THE DEFAULT :':self.installdir,
                 'IS THIS CORRECT? (Y/N):':'y',
                 'PRESS <ENTER> TO INSTALL:':"",
                 "PRESS <ENTER> TO EXIT THE INSTALLER:":"",
                 "CHOOSE LOCALE BY NUMBER:":"",
                 "Choose Instance Management Option:":""
                 }
        noqanda = [r'Installing\.\.\..*\n.*------.*\n\n.*============.*\n.*$']

        run_cmd_qa(cmd, qanda, no_qa=noqanda, log_all=True, simple=True)

        try:
            os.chmod(self.installdir, stat.S_IRWXU | stat.S_IXOTH | stat.S_IXGRP | stat.S_IROTH | stat.S_IRGRP)
        except OSError, err:
            self.log.exception("Can't set permissions on %s: %s" % (self.installdir, err))

        # determine bin dir
        os.chdir(self.installdir)
        binglob = 'cplex/bin/x86-64*'
        bins = glob.glob(binglob)

        if len(bins) == 1:
            self.bindir = bins[0]
        elif len(bins) > 1:
            self.log.error("More than one possible path for bin found: %s" % bins)
        else:
            self.log.error("No bins found using %s in %s" % (binglob, self.installdir))

    def make_module_extra(self):
        """Add installdir to path and set CPLEX_HOME"""

        txt = EB_Binary.make_module_extra(self)
        txt += self.moduleGenerator.prependPaths("PATH", [self.bindir])
        txt += self.moduleGenerator.setEnvironment("CPLEX_HOME", "$root/cplex")
        self.log.debug("make_module_extra added %s" % txt)
        return txt

    def sanitycheck(self):
        """Custom sanity check for CPLEX"""

        if not self.getcfg('sanityCheckPaths'):
            self.setcfg('sanityCheckPaths', {'files':["%s/%s" % (self.bindir, x) for x in
                                                       ["convert", "cplex", "cplexamp"]],
                                            'dirs':[]
                                           })

            self.log.info("Customized sanity check paths: %s" % self.getcfg('sanityCheckPaths'))

        EB_Binary.sanitycheck(self)
