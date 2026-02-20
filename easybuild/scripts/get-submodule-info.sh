#!/bin/bash
##
# Copyright 2025-2025 Ghent University
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
"""
Utility to gather submodules of an existing, recursively cloned repository
in the current working directory.

The output is a dictionary mapping submodule names to their repository slug, commit hash and relative path.

author: Alexander Grund (TU Dresden)
"""


echo "Print information on all submodules for the git repository in $PWD"
echo
echo "Format: '<name>': ('<owner>/<name>', '<commit>', '<path>'),"
echo

function print_submodules {
    local base_path=$1
    git -C "$base_path" submodule status | while read -r line; do
        # Example line: " 3a6b7dc libs/foo (heads/main)"
        commit=$(echo "$line" | awk '{print $1}')
        path=$(echo "$line" | awk '{print $2}')

        if [[ -z $base_path ]]; then
            sub_folder=$path
        else
            sub_folder=$base_path/$path
        fi

        # Extract owner/repo from URL
        url=$(git config --file "${base_path:-$PWD}/.gitmodules" --get "submodule.$path.url")
        repo_slug=$(echo "$url" | sed -E 's#.*[:/]([^/:]+/[^/.]+)(\.git)?$#\1#')

        name=$(basename "$path")
        short_commit=$(git -C "$sub_folder" rev-parse --short "$commit" 2>/dev/null || echo "$commit")

        printf "'%s': ('%s', '%s', '%s'),\n" "$name" "$repo_slug" "$short_commit" "$sub_folder"
        print_submodules "$sub_folder"
    done
}

print_submodules "" | sort
