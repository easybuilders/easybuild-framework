# This file is an EasyBuild recipy as per https://github.com/hpcugent/easybuild
#
# Copyright:: Copyright (c) 2012 University of Luxembourg / LCSB
# Author::    Cedric Laczny <cedric.laczny@uni.lu>, Fotis Georgatos <fotis.georgatos@uni.lu>
# License::   MIT/GPL
# File::      $File$ 
# Date::      $Date$
"""
Easybuild support for building SOAPdenovo
"""

import os
import shutil

from easybuild.easyblocks.generic.configuremake import ConfigureMake


class EB_SOAPdenovo(ConfigureMake):
    """
    Support for building SOAPdenovo.
    """

    def __init__(self, *args, **kwargs):
        """Define lists of files to install."""
        super(EB_SOAPdenovo, self).__init__(*args, **kwargs)

        self.bin_suffixes = ["31mer", "63mer", "127mer"]

    def configure_step(self):
        """
	    Skip the configure as not part of this build process
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
            for suff in self.bin_suffixes:
                srcfile = os.path.join(srcdir, "bin", "SOAPdenovo-%s" % suff)
                shutil.copy2(srcfile, destdir)
        except OSError, err:
            self.log.error("Copying %s to installation dir %s failed: %s" % (srcfile, destdir, err))

    def sanity_check_step(self):
        """Custom sanity check for SOAPdenovo."""

        custom_paths = {
                        'files': ['bin/SOAPdenovo-%s' % x for x in self.bin_suffixes],
                        'dirs': []
                       }

        super(EB_SOAPdenovo, self).sanity_check_step(custom_paths=custom_paths)
