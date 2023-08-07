#!/usr/bin/env bash

set -euo pipefail

#####################################
# Create a list for usage in `sources` of an EC by checking submodules recursively
# Usage:
# - Recursively clone git repo: `git clone --recurse-submodules ...`
# - Update variables below depending on the software
# - `createSubmoduleDeps.sh <path-to-repo-root>`

git_repo="$1"

# Template (variable) for usage with `extract_cmd` in EC
extract_cmd="local_extract_cmd_pattern"

if [[ "$(basename "$git_repo")" == "pytorch" ]]; then
    # Folder in git_repo where submodules are located in
    thirdparty_dir="third_party"
    # Repo names for dependencies that should be ignored
    repo_ignore=(zstd nccl six enum34 ios-cmake ARM_NEON_2_x86_SSE clang-cindex-python3 protobuf pybind11)
    # Subdir of git_repo to ignore
    subdir_ignore=(
        onnx/third_party/pybind11
        onnx-tensorrt/third_party/onnx
        tensorpipe/third_party/pybind11
    )
fi

function printSubmoduleDeps(){
    local dir="$1"
    local submodules_dir="$2"
    local submodules

    mapfile -t submodules < <(cd "$dir" && git submodule status "$submodules_dir")

    for submodule_data in "${submodules[@]}"; do
        hash=$(echo "$submodule_data" | awk '{print $1;}')
        submodule=$(echo "$submodule_data" | awk '{print $2;}')

        if [[ "${hash::1}" == "-" ||  "${hash::1}" == "+" ||  "${hash::1}" == "U" ]]; then
            echo "Submodule $submodule is dirty. Please reset"
            exit 1
        fi

        submodule_dir="$dir/$submodule"
        subfolder=${submodule_dir#*/$thirdparty_dir/}

        if [[ " ${subdir_ignore[*]} " =~ " $subfolder " ]]; then
            continue
        fi

        remote=$(cd "$submodule_dir" && git remote get-url origin)
        remote="${remote%.git}"
        source_url="${remote}/archive"

        if [[ " ${repo_ignore[*]} " =~ " $(basename "$remote") " ]]; then
            continue
        fi

        commit_date=$(cd "$submodule_dir" && git show -s --format='%cd' --date=format:'%Y%m%d')
        filename="$(basename "$remote")-${commit_date}.tar.gz"
        filename="${filename/-git-mirror/}"

        echo "\
    {
        'source_urls': ['$source_url'],
        'download_filename': '${hash}.tar.gz',
        'filename': '$filename',
        'extract_cmd': $extract_cmd % '$subfolder',
    },"
        printSubmoduleDeps "$submodule_dir" "."
    done
}

printSubmoduleDeps "$git_repo" "$thirdparty_dir"
