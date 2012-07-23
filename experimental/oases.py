# This file is an EasyBuild recipy as per https://github.com/hpcugent/easybuild
#
# Copyright:: Copyright (c) 2012 University of Luxembourg / LCSB
# Author::    Cedric Laczny <cedric.laczny@uni.lu>, Fotis Georgatos <fotis.georgatos@uni.lu>
# License::   MIT/GPL
# File::      $File$ 
# Date::      $Date$


##
# Copyright 2009-2012 Stijn De Weirdt, Dries Verdegem, Kenneth Hoste, Pieter De Baets, Jens Timmerman
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
import os
import shutil
import fileinput
import re
import sys 
from easybuild.framework.application import Application
from easybuild.tools.filetools import patch_perl_script_autoflush, run_cmd, run_cmd_qa
from easybuild.easyblocks.n.netcdf import set_netcdf_env_vars, get_netcdf_module_set_cmds

class Oases(Application):
    """
    Support for building oases (De novo transcriptome assembler for very short reads)
    """

    def configure(self):
        """
        Check if system is suitable apparently via "make check"
        """

    def make(self):
	"""
	Needs to get the path of the build-dir of velvet -> requires headers -> possible?
	"""
        builddep = self.getcfg('builddependencies')
	# assert that it only has ONE builddep specified
	assert len(builddep) == 1

        srcdir = self.getcfg('startfrom')

	velvet = builddep[0]['name'] 
	velvetver = builddep[0]['version']

	cmd = 'make VELVET_DIR="' + os.path.join(srcdir, "..", velvet + "_" + velvetver) + '"' 
	run_cmd(cmd, log_all=True, simple=True)

    def make_install(self):
        """
        Install by copying files to install dir
        """
        srcdir = self.getcfg('startfrom')
        destdir = os.path.join(self.installdir, 'bin')
        srcfile = None
	# Get executable files: for i in $(find . -maxdepth 1 -type f -perm +111 -print | sed -e 's/\.\///g' | awk '{print "\""$0"\""}' | grep -vE "\.sh|\.html"); do echo -ne "$i, "; done && echo
        try:
            os.makedirs(destdir)
            for filename in ["oases"]:
                srcfile = os.path.join(srcdir, filename)
                shutil.copy2(srcfile, destdir)
        except OSError, err:
            self.log.exception("Copying %s to installation dir %s failed: %s" % (srcfile, destdir, err))

