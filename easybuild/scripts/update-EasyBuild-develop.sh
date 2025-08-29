#!/usr/bin/env bash

# Stop in case of error
set -e

# Print script help
print_usage()
{
    echo "Checkout develop branch of all EasyBuild repositories"
    echo "and pull changes from the remote repository."
    echo "To be used with the EasyBuild-develop module or a set git-working-dirs-path"
    echo "Usage: $0 [<git_dir>]"
    echo
    echo "    git_dir:         directory where all the EasyBuild repositories are installed."
    echo "                     Automatically detected if not specified."
    echo
}

if [[ "$1" = "-h" ]] || [[ "$1" = "--help" ]]; then
    print_usage
    exit 0
fi

if [[ $# -gt 1 ]] ; then
    echo "Error: invalid arguments"
    echo
    print_usage
    exit 1
fi

if [[ $# -eq 1 ]]; then
    git_dir=$1
else
    # Auto detect git_dir
    git_dir=""
    if ! which eb &> /dev/null; then
        module load EasyBuild-develop || module load EasyBuild || true
        if ! which eb &> /dev/null; then
            echo 'Found neither the `eb` command nor a working module.'
            echo 'Please specify the git_dir!'
            exit 1
        fi
    fi
    if out=$(eb --show-config | grep -F 'git-working-dirs-path'); then
        path=$(echo "$out" | awk '{print $NF}')
        if [[ -n "$path" ]] && [[ -d "$path" ]]; then
            git_dir=$path
            echo "Using git_dir from git-working-dirs-path: $git_dir"
        fi
    fi
    if [[ -z "$git_dir" ]]; then
        eb_dir=$(dirname "$(which eb)")
        if [[ "$(basename "$eb_dir")" == "easybuild-framework" ]] && [[ -d "$eb_dir/.git" ]]; then
            git_dir=$(dirname "$eb_dir")
            echo "Using git_dir from eb command: $git_dir"
        else
            echo 'Please specify the git_dir as auto-detection failed!'
            exit 1
        fi
    fi
fi

cd "$git_dir"

for folder in easybuild easybuild-framework easybuild-easyblocks easybuild-easyconfigs; do
    echo # A newline
    if [[ -d "$folder" ]]; then
        echo "========= Checking ${folder} ========="
    else
        echo "========= Skipping non-existent ${folder} ========="
    fi
    cd "$folder"
    git checkout "develop"
    if git remote | grep -qF github_easybuilders; then
        git pull "github_easybuilders"
    else
        git pull
    fi
    cd ..
done

index_file="$git_dir/easybuild-easyconfigs/easybuild/easyconfigs/.eb-path-index"
if [[ -f "$index_file" ]]; then
    echo -n "Trying to remove index from ${index_file}..."
    if rm "$index_file"; then
        echo "Done!"
        echo "Recreate with 'eb --create-index \"$(dirname "$index_file")\"'"
    else
        echo "Failed!"
    fi
fi
