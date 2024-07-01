#!/usr/bin/env python
from __future__ import print_function
import sys
import os
import argparse
import shutil
from pprint import pprint


#
# This script is for managing a local collection of EasyConfig files
# It can:
#    - make a list so that they are orderd with programs listed after 
#            all of their dependiencies
#
#    - Copy EasyConfig files to a directory 
#    - suggest updates to dependency versions (from already-installed versions)
#    - Identify cases where dependency tooklchain/version is a mismatch
#    - list all applications and their dependencies
#
#  The program is a little unpolished but it is more useful than it sounds.


# When given the name (or partial name) of an application this script lists
# the toolchain module that must be loaded.

class SmartFormatter(argparse.HelpFormatter):

    def _split_lines(self, text, width):
        # this is the RawTextHelpFormatter._split_lines
        if text.startswith('R|'):
            return text[2:].splitlines()
        return argparse.HelpFormatter._split_lines(self, text, width)


######################################################################
def main():

    # default file comes from environment variable
    database_file = os.environ['EBSW_DATABASE']

    # get arguments
    parser = argparse.ArgumentParser(description="Prints a list of "
                                     "applications in such an order that all "
                                     "of the dependencies occur in the list "
                                     "before their dependent applications. "
                                     "The default is that the names of the "
                                     "EasyConfig files are listed.",
                                     formatter_class=SmartFormatter)

    parser.add_argument("tc_name", help="Toolchain name")
    parser.add_argument("tc_vers", help="Toolchain version")
    parser.add_argument("-f", "--dbfile",
                        help="Use local database file instead of default "
                        "system file:  "+database_file)
    parser.add_argument("-t", "--tc_listfile",
                        help="R|Optionally supplied file with lists of "
                        "sub-toolchains in which to chase dependencies. "
                        "Format should be:\n"
                        "<toolchain1> <version1>\n"
                        "<toolchain2> <version2>\n"
                        "<toolchain3> <version3>\n...\n"
                        "No effort is made to check any hierarchical "
                        "relationship between listed toolchains.")
    parser.add_argument("-c", "--copydir",
                        help="Directory to put a copy of EasyConfig files "
                        "into. No copy is done if this argument is not given")
    parser.add_argument("-l", "--long",
                        help="List the full path name to EasyConfig files. "
                        "Default is short name (no path). If the output "
                        "mode is one where EasyConfig files are not listed, "
                        "then this option does nothing.",
                        action="store_true")
    parser.add_argument("-T", "--toolchainfollow",
                        help="Consider an application's toolchain as a "
                        "dependency", action="store_true")

    outputgroup = parser.add_mutually_exclusive_group()
    outputgroup.add_argument("-E", "--ebfilelist",
                             help="Print an ordered list of EasyConfig files. "
                             "Default.", action="store_true", default=True)
    outputgroup.add_argument("-U", "--updatesuggest",
                             help="Suggest placed where dependency versions "
                             "*might* be updated to a newer installed "
                             "version. Toolchain updates are not suggested.",
                             action="store_true", default=False)
    outputgroup.add_argument("-D", "--deptable",
                             help="Print an ordered table of applications and "
                             "their dependencies.",
                             action="store_true", default=False)

    outputgroup.add_argument("-R", "--roguetc",
                             help="Look for EasyConfig files where a "
                             "dependency is in an unlisted toolchain/version. "
                             "For verifying version updates.",
                             action="store_true", default=False)

    group = parser.add_mutually_exclusive_group()
    group.add_argument("-a", "--allversions",
                       help="Report all versions of installed packages. "
                       "Default is to report only the highest version number",
                       action="store_true", default=True)
    group.add_argument("-s", "--singleversion",
                       help="Report only the highest version of installed "
                       "packages. Default.", action="store_true",
                       default=False)

    args = parser.parse_args()

    if(args.dbfile):
        database_file = args.dbfile

    dest_dir = ""
    if(args.copydir):
        copyflag = True
        dest_dir = args.copydir
    else:
        copyflag = False

    if(args.toolchainfollow):
        toolchain_follow = True
    else:
        toolchain_follow = False

    repeats_flag = False
    if(args.allversions):
        repeats_flag = True
    if(args.singleversion):
        repeats_flag = False

    full_path_flag = False
    if(args.long):
        full_path_flag = True

    # output formatting
    # default is a list of ebfiles
    eblist_flag = True
    if(args.ebfilelist):
        eblist_flag = True

    suggest_updates = False
    if(args.updatesuggest):
        suggest_updates = True

    deptable_flag = False
    if(args.deptable):
        deptable_flag = True

    rogue_tc_check_flag = False
    if(args.roguetc):
        rogue_tc_check_flag = True

    toolchain = args.tc_name
    toolchain_vers = args.tc_vers

    tc_list = []
    tc_dict = {'tc': toolchain, 'tc_vers': toolchain_vers}
    tc_list.append(tc_dict)

    # if user has supplied a file with subtoolchains listed, add them to
    # tc_list
    if(args.tc_listfile):
        tc_listfile = args.tc_listfile
        add_toolchains_to_list(tc_listfile, tc_list)

    if(toolchain_follow):
        # add "dummy","dummy"  as a relevant toolchain
        tc_list.append({'tc': 'dummy', 'tc_vers': 'dummy'})

    apps_list = read_database_file(database_file, tc_list, toolchain_follow,
                                   rogue_tc_check_flag)

    if rogue_tc_check_flag:
        # for dependency toolchain check,
        dump_out_offending(apps_list, tc_list, full_path_flag)

    # now sort the apps
    sort_apps(apps_list)

    # now print
    if(deptable_flag):
        print_package_list(apps_list, full_path_flag, copyflag, dest_dir,
                           repeats_flag)
        sys.exit()

    if(suggest_updates):
        print_dependency_updates(apps_list, full_path_flag, copyflag, dest_dir,
                                 repeats_flag)
    else:
        print_packages(apps_list, full_path_flag, copyflag, dest_dir,
                       repeats_flag)


######################################################################
def print_package_list(apps_list, full_path_flag, copyflag, dest_dir, repeats):

    # print out list of easyconfig files in new order
    # copy eb file if needed
    highest_version_list = make_highest_version_list(apps_list)

    package_index = 0
    for app in apps_list:
        name = app['name']
        vers = app['vers']
        tc_name = app['tc']
        tc_vers = app['tc_vers']

        if ((repeats) or (vers == highest_version_list[name])):

            path_chunks = app['ebfile'].split("/")
            short_file_name = path_chunks[len(path_chunks)-1]

            eb_file_full = app['ebfile']

            print("\n{0}  {1}\t{2}  {3}".format(name, vers, tc_name, tc_vers))

            if(app.get('deps')):
                dep_index = 0
                for dep in app['deps']:
                    d_name = dep['name']
                    d_vers = dep['vers']
                    d_tc = dep['tc']
                    d_tc_vers = dep['tc_vers']
                    print ("\t{0} {1}  {2}\t{3}  {4}".format(dep_index,
                                                             d_name, d_vers,
                                                             d_tc, d_tc_vers))
                    dep_index += 1
            package_index += 1

            copy_easyconfig(copyflag, eb_file_full, dest_dir)


######################################################################
def print_packages(apps_list, full_path_flag, copyflag, dest_dir, repeats):

    # print out list of easyconfig files in new order
    # copy eb file if needed
    highest_version_list = make_highest_version_list(apps_list)

    for app in apps_list:
        name = app['name']
        vers = app['vers']

        if ((repeats) or (vers == highest_version_list[name])):

            eb_file_full = app['ebfile']
            path_chunks = eb_file_full.split("/")
            short_file_name = path_chunks[len(path_chunks)-1]

            if(full_path_flag):
                print(eb_file_full)
            else:
                print(short_file_name)

            copy_easyconfig(copyflag, eb_file_full, dest_dir)


######################################################################
def print_dependency_updates(apps_list, full_path_flag, copyflag, dest_dir,
                             repeats):

    # print out list in new order
    # Eliminate repeats by default if requested

    # copy eb file if needed
    num_deps = 0
    package_index = 0
    num_packages = len(apps_list)

    highest_version_list = make_highest_version_list(apps_list)
    print ("")
    if repeats:
        print ("Repeats")
    else:
        print ("No repeats")

    print("These packages have no dependencies. "
          "Manually check for available updates.")

    while ((num_deps == 0) and (package_index < num_packages)):
        app = apps_list[package_index]
        if((not app.get('deps')) or (len(app['deps']) == 0)):
            app = apps_list[package_index]
            name = app['name']
            vers = app['vers']
            eb_file_full = app['ebfile']

            if ((repeats) or (vers == highest_version_list[name])):
                # Either this is the highest version
                # or we will print all of the versions
                num_deps = 0

                print("{0}\t{1}".format(name, vers))

                copy_easyconfig(copyflag, eb_file_full, dest_dir)
                if(app.get('deps')):
                    num_deps = len(app['deps'])

            package_index += 1

        else:
            num_deps = len(app['deps'])

    first_pack_w_deps = package_index

    # now print the packages with dependencies
    print("\nResolving dependency versions for the following packages.\n"
          "Arrows *suggest* possible changes in dependency versions "
          "to the highest version already installed.")

    for package_index in range(first_pack_w_deps, len(apps_list)):
        app = apps_list[package_index]
        name = app['name']
        vers = app['vers']
        eb_file_full = app['ebfile']

        if ((repeats) or (vers == highest_version_list[name])):
            # Either this is the highest version
            # or we will print all of the versions
            print("{0}\t{1}".format(name, vers))
            for dep in app['deps']:
                dep_name = dep['name']
                dep_vers = dep['vers']
                if(dep_name != app['tc']):
                    # do not list version updates for toolchains
                    update_string = ""
                    if (dep_vers < highest_version_list[dep_name]):
                        update_string = "-----> " + \
                            highest_version_list[dep_name]

                    print("\t{0}\t{1}\t{2}".format(dep_name, dep_vers,
                                                   update_string))

            copy_easyconfig(copyflag, eb_file_full, dest_dir)


######################################################################
def dump_out_offending(apps_list, tc_list, full_path_flag):

    #  if rogue_tc_check_flag we print out any applications where
    #  a dependency is not in the list of acceptible ones

    for app in apps_list:

        flag_this_app = False

        name = app['name']
        version = app['vers']

        tc = app['tc']
        tc_vers = app['tc_vers']
        eb_file_full = app['ebfile']
        if (app.get('deps')):
            for dep in app['deps']:
                dep_name = dep['name']
                dep_vers = dep['vers']
                dep_tc = dep['tc']
                dep_tc_vers = dep['tc_vers']
                test = toolchain_test(tc_list, dep_tc, dep_tc_vers)

                if (not test) \
                        and (dep_tc != "dummy") \
                        and (dep_tc_vers != "dummy"):
                    # we have found an unlisted toolchain
                    flag_this_app = True
                    
        if flag_this_app:
            # there is an unlisted toolchain in one of the dependencies
            print("In\n{0} {1}\t{2} {3}".format(name, version, tc, tc_vers))
            path_chunks = eb_file_full.split("/")
            short_file_name = path_chunks[len(path_chunks)-1]

            if(full_path_flag):
                print(eb_file_full)
            else:
                print(short_file_name)

            if (app.get('deps')):
                for dep in app['deps']:
                    dep_name = dep['name']
                    dep_vers = dep['vers']
                    dep_tc = dep['tc']
                    dep_tc_vers = dep['tc_vers']
                    test = toolchain_test(tc_list, dep_tc, dep_tc_vers)

                    if not test \
                            and (dep_tc != "dummy") \
                            and (dep_tc_vers != "dummy"):
                         print("\t{0} {1}\t{2} {3} "
                               "<---- check".format(dep_name, dep_vers,
                                                   dep_tc, dep_tc_vers))
    sys.exit()


######################################################################
def sort_apps(apps_list):

    # sort the apps
    # make sure each application appears in the list *after* its dependencies

    # find the first app that has dependencies
    first_pack_w_deps = -1

    for package_index in range(0, len(apps_list)):
        app = apps_list[package_index]

        if(first_pack_w_deps == -1) and (app.get('deps')):
            first_pack_w_deps = package_index

    if (first_pack_w_deps < 0):
        start_index = 0
    else:
        start_index = first_pack_w_deps

    # first pass; put independent packages first
    for package_index in range(start_index, len(apps_list)):
        app = apps_list[package_index]

        if((package_index > first_pack_w_deps) and (not app.get('deps'))):
            # we have found a package with no deps after the first_pack_w_deps
            # push everything back and stick it in

            hold_app = apps_list.pop(package_index)
            if (first_pack_w_deps == -1):
                apps_list.insert(0, hold_app)
                first_pack_w_deps = 0
            else:
                apps_list.insert(first_pack_w_deps, hold_app)
                first_pack_w_deps += 1

    # now list all of the dependencies first
    # continue to sweep the list until no more out-of order entriess are found

    switches_happened = True

    pass_counter = 0
    while (switches_happened):
        # continue sorting until we have made one full pass with no
        # need to re-arrange

        pass_counter += 1
        switches_happened = False

        for package_index in range(first_pack_w_deps, len(apps_list)):
            # sweep through the list

            # make a hash table of indicies
            indicies = make_name_ver_tc_hash(apps_list)

            app = apps_list[package_index]

            # find the dependency with the highest index
            highest_dep_index = find_highest_dependency(app, indicies)

            if (highest_dep_index > package_index):

                # move the package down in the list,
                # past its highest-indexed dependency

                hold_app = apps_list.pop(package_index)
                apps_list.insert(highest_dep_index, hold_app)
                switches_happened = True


######################################################################
def find_highest_dependency(app, indicies):
    highest_dep_index = -1
    # default value

    if app.get('deps'):

        for dep in app.get('deps'):

            dep_name = dep.get('name')
            dep_vers = dep.get('vers')
            dep_tc = dep.get('tc')
            dep_tc_vers = dep.get('tc_vers')

            dep_name_vers = \
                dep_name+"."+dep_vers+"."+dep_tc+"."+dep_tc_vers

            if dep_name_vers in indicies:

                if (indicies[dep_name_vers] > highest_dep_index):
                    highest_dep_index = indicies[dep_name_vers]
            else:
                print("Problem with dependency name-vers hash "
                      "at {0}".format(dep_name_vers))
                print("This usually indicates an unfulfilled dependency.")
                sys.exit()

    return highest_dep_index


######################################################################
def read_database_file(database_file, tc_list, toolchain_follow,
                       rogue_tc_check_flag):
    apps_list = []
    # open the database file
    try:
        db_file = open(database_file, "r")
    except IOError:
        print("Cannot open database file. Check that the file")
        print("{0}".format(database_file))
        print("exits and is readable. If not, run toolchain_finder.py")
        sys.exit()

    # read all of the lines, then close it again
    lines = db_file.readlines()
    db_file.close()

    for line in lines:
        words = line.split()

        if (len(words) > 1):

            if(words[0] == "APP"):
                # a new package listing
                test_tc = words[3]
                test_tc_vers = words[4]

                use_pkg = False

                # see if this toolchain is on the list of relevant ones
                use_pkg = toolchain_test(tc_list, test_tc, test_tc_vers)

                if (use_pkg):

                    apps_list.append({})
                    package_index = len(apps_list) - 1

                    apps_list[package_index]['name'] = words[1]
                    apps_list[package_index]['vers'] = words[2]
                    apps_list[package_index]['tc'] = words[3]
                    apps_list[package_index]['tc_vers'] = words[4]

                    if(toolchain_follow):
                        # consider the toolchain as the first dependency
                        tc_name = apps_list[package_index]['tc']
                        tc_vers = apps_list[package_index]['tc_vers']

                        if(tc_name != "dummy"):
                            add_dependency_to_list(apps_list[package_index],
                                                   tc_name, tc_vers,
                                                   "dummy", "dummy")

            if ((words[0] == "FILE") and (use_pkg == 1)):
                # the associated EasyConfig file
                apps_list[package_index]['ebfile'] = words[1]

            if((words[0] == "DEP") and (use_pkg == 1)):
                # These are dependencies
                deps_list = apps_list[package_index].get('deps')
                name = words[1]
                version = words[2]
                tc_name = words[3]
                tc_version = words[4]

                use_dep = toolchain_test(tc_list, tc_name, tc_version)

                # only track dependencies if they are in a toolchain
                # that we are following.
                # However, if rogue_tc_check_flag is enabled, add it
                # anyway and we will spit out the list later
                if use_dep or rogue_tc_check_flag:

                    add_dependency_to_list(apps_list[package_index], name,
                                           version, tc_name, tc_version)

    return apps_list


######################################################################
def make_name_ver_tc_hash(apps_list):

    indicies = {}

    # make a hash table of indicies
    for sort_index in range(0, len(apps_list)):

        sort_app = apps_list[sort_index]
        if (not sort_app.get('name')) or (not sort_app.get('vers')):
            print("Problem in package list at index {0}".format(sort_index))
            sys.exit()

        name_vers = sort_app.get('name')+"."+sort_app.get('vers')\
            + "." + sort_app.get('tc') + "." + sort_app.get('tc_vers')

        indicies[name_vers] = sort_index

    return indicies


######################################################################

def toolchain_test(tc_list, tc_name, tc_version):

    test = False

    for tchain in tc_list:

        if((tc_name == tchain.get('tc')) and
           (tc_version == tchain.get('tc_vers'))):
            test = True

    return test


######################################################################

def add_dependency_to_list(app, name, version, tc_name, tc_version):

    if(not app.get('deps')):
        app['deps'] = []

    dep = {}
    dep['name'] = name
    dep['vers'] = version
    dep['tc'] = tc_name
    dep['tc_vers'] = tc_version

    app['deps'].append(dep)


######################################################################

def add_toolchains_to_list(tc_listfile, tc_list):
    if(os.path.isfile(tc_listfile)):
        # open the toolchain file
        try:
            tc_file = open(tc_listfile, "r")
        except IOError:
            print("Cannot open toolchain file. Check that the file")
            print("{0}".format(tc_listfile))
            print("exits and is readable.")
            sys.exit()

        # read all of the lines, then close it again
        lines = tc_file.readlines()
        tc_file.close()
        linecount = 0

        # add listed toolchains/versions to toolchain list
        for line in lines:
            linecount += 1
            words = line.split()
            if(len(words) < 2):
                print("Not enough words on line {0} of toolchain file."
                      .format(linecount))
                sys.exit()
            else:
                tc_name = words[0]
                tc_vers = words[1]
                tc_list.append({'tc': tc_name, 'tc_vers': tc_vers})

    return tc_list


######################################################################
def make_highest_version_list(apps_list):

    highest_version = {}

    for app in apps_list:
        name = app['name']
        vers = app['vers']
        name_vers = name + "-" + vers

        if (name in highest_version):
            if (vers > highest_version[name]):
                highest_version[name] = vers
        else:
            highest_version[name] = vers

    return highest_version


######################################################################
def copy_easyconfig(copyflag, eb_file, dest_dir):

    if (copyflag):
        if(os.path.isfile(eb_file)):
            shutil.copy2(eb_file, dest_dir)
        else:
            print("File {0} does not exist. "
                  "Possibly the system database is out of date. "
                  "Skipping.".format(eb_file))

######################################################################

if __name__ == "__main__":
    main()
