# Copyright 2014-2017 Ghent University
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
Support for generating Singularity definition files and creating Singularity images

:author: Shahzeb Siddiqui (Pfizer)
:author: Kenneth Hoste (HPC-UGent)
"""
import os
from distutils.version import LooseVersion
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import build_option, container_path, get_module_naming_scheme
from easybuild.tools.filetools import change_dir, which, write_file
from easybuild.tools.run import run_cmd


CONT_TYPE_DOCKER = 'docker'
CONT_TYPE_SINGULARITY = 'singularity'

DOCKER = 'docker'
LOCALIMAGE = 'localimage'
SHUB = 'shub'
SINGULARITY_BOOTSTRAP_TYPES = [DOCKER, LOCALIMAGE, SHUB]


_log = fancylogger.getLogger('tools.containers')  # pylint: disable=C0103


def check_bootstrap(singularity_bootstrap):
    """ sanity check for --singularity-bootstrap option"""
    if singularity_bootstrap:
        bootstrap_specs = singularity_bootstrap.split(':')
        # checking format of --singularity-bootstrap
        if len(bootstrap_specs) > 3 or len(bootstrap_specs) <= 1:
            error_msg = '\n'.join([
                "Invalid Format for --singularity-bootstrap, must be one of the following:",
                '',
                "--singularity-bootstrap localimage:/path/to/image",
                "--singularity-bootstrap shub:<image>:<tag>",
                "--singularity-bootstrap docker:<image>:<tag>",
            ])
            raise EasyBuildError(error_msg)
    else:
        raise EasyBuildError("--container-bootstrap must be specified")

    # first argument to --singularity-bootstrap is the bootstrap agent (localimage, shub, docker)
    bootstrap_type = bootstrap_specs[0]

    # check bootstrap type value and ensure it is localimage, shub, docker
    if bootstrap_type not in SINGULARITY_BOOTSTRAP_TYPES:
        raise EasyBuildError("bootstrap type must be one of %s" % ', '.join(SINGULARITY_BOOTSTRAP_TYPES))

    return bootstrap_type, bootstrap_specs


def generate_singularity_recipe(ordered_ecs, options):
    """ main function to singularity recipe and containers"""

    cont_path = container_path()

    # check if --containerpath is valid path and a directory
    if os.path.isdir(cont_path):
        _log.info("Path for container recipes & images: %s", cont_path)
    else:
        raise EasyBuildError("Location for container recipes & images is a non-existing directory: %s" % cont_path)

    bootstrap_type, bootstrap_list = check_bootstrap(options.container_bootstrap)

    # extracting application name,version, version suffix, toolchain name, toolchain version from
    # easyconfig class

    appname = ordered_ecs[0]['ec']['name']
    appver = ordered_ecs[0]['ec']['version']
    appversuffix = ordered_ecs[0]['ec']['versionsuffix']

    tcname = ordered_ecs[0]['ec']['toolchain']['name']
    tcver = ordered_ecs[0]['ec']['toolchain']['version']

    osdeps = ordered_ecs[0]['ec']['osdependencies']

    modulepath = ""


    # with localimage it only takes 2 arguments. --singularity-bootstrap localimage:/path/to/image
    # checking if path to image is valid and verify image extension is".img or .simg"
    if bootstrap_type == LOCALIMAGE:
        bootstrap_imagepath = bootstrap_list[1]
        if os.path.exists(bootstrap_imagepath):
            # get the extension of container image
            image_ext = os.path.splitext(bootstrap_imagepath)[1]
            if image_ext == '.img' or image_ext == '.simg':
                _log.debug("Image Extension is OK")
            else:
                raise EaasyBuildError("Invalid image extension %s must be .img or .simg", image_ext)
        else:
            raise EasyBuildError("Singularity base image at specified path does not exist: %s", bootstrap_imagepath)

    # if option is shub or docker
    else:
        bootstrap_image = bootstrap_list[1]
        image_tag = None
        # format --singularity-bootstrap shub:<image>:<tag>
        if len(bootstrap_list) == 3:
            image_tag = bootstrap_list[2]

    module_scheme = get_module_naming_scheme()

    # bootstrap from local image
    if bootstrap_type == LOCALIMAGE:
        bootstrap_content = 'Bootstrap: ' + bootstrap_type + '\n'
        bootstrap_content += 'From: ' + bootstrap_imagepath + '\n'
    # default bootstrap is shub or docker
    else:
            bootstrap_content = 'BootStrap: ' + bootstrap_type + '\n' 

            if image_tag is None:
                bootstrap_content += 'From: ' + bootstrap_image  + '\n'
            else:
                bootstrap_content += 'From: ' + bootstrap_image + ':' + image_tag + '\n'

    if module_scheme == "HierarchicalMNS":
        modulepath = "/app/modules/all/Core"
    else:
        modulepath = "/app/modules/all/"

    post_content = """
%post
"""
    # if there is osdependencies in easyconfig then add them to Singularity recipe
    if len(osdeps) > 0:
        # format: osdependencies = ['libibverbs-dev', 'libibverbs-devel', 'rdma-core-devel']
        if isinstance(osdeps[0], basestring):
            for os_package in osdeps:
                post_content += "yum install -y " + os_package + " || true \n"
        # format: osdependencies = [('libibverbs-dev', 'libibverbs-devel', 'rdma-core-devel')]
        else:
            for os_package in osdeps[0]:
                post_content += "yum install -y " + os_package + " || true \n"

   # upgrade easybuild package automatically in all Singularity builds
    post_content += "pip install -U easybuild \n"
    post_content += "su - easybuild \n"

    environment_content = """
%environment
source /etc/profile
"""
    # check if toolchain is specified, that affects how to invoke eb and module load is affected based on module naming scheme
    if tcname != "dummy":
        # name of easyconfig to build
        easyconfig  = appname + "-" + appver + "-" + tcname + "-" + tcver +  appversuffix + ".eb"
        # name of Singularity defintiion file
        def_file  = "Singularity." + appname + "-" + appver + "-" + tcname + "-" + tcver +  appversuffix

        ebfile = os.path.splitext(easyconfig)[0] + ".eb"
        post_content += "eb " + ebfile  + " --robot --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp  --module-naming-scheme=" + module_scheme + "\n"

        # This would be an example like running eb R-3.3.1-intel2017a.eb --module-naming-scheme=HierarchicalMNS. In HMNS you need to load intel/2017a first then R/3.3.1
        if module_scheme == "HierarchicalMNS":
                environment_content += "module use " + modulepath + "\n"
                environment_content +=  "module load " + os.path.join(tcname,tcver) + "\n"
                environment_content +=  "module load " + os.path.join(appname,appver+appversuffix) + "\n"
        # This would be an example of running eb R-3.3.1-intel2017a.eb with default naming scheme, that will result in only one module load and moduletree will be different
        else:

                environment_content += "module use " +  modulepath + "\n" 
                environment_content += "module load " + os.path.join(appname,appver+"-"+tcname+"-"+tcver+appversuffix) + "\n"
    # for dummy toolchain module load will be same for EasybuildMNS and HierarchicalMNS but moduletree will not
    else:
        # this would be an example like eb bzip2-1.0.6.eb. Also works with version suffix easyconfigs

        # name of easyconfig to build
        easyconfig  = appname + "-" + appver + appversuffix + ".eb"

        # name of Singularity defintiion file
        def_file  = "Singularity." + appname + "-" + appver + appversuffix

        ebfile = os.path.splitext(easyconfig)[0] + ".eb"
        post_content += "eb " + ebfile + " --robot --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp  --module-naming-scheme=" + module_scheme + "\n"

        environment_content += "module use " +  modulepath + "\n"
        environment_content +=  "module load " + os.path.join(appname,appver+appversuffix) + "\n"


    # cleaning up directories in container after build
    post_content += '\n'.join([
        'exit',
        "rm -rf /scratch/tmp/* /scratch/build /scratch/sources /scratch/ebfiles_repo",
    ])

    runscript_content = '\n'.join([
        "%runscript",
        'eval "$@"',
    ])

    label_content = "\n%labels \n"

    # adding all the regions for writing the  Singularity definition file
    content = bootstrap_content + post_content + runscript_content + environment_content + label_content
    def_path = os.path.join(cont_path, def_file)
    write_file(def_path, content)

    print_msg("Singularity definition file created at %s" % def_path, log=_log)

    # also build container image, if requested (requires sudo!)
    if build_option('container_build_image'):

        # use --imagename if specified, otherwise derive based on filename of recipe
        cont_img = build_option('container_image_name')
        if cont_img is None:
            # definition file Singularity.<app>-<version, container name <app>-<version>.<img|simg>
            dot_idx = def_file.find('.')
            cont_img = def_file[dot_idx+1:]

        cont_img_cmd_opts = ''

        image_format = build_option('container_image_format')

        # squashfs image format (default for Singularity)
        if image_format in [None, CONT_IMAGE_FORMAT_SQUASHFS]:
            cont_img_path = os.path.join(cont_path, cont_img + '.simg')

        # ext3 image format, creating as writable container
        elif image_format == CONT_IMAGE_FORMAT_EXT3:
            cont_img_path = os.path.join(cont_path, cont_img + '.img')
            cont_img_cmd_opts = '--writeable'

        # sandbox image format, creates as a directory but acts like a container
        elif image_format == CONT_IMAGE_FORMAT_SANDBOX:
            cont_img_path = os.path.join(cont_path, cont_img)

        else:
            raise EasyBuildError("Unknown container image format specified for Singularity: %s" % image_format)

        if os.path.exists(cont_img_path):
            raise EasyBuildError("Container image already exists at " + cont_img_path)
        else:
            cont_img_cmd = "sudo singularity build %s --sandbox %s %s" % (cont_img_cmd_opts, cont_img_path, def_path)
            run_cmd(cont_img_cmd)
            print_msg("Singularity image created at %s" % cont_img_path, log=_log)


def check_singularity(ordered_ecs,options):
    """
    Return build statistics for this build
    """
    path_to_singularity_cmd = which('singularity')
    if path_to_singularity_cmd:
        print_msg("Singularity tool found at %s" % path_to_singularity_cmd)
        out, ec = run_cmd("singularity --version", simple=False)
        if ec:
            raise EasyBuildError("Failed to determine Singularity version: %s" % out)
        else:
            # singularity version format for 2.3.1 and higher is x.y-dist
            singularity_version = out.strip().split('-')[0]

    if build_option('container_build_image'):
        if not path_to_singularity_cmd:
            raise EasyBuildError("Singularity not found in your system")

        if LooseVersion(singularity_version) < LooseVersion('2.4'):
            raise EasyBuildError("Please upgrade singularity instance to version 2.4 or higher")
        else:
            print_msg("Singularity version '%s' is 2.4 or higher ... OK" % singularity_version)

    generate_singularity_recipe(ordered_ecs, options)
