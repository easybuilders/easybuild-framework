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
import os

from vsc.utils import fancylogger

from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option, container_path
from easybuild.tools.containers.utils import check_tool
from easybuild.tools.filetools import write_file


class ContainerGenerator(object):
    """
    The parent class for concrete container recipe and image generator.
    Subclasses have to provide at least template resolution and image creation logic.
    """

    TOOLS = {}

    RECIPE_FILE_NAME = None

    def __init__(self, easyconfigs):
        self.container_base = build_option('container_base')
        self.container_build_image = build_option('container_build_image')
        self.container_path = container_path()
        self.easyconfigs = easyconfigs
        self.image_format = build_option('container_image_format')
        self.img_name = build_option('container_image_name')
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.mns = ActiveMNS()
        self.tmpdir = build_option('container_tmpdir')

    def generate(self):
        """
        The entry point for container recipe and image generation.
        It starts by validating the needed tools are available using TOOLS class attribute.
        If the validation passes, it will generate the container recipe, and optionally build out of it the container.
        """
        self.validate()
        recipe_path = self.generate_recipe()
        if self.container_build_image:
            self.build_image(recipe_path)

    def validate_tools(self):
        """
        A method that gets called as part of image generation
        that uses TOOLS class attribute to check for the existence
        of the needed binary/tools on the host system.
        """
        for tool_name, tool_version in self.TOOLS.items():
            if not check_tool(tool_name, tool_version):
                err_msg = "".join([
                    tool_name,
                    " with version {0} or higher".format(tool_version) if tool_version else "",
                    " not found on your system.",
                ])
                raise EasyBuildError(err_msg)

    def validate(self):
        """
        A method that should contain all the validation logic
        for both container recipe (Singularity, Dockerfile, ...) and
        image generation.
        """
        if self.container_build_image:
            self.validate_tools()

    def resolve_template(self):
        """
        This method should be implemented by the concrete subclass to return
        the correct template for the container recipe.
        """
        raise NotImplementedError

    def resolve_template_data(self):
        """
        This method should be implemented by the concrete subclass to return
        a dictionary of template data for container recipe generation.
        """
        return {}

    def generate_recipe(self):
        """
        This method will make use of resolve_template and resolve_template_data methods
        in order to generate the container recipe.
        """
        template = self.resolve_template()
        data = self.resolve_template_data()

        if self.img_name:
            file_label = os.path.splitext(self.img_name)[0]
        else:
            file_label = data['mod_names'].split(' ')[0].replace('/', '-')

        recipe_path = os.path.join(self.container_path, "%s.%s" % (self.RECIPE_FILE_NAME, file_label))

        if os.path.exists(recipe_path):
            if build_option('force'):
                print_msg("WARNING: overwriting existing container recipe at %s due to --force" % recipe_path)
            else:
                raise EasyBuildError("Container recipe at %s already exists, not overwriting it without --force",
                                     recipe_path)

        recipe_content = template % data
        write_file(recipe_path, recipe_content)
        print_msg("%s definition file created at %s" % (self.RECIPE_FILE_NAME, recipe_path), log=self.log)

        return recipe_path

    def build_image(self, recipe_path):
        """
        This method will be used on the concrete subclass to build the image using
        The path of the container recipe.
        """
        raise NotImplementedError
