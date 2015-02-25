#!/usr/bin/env python
from __future__ import print_function
import sys
import os
import time
import pwd
from easybuild.framework.easyconfig.format.format import Dependency
from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.framework.easyconfig.parser import EasyConfigParser

import argparse
#
# This program makes a database of all software installed by EasyBuild. 
# It walks the directory tree starting by default at EASYBUILD_INSTALLPATH.
# The EasyBuild module should be loaded ahead of running.
# All files *.eb are parsed 
#
# It is useful to copy the resulting output in a common accessible location 
# For use by other scripts such as:
#                query_toolchain.py       --- lists toolchain module for some
#                                               software/ version
#                query_dependency.py      --- reverse dependency lookup
#                ec_manager.py            --- manages easyconfig collections
#                find_not_dependency.py   --- lists programs that are not 
#                                                dependencies of any others
# EB Gregory 25 Feb 2015


def main():

    if 'EASYBUILD_INSTALLPATH' in os.environ:
        top_default = os.environ['EASYBUILD_INSTALLPATH']+'/software/'
    else:
        print ("Please define the environment variable EASYBUILD_INSTALLPATH "
               "as the EasyBuild install path root, or give a search path "
               "with the -t TOPDIR command line argument.")
        sys.exit()

    # get arguments
    parser = argparse.ArgumentParser(description="Builds a catalog of software "
                                     "installed by easybuild. Currently does "
                                     "not list versions of Easybuild.")
    parser.add_argument("-t", "--topdir", help="the top directory for "
                        "beginning the search for installed software",
                        default=top_default)
    args = parser.parse_args()

    top = args.topdir

    exten = '.eb'
    applications = []

    num_apps = 0

    exclude = set(['EasyBuild'])
    exclude_sstr = ".sys."

    for root, dirs, files in os.walk(top, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude]

        for name in files:
            # the exclude_sstr part should be improved
            if (name.lower().endswith(exten) and (exclude_sstr not in name)):
                eb_file = os.path.join(root, name)

                app_dict = parse_eb_file(eb_file)

                applications.append(app_dict)

                num_apps += 1

    applications.sort(key=by_name_vers)

    for app in applications:
        app_name = app.get('name')
        app_vers = app.get('vers')
        app_tc = app.get('tc_name')
        app_tcvers = app.get('tc_vers')
        app_owner = app.get('owner')
        app_ebfile = app.get('ebfile')

        print("APP {0}\t{1}\t{2}\t{3}\t{4}".format(app_name, app_vers,
                                                   app_tc, app_tcvers,
                                                   app_owner))
        print("FILE {0}".format(app_ebfile))
        if app.get('deps'):
            app_deps = app.get('deps')
            numdeps = len(app_deps)
            for i in range(numdeps):
                dep_name = app_deps[i][0]
                dep_vers = app_deps[i][1]
                dep_vers_suffix = ''
                dep_tc = app_tc
                dep_tc_vers = app_tcvers
                if len(app_deps[i]) > 2:
                    dep_vers_suffix = app_deps[i][2]

                if len(app_deps[i]) > 3:
                    dep_tc = app_deps[i][3][0]
                    dep_tc_vers = app_deps[i][3][1]

                dep_vers = dep_vers+dep_vers_suffix
                print("\tDEP {0}\t{1}\t{2}\t{3}".format(
                      dep_name, dep_vers, dep_tc, dep_tc_vers))


def by_name_vers(app_dict):
    app_name = app_dict.get("name")
    app_vers = app_dict.get("vers")
    nv = app_name+"-"+app_vers
    return nv


def parse_eb_file(eb_file):

    ecp = EasyConfigParser(eb_file)

    ec = ecp.get_config_dict()
    owner = pwd.getpwuid(os.stat(eb_file).st_uid).pw_name

    name = ec.get('name')
    vers = ec.get('version')
    tc_name = ec.get('toolchain', dict()).get('name')
    tc_vers = ec.get('toolchain', dict()).get('version')

    if ((not name) or (not vers) or (not tc_name) or (not tc_vers)):
        # check that this file has the basics of an easyconfig
        return

    vsuff = ec.get('versionsuffix', '')
    vpref = ec.get('versionprefix', '')
    vers = vpref+vers+vsuff

    deps = ec.get("dependencies")
    # also check for build dependencies, which are listed
    # separately in the eb file

    builddeps = ec.get("builddependencies")

    if builddeps:
        if deps:
            deps.extend(builddeps)
        else:
            deps = builddeps

    if deps:
        numdeps = len(deps)

        for i in range(0, numdeps):

            dep_name = deps[i][0]
            dep_vers = deps[i][1]

            # default is dependency toolchain is the same
            # and no dependency version suffix
            # unless we hear otherwise
            dep_vers_suffix = ""
            dep_tc = tc_name
            dep_tc_vers = tc_vers

            if len(deps[i]) > 2:
                dep_vers_suffix = deps[i][2]

                if len(deps[i]) > 3:
                    dep_tc = deps[i][3][0]
                    dep_tc_vers = deps[i][3][1]

            dep_vers += dep_vers_suffix

    return {'name': name, 'vers': vers, 'tc_name': tc_name, 'tc_vers': tc_vers,
            'owner': owner, 'deps': deps, 'ebfile': eb_file}


if __name__ == "__main__":
    main()
