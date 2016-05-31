##
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
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
Toolchain fft module, provides abstract class for FFT libraries.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.toolchain.toolchain import Toolchain


class Fft(Toolchain):
    """General FFT-like class
        To provide FFT tools
    """

    FFT_MODULE_NAME = None
    FFT_LIB = None
    FFT_LIB_GROUP = False
    FFT_LIB_STATIC = False
    FFT_LIB_DIR = ['lib']
    FFT_INCLUDE_DIR = ['include']

    def __init__(self, *args, **kwargs):
        Toolchain.base_init(self)

        super(Fft, self).__init__(*args, **kwargs)

    def _set_fft_variables(self):
        """Set FFT variables"""
        fft_libs = self.variables.nappend('LIBFFT', self.FFT_LIB)
        self.variables.add_begin_end_linkerflags(fft_libs, toggle_startstopgroup=self.FFT_LIB_GROUP,
                                                 toggle_staticdynamic=self.FFT_LIB_STATIC)

        self.variables.join('FFT_STATIC_LIBS', 'LIBFFT')
        for root in self.get_software_root(self.FFT_MODULE_NAME):
            self.variables.append_exists('FFT_LIB_DIR', root, self.FFT_LIB_DIR)
            self.variables.append_exists('FFT_INC_DIR', root, self.FFT_INCLUDE_DIR)

        self._add_dependency_variables(self.FFT_MODULE_NAME)

    def set_variables(self):
        """Set the variables"""
        ## TODO is link order fully preserved with this order ?
        self._set_fft_variables()

        self.log.debug('set_variables: FFT variables %s' % self.variables)

        super(Fft, self).set_variables()
