# This file is an EasyBuild recipy as per https://github.com/hpcugent/easybuild
#
# Copyright:: Copyright (c) 2012 University of Luxembourg / LCSB
# Author::    Cedric Laczny <cedric.laczny@uni.lu>, Fotis Georgatos <fotis.georgatos@uni.lu>
# License::   MIT/GPL
# File::      $File$ 
# Date::      $Date$
"""
EasyBuild support for building and installing Bowtie2, implemented as an easyblock
"""

import os
import shutil

from easybuild.easyblocks.generic.configuremake import ConfigureMake


class EB_Bowtie2(ConfigureMake):
    """
    Support for building bowtie2 (ifast and sensitive read alignment)
    - create Make.UNKNOWN
    - build with make and install 
    """

    def configure_step(self):
        """
        Empty function as bowtie2 comes with _no_ configure script
        """
        pass

    def install_step(self):
        """
        Install by copying files to install dir
        """
        srcdir = self.cfg['start_dir']
        destdir = os.path.join(self.installdir, 'bin')
        srcfile = None
        try:
            os.makedirs(destdir)
            for filename in ["bowtie2", "bowtie2-align", "bowtie2-build", "bowtie2-inspect"]:
                srcfile = os.path.join(srcdir, filename)
                shutil.copy2(srcfile, destdir)
        except OSError, err:
            self.log.error("Copying %s to installation dir %s failed: %s" % (srcfile, destdir, err))

    def sanity_check_step(self):
        """Custom sanity check for Bowtie2."""

        custom_paths = {
                        'files': ['bin/bowtie2', 'bin/bowtie2-align', 'bin/bowtie2-build', 'bin/bowtie2-inspect' ],
                        'dirs': ['.']
                       }

        super(EB_Bowtie2, self).sanity_check_step(custom_paths=custom_paths)

