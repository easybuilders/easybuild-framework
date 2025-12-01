#!/bin/bash

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
