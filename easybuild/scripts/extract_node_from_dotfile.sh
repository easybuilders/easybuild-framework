#!/bin/bash

find_children () {
 # The fact that we put the semicolon straight after means we exclude anywhere the module
 # is only required as a build dependency (since these cases have extra formatting the
 # semicolon comes later);
 # the sed command makes sure we ignore whether the module is hidden or not
 grep ' "'$3'";' $1 | sed s#/\\.#/#g >> $2
 grep ' "'$3'";' $1 | awk '{print $1}'| xargs -i bash -c "map_dep $1 $2 {}"
}

map_dep () {
 # Search for a node that matches the string and add a comment marker at the end
 # to leverage with grep later
 # (if non-installed software had additional formatting they would be ignored)
 # the sed command makes sure we ignore whether the module is hidden or not
 grep "^"'"'$3'";' $1 | awk '{print $1" // xxnodexx"}' | sed s#/\\.#/#g >> $2
 if [ $? ]
 then
   find_children $1 $2 $3
 fi
}

export -f find_children
export -f map_dep

# Check command line
if [ "$#" -ne 3 ]; then
    echo -e "Expected command line:\n\t<script> <input dot file> <output dot file> <node to search for>"
    exit 1
fi

# Begin digraph in output file
echo digraph graphname \{ > $2

# Use a temporary file to store nodes and edges
> temp.dot
# Gather nodes and edges related to $3
map_dep $1 temp.dot $3

# There is potential duplication due to nodes being followed multiple times so let's
# remove it:
# put nodes first (we used a marker to identify them), make sure they are unique
cat temp.dot | sort | uniq | grep xxnodexx >> $2
# Then edges, also make sure they are unique
cat temp.dot | sort | uniq | grep -v xxnodexx >> $2

# Clean up
rm temp.dot
echo \} >> $2