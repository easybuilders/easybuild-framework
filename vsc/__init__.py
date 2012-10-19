##
# Copyright 2011-2012 Jens Timmerman
#
# This file is part of VSC-tools,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc)
# and the VSC (Flemish Supercomputer Centre - https://vscentrum.be/nl/en).
#
# http://github.com/hpcugent/VSC-tools
#
# VSC-tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with VSC-tools. If not, see <http://www.gnu.org/licenses/>.
##
"""
Initialize vsc package.
the vsc namespace is used in different folders allong the system
so explicitly declare this is also the vsc namespace
"""
import pkg_resources
pkg_resources.declare_namespace(__name__)
