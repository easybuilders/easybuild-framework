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
import easybuild.tools.options as eboptions
from easybuild.tools.config import build_option, get_module_naming_scheme, package_path
from easybuild.tools.filetools import change_dir, which, write_file
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.testing import  session_state

def architecture_query(model_num):
	model_mapping = {
		'4F': 'Broadwell',
		'57': 'KnightsLanding',
		'3F': 'Haswell',
		'46': 'Haswell',
		'3A': 'IvyBridge',
		'3E': 'IvyBridge',
		'2A': 'SandyBridge',
		'2D': 'SandyBridge',
		'25': 'Westmere',
		'2C': 'Westmere',
		'2F': 'Westmere',
		'1E': 'Nehalem',
		'1A': 'Nehalem',
		'2E': 'Nehalem',
		'17': 'Penryn',
		'1D': 'Penryn',
		'0F': 'Merom'
		}
	if model_num in model_mapping.keys():
		return model_mapping[model_num]
	else:
		print "Model Number: ", model_num, " not found in dictionary, please consider adding the model number and Architecture name"
		return None


def generate_singularity_recipe(software,toolchain, system_info,arch_name):

    singularity_os = build_option('singularity_os')
    singularity_os_release = build_option('singularity_os_release')
    singularity_bootstrap = build_option('singularity_bootstrap')
    container_size = build_option('container_size')
    build_container= build_option('build_container')

    print "OS/Release:", singularity_os, singularity_os_release
    packagepath_dir = package_path()
    modulepath = ""

    appname,appver = software

    if toolchain == None:
	tcname = None 
    else:
	tcname,tcver = toolchain

    module_scheme = get_module_naming_scheme()
    bootstrap_content = "BootStrap: " + singularity_bootstrap + "\n" 
    bootstrap_content += "From: shahzebsiddiqui/easybuild-framework:" + singularity_os + "-" + singularity_os_release + "\n"
    
    if module_scheme == "HierarchicalMNS":
	    modulepath = "/app/modules/all/Core"
    else:
	    modulepath = "/app/modules/all/"

    post_content = """
%post
su - easybuild
"""
    environment_content = """
%environment
source /etc/profile
"""


    # check if toolchain is specified, that affects how to invoke eb and module load is affected based on module naming scheme
    if tcname != None:
        post_content += "eb " + appname + "-" + appver + "-" + tcname + "-" + tcver + ".eb --robot --installpath=/app/easybuild --prefix=/scratch --tmpdir=/scratch/tmp  --module-naming-scheme=" + module_scheme + "\n"

        def_file  = appname + "-" + appver + "-" + tcname + "-" + tcver + ".def"

        if module_scheme == "HierarchicalMNS":
                environment_content += "module use " + modulepath + "\n" 
		environment_content += "module load " + os.path.join(appname,appver) + "\n"
        else:

                environment_content += "module use " +  modulepath + "\n" 
                environment_content += "module load " + os.path.join(appname,appver+"-"+tcname+"-"+tcver) + "\n"
    else:
        post_content += "eb " + appname + "-" + appver + ".eb --robot --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp  --module-naming-scheme=" + module_scheme + "\n"
	
        if module_scheme == "HierarchicalMNS":
                environment_content += "module use " +  modulepath + "\n"
	else:
                environment_content += "module use " +  modulepath + "\n"

        environment_content +=  "module load " + os.path.join(appname,appver) + "\n"
        def_file  = appname + "-" + appver + ".def"


    post_content += "exit \n"


    runscript_content = """
%runscript
eval "$@"
"""

    label_content = "\n%labels \n"
    label_content += "Architecture " + arch_name + "\n"
    label_content += "Host " + system_info['hostname'] + "\n"
    label_content += "CPU  " + system_info['cpu_model'] + "\n"

    content = bootstrap_content + post_content + runscript_content + environment_content + label_content
    change_dir(packagepath_dir)
    write_file(def_file,content)

    print "Writing Singularity Definition File: %s" % os.path.join(packagepath_dir,def_file)

    print "build_container:", build_container
    # if easybuild will create and build container
    if build_container:
	    container_name = os.path.splitext(def_file)[0] + ".img"
   	    os.system("sudo singularity image.create -s " + str(container_size) + " " + container_name)
	    os.system("sudo singularity build " + container_name + " " + def_file)
    return 




def check_singularity(software, toolchain):
    """
    Return build statistics for this build
    """
    singularity_path = which("singularity")
    singularity_version = 0
    if singularity_path:
	print "Singularity tool found at %s" % singularity_path
	ret = subprocess.Popen("singularity --version", shell=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	# singularity version format for 2.3.1 and higher is x.y-dist
	singularity_version = ret.communicate()[0].split("-")[0]
    else:
	print "Singularity not found in your system."
 	EasyBuildError("Singularity not found in your system")


    if float(singularity_version) < 2.4:
    	EasyBuildError("Please upgrade singularity instance to version 2.4.1 or higher")
    else:
	print "Singularity version is 2.4 or higher ... OK"
	print "Singularity Version is " + singularity_version

    buildsystem_session = session_state()
    system_info = buildsystem_session['system_info']
    """
    print buildsystem_session['cpu_model']
    model = buildsystem_session['cpu_model'],
    host = buildsystem_session['hostname'],
    osname = buildsystem_session['os_name'],
    ostype = buildsystem_session['os_type'],
    osversion = buildsystem_session['os_version'],

    print model
    print host
    print host
    print osname
    print ostype
    print osversion
    """

    ret = subprocess.Popen("""lscpu | grep Model: | cut -f2 -d ":" """,shell=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    model_num = int(ret.communicate()[0])

    # convert decimal to hex. Output like  0x3e. Take everything after x and convert to uppercase
    model_num = hex(model_num).split('x')[-1].upper()
    arch_name = architecture_query(model_num)

    generate_singularity_recipe(software,toolchain, system_info, arch_name)

    return 
