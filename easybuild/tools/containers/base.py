# #
# Copyright 2009-2018 Ghent University
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
# #
"""
:author: Mohamed Abidi (Bright Computing)
"""
from vsc.utils import fancylogger

import os
from easybuild.tools.filetools import write_file
from easybuild.tools.config import build_option, container_path
from easybuild.tools.build_log import EasyBuildError, print_msg
from .utils import check_tool


_log = fancylogger.getLogger('tools.containers.singularity')  # pylint: disable=C0103


class ContainerGenerator(object):

    TOOLS = {}

    RECIPE_FILE_NAME = None

    def __init__(self, easyconfigs):
        self._easyconfigs = easyconfigs
        self._img_name = build_option('container_image_name')
        self._force = build_option('force')
        self._image_format = build_option('container_image_format')
        self._tmpdir = build_option('container_tmpdir')
        self._container_build_image = build_option('container_build_image')
        self._container_base = build_option('container_base')
        self._container_path = container_path()

    def generate(self):
        self.validate()
        recipe_path = self.generate_recipe()
        if self._container_build_image:
            self.build_image(recipe_path)

    def validate(self):
        if not self._container_build_image:
            return
        for tool_name, tool_version in self.TOOLS.items():
            if not check_tool(tool_name, tool_version):
                raise EasyBuildError("{0!r} not found on your system.".format(tool_name,))

    def resolve_template(self):
        raise NotImplementedError

    def resolve_template_data(self):
        return {}

    def _write_recipe(self, template, data):

        if self._img_name:
            file_label = os.path.splitext(self._img_name)[0]
        else:
            file_label = data['mod_names'].split(' ')[0].replace('/', '-')

        recipe_path = os.path.join(self._container_path, "%s.%s" % (self.RECIPE_FILE_NAME, file_label))

        if os.path.exists(recipe_path):
            if self._force:
                print_msg("WARNING: overwriting existing container recipe at %s due to --force" % recipe_path)
            else:
                raise EasyBuildError("Container recipe at %s already exists, not overwriting it without --force", recipe_path)

        recipe_content = template % data
        write_file(recipe_path, recipe_content)
        print_msg("%s definition file created at %s" % (self.RECIPE_FILE_NAME, recipe_path), log=_log)

        return recipe_path

    def generate_recipe(self):
        tmpl = self.resolve_template()
        data = self.resolve_template_data()
        return self._write_recipe(tmpl, data)

    def build_image(self, recipe_path):
        raise NotImplementedError
