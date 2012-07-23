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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild. If not, see <http://www.gnu.org/licenses/>.
##
import os
import shutil
from easybuild.framework.application import Application

class Bwa(Application):
    """
    Support for building bwa (ifast and sensitive read alignment)
    - create Make.UNKNOWN
    - build with make and install
    """

    def configure(self):
        """
	Empty function as bwa comes with _no_ configure script
	"""

    def make_install(self):
        """
	Install by copying files to install dir
	"""
        srcdir = self.getcfg('startfrom')
        destdir = os.path.join(self.installdir, 'bin')
        srcfile = None
        try:
            os.makedirs(destdir)
            for filename in ["bwa", "qualfa2fq.pl", "solid2fastq.pl", "xa2multi.pl"]:
                srcfile = os.path.join(srcdir, filename)
                shutil.copy2(srcfile, destdir)
        except OSError, err:
            self.log.exception("Copying %s to installation dir %s failed: %s" % (srcfile, destdir, err))

