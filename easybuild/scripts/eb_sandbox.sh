#!/bin/bash
##
# Copyright 2014 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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
#
# Script to test EasyBuild in a sandbox environment.
#
# author: Kenneth Hoste (HPC-UGent)
#

# exit on errors
set -e

DEFAULT_USER_BRANCH='hpcugent:master'
# use $TMPDIR/$TMP/$TEMP (in order of preference) as default sandbox if set, use /tmp as default
DEFAULT_SANDBOX_DIR=${TMPDIR:=${TMP:=${TEMP:='/tmp'}}}
GITHUB_API_URL='https://api.github.com/repos/hpcugent'

# disable debugging by default
debug=false
# don't keep sandbox by default, remove it
keep_sandbox=false
# disable fetching repositories via 'git clone' (since it's quite slow)
use_git=false

#############
# FUNCTIONS #
#############

# helper functions for printing debug information, warnings and error
debug() {
    if [ $debug = true ];
    then
        echo "[DEBUG] $1"
    fi
}
warning() {
    echo "[WARNING] $1" 1>&2
}
error() {
    echo "ERROR: $1" 1>&2
    exit 1
}

# print usage
usage() {
    echo "Usage: $0 [-d] [-f user:branch|PR] [-b user:branch|PR] [-c PR] [easyconfig files] -- [extra eb command line arguments]"
    echo "Example: $0 -c 767 -- --debug"
}

# print help
help() {
    echo "Script to test EasyBuild in a sandbox environment"
    echo "$(usage)"
    echo ""
    echo "Available options:"
    echo "  -b: Specify easyblocks user:branch or PR (default: ${DEFAULT_USER_BRANCH})"
    echo "  -c: Specify easyconfigs PR (passed to --from-pr)"
    echo "  -d: Enable debugging"
    echo "  -f: Specify framework user:branch or PR (default: ${DEFAULT_USER_BRANCH})"
    echo "  -g: Use 'git clone' to fetch repositories (default: use 'curl' or 'wget')"
    echo "  -h: Print help"
    echo "  -k: keep sandbox around (default: remove sandbox, unless script failed)"
    echo "  -t: Specify (parent) path for sandbox"
}

# download specified branch from specified GitHub repo and user
download_repo() {
    user=$1
    repo=$2
    branch=$3
    cd $sandbox
    debug "Downloading branch $branch from github.com/$user/easybuild-$repo into $PWD"
    # use git, if it's available
    if [ $use_git = true ]
    then
        which git | error "git command is not available"
        git_url="https://github.com/$user/easybuild-${repo}.git"
        # only download last 100 revisions, don't pull in all history
        git_clone_cmd="git clone --branch $branch --depth 100 $git_url"
        debug "Cloning branch $branch from $git_url into $PWD using '$git_clone_cmd'"
        eval $git_clone_cmd
    else
        ok=false
        which curl &> /dev/null && ok=true || warning "curl command is not available"
        if [[ $ok = true ]]
        then
            # use curl if it's available
            curl_cmd="curl -LsS https://github.com/$user/easybuild-$repo/archive/${branch}.tar.gz | tar xfz -"
            debug "Downloading and unpacking tarball $user:$branch using '$curl_cmd'"
            eval $curl_cmd
        else
            # try wget if curl is not available
            which wget &> /dev/null && ok=true || warning "wget command is not available"
            if [[ $ok = true ]]
            then
                tarball=${repo}_${user}_${branch}.tar.gz
                wget_cmd="wget https://github.com/$user/easybuild-$repo/archive/${branch}.tar.gz -O $tarball"
                debug "Downloading and unpacking tarball $user:$branch using '$wget_cmd'"
                eval $wget_cmd
                tar xfz $tarball
            else
                error "Neither curl nor wget are available, giving up"
            fi
        fi
    fi
    debug "Downloaded easybuild-$repo/$user:$branch to $PWD/easybuild-$repo"
}

# fetch EasyBuild repository according to provided specifications (user:branch or PR)
fetch() {
    repo=$1
    spec=$2
    if [[ "$spec" =~ ^[0-9][0-9]*$ ]]
    then
        # if a pull request number was specified, figure out the user:branch label first
        pr=$spec
        debug "Detected PR #$pr for easybuild-$repo repository"
        pr_data=`curl -sS $GITHUB_API_URL/easybuild-$repo/pulls/$pr`
        spec=`echo $pr_data | tr ',' '\n' | grep '"label":' | head -1 | sed 's/.*"label": "\([^"]*\)".*/\1/g'`
        debug "Obtained user:branch $spec for $repo PR #$pr"
    else
        # if the specification doesn't match a PR #, assume it's a user:branch label
        debug "Assuming '${spec}' is an easybuild-$repo repository user:branch label (since it's not a PR #)"
    fi
    user=`echo $spec | cut -f1 -d:`
    branch=`echo $spec | cut -f2 -d:`
    download_repo $user $repo $branch
}

# generate a random alphanumeric string of specified length
random_str() {
    n=$1
    # compose list of available characters
    i=0
    for c in {a..z} {A..Z} {0..9}
    do
        chars[$i]=${c}
        i=$(($i+1))
    done
    # compose random string
    str=""
    for i in `seq 1 $n`;
    do
        i=$(($RANDOM%${#chars[*]}))
        str="${str}${chars[$i]}"
    done
    echo $str
}

########
# MAIN #
########

# parse command line options
while getopts ":b:c:df:ghkt:" o; do
    case "${o}" in
        b)
            easyblocks_spec=${OPTARG}
            ;;
        c)
            easyconfigs_spec=${OPTARG}
            ;;
        d)
            debug=true
            ;;
        f)
            framework_spec=${OPTARG}
            ;;
        g)
            use_git=true
            ;;
        h)
            help
            exit 0
            ;;
        k)
            keep_sandbox=true;
            ;;
        t)
            sandbox_dir=${OPTARG}
            ;;
        :)
            error "Option -$OPTARG requires an argument."
            ;;
    esac
done
shift $((OPTIND-1))
eb_args=$*
extra_eb_args=''

if [ -z $sandbox_dir ]
then
    sandbox_dir=$DEFAULT_SANDBOX_DIR
fi

if [ -z ${framework_spec} ]
then
    framework_spec=$DEFAULT_USER_BRANCH
fi
if [ -z ${easyblocks_spec} ]
then
    easyblocks_spec=$DEFAULT_USER_BRANCH
fi
if [ -z ${easyconfigs_spec} ]
then
    easyconfigs_spec=$DEFAULT_USER_BRANCH
fi

# ensure a random subdir in specified sandbox
sandbox="$sandbox_dir/eb_sandbox_`date "+%Y%m%d_%H-%M-%S"`_`random_str 5`"
echo "Using $sandbox as sandbox"

debug "sandbox: $sandbox"
debug "framework spec: $framework_spec"
debug "easyblocks spec: $easyblocks_spec"
debug "easyconfigs spec: $easyconfigs_spec"
debug "eb arguments: $eb_args"

# fetch framework & easyblocks into sandbox
cwd=$PWD
mkdir -p $sandbox
cd $sandbox
echo "Fetching EasyBuild repositories into $sandbox"
fetch 'framework' $framework_spec
fetch 'easyblocks' $easyblocks_spec
if [[ "$eb_args" =~ .*\.eb.* ]]
then
    # only fetch easyconfigs repository if easyconfig files are specified
    fetch 'easyconfigs' $easyconfigs_spec
elif [[ "$easyconfigs_spec" =~ ^[0-9][0-9]*$ ]]
then
    # specify --from-pr if no easyconfig files are specified and a easyconfigs repo PR # is provided
    extra_eb_args="$extra_eb_args --from-pr=$easyconfigs_spec"
fi
cd $cwd

# set up sandbox environment
PATH=$sandbox/easybuild-framework:$PATH
PYTHONPATH=$sandbox/easybuild-framework:$sandbox/easybuild-easyblocks:$sandbox/easyblocks-easyconfigs:$PYTHONPATH
MODULEPATH=$sandbox/modules/all:$MODULEPATH

# compose command line
eb_cmd="eb --buildpath $sandbox --installpath $sandbox --force --debug $eb_args $extra_eb_args"

# run EasyBuild
echo "Running '$eb_cmd' in $PWD"
eval $eb_cmd 2>&1 | tee eb.log
echo "EasyBuild log available at eb.log"

# cleanup
if [ $keep_sandbox = true ]
then
    echo "Sandbox $sandbox retained"
else
    rm -rf $sandbox
    echo "Cleaned up sandbox $sandbox"
fi
