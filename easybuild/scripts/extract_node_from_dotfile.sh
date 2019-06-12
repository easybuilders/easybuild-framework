#!/bin/bash
##
# Copyright 2012-2019 Ghent University
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
##

# @author: Alan O'Cais (Juelich Supercomputing Centre)

##
# Use case:
#
# A large dotfile that contains all software installed with EasyBuild can be generated with a command line such as:
#   eb --dep-graph=depgraph.dot $EASYBUILD_INSTALLPATH/software/*/*/easybuild/*.eb
# Such a dotfile is (typically) too large to deal with directly. This script can extract a particular node from such a
# dotfile, e.g.,
#   ./<script> <input dot file> <output dot file> "Compiler/GCCcore/7.3.0/h5py/2.8.0-serial-Python-3.6.6"
# which can be used to help evaluate the impact of uninstalling that particular software package
##

find_children () {
    input_dotfile=$1
    output_dotfile=$2
    node_to_search_for=$3
    # The fact that we put the semicolon straight after means we exclude anywhere the module
    # is only required as a build dependency (since these cases have extra formatting the
    # semicolon comes later);
    # the sed command makes sure we ignore whether the module is hidden or not
    grep ' "'${node_to_search_for}'";' ${input_dotfile} | sed s#/\\.#/#g >> ${output_dotfile}
    grep ' "'${node_to_search_for}'";' ${input_dotfile} | awk '{print $1}'| \
        xargs -i bash -c "map_dep ${input_dotfile} ${output_dotfile} {}"
}

map_dep () {
    input_dotfile=$1
    output_dotfile=$2
    node_to_search_for=$3
    # Search for a node that matches the string and add a comment marker at the end
    # to leverage with grep later
    # (if non-installed software had additional formatting they would be ignored)
    # the sed command makes sure we ignore whether the module is hidden or not
    grep "^"'"'${node_to_search_for}'";' ${input_dotfile} | awk '{print $1" // xxnodexx"}' | \
        sed s#/\\.#/#g >> ${output_dotfile}
    if [ $? ]
    then
        find_children ${input_dotfile} ${output_dot_file} ${node_to_search_for}
    fi
}

export -f find_children
export -f map_dep

# Check command line
if [ "$#" -ne 3 ]; then
    echo -e "Expected command line:\n\t<script> <input dot file> <output dot file> <node to search for>"
    exit 1
fi

input_dotfile=$1
output_dotfile=$2
node_to_search_for=$3

# Begin digraph in output file
echo digraph graphname \{ > ${output_dotfile}

# Use a temporary file to store nodes and edges
tmpfile=`mktemp`
# initialise the file
> ${tmpfile}

# Gather nodes and edges related to ${node_to_search_for}
map_dep ${input_dotfile} ${tmpfile} ${node_to_search_for}

# There is potential duplication due to nodes being followed multiple times so let's
# remove it:
# put nodes first (we used a marker to identify them), make sure they are unique
cat ${tmpfile} | sort | uniq | grep xxnodexx >> ${output_dotfile}
# Then edges, also make sure they are unique
cat ${tmpfile} | sort | uniq | grep -v xxnodexx >> ${output_dotfile}

# Clean up
rm ${tmpfile}
echo \} >> ${output_dotfile}