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
All required to provide details of build environment
and allow for reproducable builds

:author: Shahzeb Siddiqui (Pfizer)
"""
import subprocess
import os
import sys
import urllib2
import easybuild.tools.options as eboptions

from vsc.utils import fancylogger
from easybuild.tools.config import build_option, get_module_naming_scheme, singularity_path
from easybuild.tools.filetools import change_dir, which, write_file
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.testing import  session_state
_log = fancylogger.getLogger('tools.package')  # pylint: disable=C0103


def check_bootstrap(options):
    """ sanity check for --singularity-bootstrap option"""
    if options.singularity_bootstrap:
    	bootstrap_opts = options.singularity_bootstrap
	bootstrap_list = bootstrap_opts.split(":")
    	# checking format of --singularity-bootstrap
    	if len(bootstrap_list) > 3 or len(bootstrap_list) <= 1:
		print """ Invalid Format for --singularity-bootstrap 

		  Must be one of the following

		  --singularity-bootstrap localimage:/path/to/image
		  --singularity-bootstrap shub:<image>:<tag>
		  --singularity-bootstrap docker:<image>:<tag>
		  """

		sys.exit(1)
    else:
     	raise EasyBuildError("must specify --singularity-bootstrap option")

    # first argument to --singularity-bootstrap is the bootstrap agent (localimage, shub, docker)
    bootstrap_type = bootstrap_list[0]

    # check bootstrap type value and ensure it is localimage, shub, docker
    if bootstrap_type != "localimage" and bootstrap_type != "shub" and bootstrap_type != "docker":
    	raise EasyBuildError("bootstrap type must be localimage, shub, or docker ")


    return bootstrap_type,bootstrap_list


def generate_singularity_recipe(ordered_ecs,options):
    """ main function to singularity recipe and containers"""

    image_name = build_option('imagename')
    image_format = build_option('imageformat')
    build_image = build_option('buildimage')
    sing_path = singularity_path()
    bootstrap_opts = ""

    # check if --singularitypath is valid path and a directory
    if os.path.exists(sing_path) and os.path.isdir(sing_path):
	singularity_writepath = singularity_path()
    else:
	msg = "Invalid path: " +  sing_path +  " please specify a valid directory path"
	print msg
	raise EasyBuildError(msg)

    bootstrap_type, bootstrap_list = check_bootstrap(options)

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
    if bootstrap_type == "localimage":
    	bootstrap_imagepath = bootstrap_list[1]
	if os.path.exists(bootstrap_imagepath):
		# get the extension of container image
		image_ext = os.path.splitext(bootstrap_imagepath)[1]
		if image_ext == ".img" or image_ext == ".simg":
    			_log.debug("Image Extension is OK")
		else:
			print "Invalid image extension %s, must be .img or .simg", image_ext
			raise EaasyBuildError("Invalid image extension %s must be .img or .simg", image_ext)
	else:
		print "Can't find image path ", bootstrap_imagepath
		raise EasyBuildError("Can't find image path %s", bootstrap_imagepath)

    # if option is shub or docker
    else:
	bootstrap_image = bootstrap_list[1]
        image_tag = "NONE"
    	# format --singularity-bootstrap shub:<image>:<tag>
        if len(bootstrap_list) == 3:
		image_tag = bootstrap_list[2]

    module_scheme = get_module_naming_scheme()

    # bootstrap from local image
    if bootstrap_type == "localimage":
	bootstrap_content = "Bootstrap: " + bootstrap_type + " \n"
	bootstrap_content += "From: " + bootstrap_imagepath + "\n" 
    # default bootstrap is shub or docker
    else:
	    bootstrap_content = "BootStrap: " + bootstrap_type + "\n" 

	    if image_tag == "NONE":
		    bootstrap_content += "From: " + bootstrap_image  + "\n"
	    else:
		    bootstrap_content += "From: " + bootstrap_image + ":" + image_tag  + "\n"

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
        if isinstance(osdeps[0],basestring):
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
    post_content += """exit
rm -rf /scratch/tmp/*
rm -rf /scratch/build
rm -rf /scratch/sources
rm -rf /scratch/ebfiles_repo
"""


    runscript_content = """
%runscript
eval "$@"
"""

    label_content = "\n%labels \n"

    # adding all the regions for writing the  Singularity definition file
    content = bootstrap_content + post_content + runscript_content + environment_content + label_content
    change_dir(singularity_writepath)
    write_file(def_file,content)

    print "Writing Singularity Definition File: %s" % os.path.join(singularity_writepath,def_file)
    _log.info("Writing Singularity Definition File: %s" % os.path.join(singularity_writepath,def_file))

    # if easybuild will build container
    if build_image:

        container_name = ""

	# if --imagename is specified
	if image_name != None:
		"""
		ext =  os.path.splitext(image_name)[1]
		if ext == ".img" or ext == ".simg":
			_log.debug("Extension for image is okay from --image-name")
		else:
			raise EasyBuildError("Invalid Extension for --imagename %s", ext)
		"""
		container_name = image_name
	else:
		# definition file Singularity.<app>-<version, container name <app>-<version>.<img|simg>
		pos = def_file.find('.')
		container_name = def_file[pos+1:]

	#squash image format
	if image_format == "squashfs":
		container_name += ".simg"
		if os.path.exists(container_name):
			errmsg = "Image already exist at " + os.path.join(singularity_writepath,container_name)
			print errmsg
			raise EasyBuildError(errmsg)

		os.system("sudo singularity build " + container_name + " " + def_file)

	# ext3 image format, creating as writable container
	elif image_format == "ext3":
	    	container_name += ".img"

		if os.path.exists(container_name):
			errmsg = "Image already exist at " + os.path.join(singularity_writepath,container_name)
			print errmsg
			raise EasyBuildError(errmsg)

		os.system("sudo singularity build --writable " + container_name + " " + def_file)

	# sandbox image format, creates as a directory but acts like a container
	elif image_format == "sandbox":

		if os.path.exists(container_name):
			errmsg = "Image already exist at " + os.path.join(singularity_writepath,container_name)
			print errmsg
			raise EasyBuildError(errmsg)

	     	os.system("sudo singularity build --sandbox " + container_name + " " + def_file)


def check_singularity(ordered_ecs,options):
    """
    Return build statistics for this build
    """

    path_to_singularity_cmd = which("singularity")
    singularity_version = 0
    if path_to_singularity_cmd:
	print "Singularity tool found at %s" % path_to_singularity_cmd
	ret = subprocess.Popen("singularity --version", shell=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	# singularity version format for 2.3.1 and higher is x.y-dist
	singularity_version = ret.communicate()[0].split("-")[0]
    else:
	print "Singularity not found in your system."
 	raise EasyBuildError("Singularity not found in your system")


    if float(singularity_version) < 2.4:
    	raise EasyBuildError("Please upgrade singularity instance to version 2.4 or higher")

    else:
	print "Singularity version is 2.4 or higher ... OK"
	print "Singularity Version is " + singularity_version

    generate_singularity_recipe(ordered_ecs, options)
