#
# Copyright 2019-2021 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
#
import sys

# all functionality provided by the py2 and py3 modules is made available via the easybuild.tools.py2vs3 namespace
if sys.version_info[0] >= 3:
    from easybuild.tools.py2vs3.py3 import *  # noqa
else:
    from easybuild.tools.py2vs3.py2 import *  # noqa


# based on six's 'with_metaclass' function
# see also https://stackoverflow.com/questions/18513821/python-metaclass-understanding-the-with-metaclass
def create_base_metaclass(base_class_name, metaclass, *bases):
    """Create new class with specified metaclass based on specified base class(es)."""
    return metaclass(base_class_name, bases, {})
