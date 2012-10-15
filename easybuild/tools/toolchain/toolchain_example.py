##
# Copyright 2012 Stijn De Weirdt
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
from easybuild.tools.toolchain import search_toolchain

if __name__ == '__main__':
    from vsc.fancylogger import setLogLevelDebug
    setLogLevelDebug()

    tc_class, all_tcs = search_toolchain('goalf')

    print ",".join([x.__name__ for x in all_tcs])

    tc = tc_class(version='1.0.0')
    tc.options['cstd'] = 'CVERYVERYSPECIAL'
    tc.options['pic'] = True
    tc.set_variables()
    tc.generate_vars()
    tc.show_variables(offset=" "*4, verbose=True)


