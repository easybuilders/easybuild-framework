# Copyright 2022-2025 Ghent University
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
"""
Support for generating Apptainer container recipes and creating container images

:author: Kenneth Hoste (HPC-UGent)
"""
import os
import re

from easybuild.tools.build_log import EasyBuildError, EasyBuildExit, print_msg
from easybuild.tools.containers.singularity import SingularityContainer
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX
from easybuild.tools.config import CONT_IMAGE_FORMAT_SIF, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import build_option, container_path
from easybuild.tools.filetools import remove_file, which
from easybuild.tools.run import run_shell_cmd


class ApptainerContainer(SingularityContainer):

    TOOLS = {'apptainer': '1.0', 'sudo': None}

    RECIPE_FILE_NAME = 'Apptainer'

    @staticmethod
    def apptainer_version():
        """Get Apptainer version."""
        version_cmd = "apptainer --version"
        res = run_shell_cmd(version_cmd, hidden=True, in_dry_run=True)
        if res.exit_code != EasyBuildExit.SUCCESS:
            raise EasyBuildError(f"Error running '{version_cmd}': {res.output}")

        regex_res = re.search(r"\d+\.\d+(\.\d+)?", res.output.strip())
        if not regex_res:
            raise EasyBuildError(f"Error parsing Apptainer version: {res.output}")

        return regex_res.group(0)

    def build_image(self, recipe_path):
        """Build container image by calling out to 'sudo apptainer build'."""

        cont_path = container_path()
        def_file = os.path.basename(recipe_path)

        # use --imagename if specified, otherwise derive based on filename of recipe
        img_name = self.img_name
        if img_name is None:
            # definition file Apptainer.<app>-<version, container name <app>-<version>.<img|simg>
            img_name = def_file.split('.', 1)[1]

        cmd_opts = ''

        image_format = self.image_format

        # singularity image format (default for Apptainer)
        if image_format in [None, CONT_IMAGE_FORMAT_SQUASHFS, CONT_IMAGE_FORMAT_SIF]:
            img_path = os.path.join(cont_path, img_name + '.sif')

        # ext3 image format, creating as writable container
        elif image_format == CONT_IMAGE_FORMAT_EXT3:
            raise EasyBuildError("ext3 image format is not supported with Apptainer")

        # sandbox image format, creates as a directory but acts like a container
        elif image_format == CONT_IMAGE_FORMAT_SANDBOX:
            img_path = os.path.join(cont_path, img_name)
            cmd_opts = '--sandbox'

        else:
            raise EasyBuildError("Unknown container image format specified for Apptainer: %s" % image_format)

        if os.path.exists(img_path):
            if build_option('force'):
                print_msg("WARNING: overwriting existing container image at %s due to --force" % img_path)
                remove_file(img_path)
            else:
                raise EasyBuildError("Container image already exists at %s, not overwriting it without --force",
                                     img_path)

        # resolve full path to 'apptainer' binary, since it may not be available via $PATH under sudo...
        apptainer = which('apptainer')
        cmd_env = ''

        apptainer_tmpdir = self.tmpdir
        if apptainer_tmpdir:
            cmd_env += 'APPTAINER_TMPDIR=%s' % apptainer_tmpdir

        cmd = ' '.join(['sudo', cmd_env, apptainer, 'build', cmd_opts, img_path, recipe_path])
        print_msg("Running '%s', you may need to enter your 'sudo' password..." % cmd)
        run_shell_cmd(cmd, stream_output=True)
        print_msg("Apptainer image created at %s" % img_path, log=self.log)
