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
import os
import sys
from easybuild.tools.config import build_option, get_module_naming_scheme, package_path
from easybuild.tools.filetools import change_dir, which, write_file

# ----
from easybuild.tools.filetools import det_size
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.systemtools import get_system_info
from easybuild.tools.version import EASYBLOCKS_VERSION, FRAMEWORK_VERSION


def generate_singularity_recipe(software,toolchain):

    singularity_os = build_option('singularity_os')
    singularity_bootstrap = build_option('singularity_bootstrap')

    packagepath_dir = package_path()
    modulepath = ""

    appname,appver = software

    if toolchain == None:
	tcname = None 
    else:
	tcname,tcver = toolchain

    module_scheme = get_module_naming_scheme()
    bootstrap_content = "BootStrap: " + singularity_bootstrap + "\n" 
    bootstrap_content += "From: shahzebsiddiqui/easybuild \n"
    
    if module_scheme = "HierarchicalMNS":
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

                environment_content += "module use " modulepath + "\n" 
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
    content = bootstrap_content + post_content + runscript_content + environment_content
    change_dir(packagepath_dir)
    write_file(def_file,content)

    print "Writing Singularity Definition File: %s" % os.path.join(packagepath_dir,def_file)

    container_name = os.path.splitext(def_file)[0] + ".img"
    os.system("sudo singularity build " + container_name + " " + def_file)
    return 




def check_singularity(software, toolchain):
    """
    Return build statistics for this build
    """
    singularity_path = which("singularity")
    if singularity_path:
	print "Singularity tool found at %s" % singularity_path
    else:
	print "Singularity not found in your system."
	sys.exit(1)

    generate_singularity_recipe(software,toolchain)

    return 
