#!/usr/bin/env bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

function printError {
    echo -e "${RED}$@${NC}"
}

verbose=0
function printVerbose {
    (( verbose == 0 )) || echo "$@"
}

function checkModule {
    moduleFolder="$1"
    moduleName="$(basename "$(dirname "$moduleFolder")")"
    moduleVersion="$(basename "$moduleFolder")"
    moduleStr="$moduleName/$moduleVersion"
    printVerbose "Processing $moduleStr"
    ec_glob=( "$moduleFolder/easybuild/"*.eb )
    if [[ ! -e "${ec_glob[@]}" ]]; then
        printError "=== Did not find installed EC for $moduleStr"
        return
    fi
    ec_installed="$ec_glob"
    ec_filename=$(basename "$ec_installed")
    # Try with most likely location first for speed
    first_letter=${ec_filename:0:1}
    letterPath=$easyconfigFolder/${first_letter,,}
    if [[ -d "$letterPath" ]]; then
        ec_new="$(find "$letterPath" -type f -name "$ec_filename")"
    else
        ec_new=
    fi
    # Fallback if not found
    [[ -n "$ec_new" ]] || ec_new="$(find "$easyconfigFolder" -type f -name "$ec_filename")"
    if [[ -z "$ec_new" ]]; then
        printError "=== Did not find new EC $ec_filename"
    elif [[ ! -e "$ec_new" ]]; then
        printError "=== Found multiple new ECs: $ec_new"
    elif ! out=$(diff -u "$ec_installed" "$ec_new"); then
        if ((short == 1)); then
            basename "$ec_installed"
        else
            echo -e "${YELLOW}=== Needs updating: ${GREEN}${ec_installed}${YELLOW} vs ${GREEN}${ec_new}${NC}"
            if ((showDiff == 1)); then
                echo "$out"
            fi
        fi
    fi
}

ecDefaultFolder=
if path=$(which eb 2>/dev/null); then
    path=$(dirname "$path")
    for p in "$path" "$(dirname "$path")"; do
        if [ -d "$p/easybuild/easyconfigs" ]; then
            ecDefaultFolder=$p
            break
        fi
    done
fi

function usage {
    echo "Usage: $(basename "$0") [--verbose] [--diff] --loaded|--modules INSTALLPATH --easyconfigs EC-FOLDER"
    echo
    echo "Check installed modules against the source EasyConfig (EC) files to determine which have changed."
    echo "Can either check the currently loaded modules or all modules installed in a specific location"
    echo
    echo "--verbose                Verbose status output while checking"
    echo "--loaded                 Check only currently loaded modules"
    echo "--short                  Only show filename of changed ECs"
    echo "--diff                   Show diff of changed module files"
    echo "--modules INSTALLPATH    Check all modules in the specified (software) installpath, i.e. the root of module-binaries"
    echo "--easyconfigs EC-FOLDER  Path to the folder containg the current/updated EasyConfigs. ${ecDefaultFolder:+Defaults to $ecDefaultFolder}"
    exit 0
}

checkLoadedModules=0
showDiff=0
short=0
modulesFolder=""
easyconfigFolder=$ecDefaultFolder

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage;;
        -v|--verbose)
            verbose=1;;
        -d|--diff)
            showDiff=1;;
        -s|--short)
            short=1;;
        -l|--loaded)
            checkLoadedModules=1;;
        -m|--modules)
            modulesFolder="$2"
            shift;;
        -e|--easyconfigs)
            easyconfigFolder="$2"
            shift;;
        *)
            printError "Unknown argument: $1"
            exit 1;;
    esac
    shift
done

if [ -z "$easyconfigFolder" ]; then
    printError "Folder to easyconfigs not given!" && exit 1
fi
if [ -z "$modulesFolder" ]; then
    if (( checkLoadedModules == 0 )); then
        printError "Need either --modules or --loaded to specify what to check!" && exit 1
    fi
elif (( checkLoadedModules == 1 )); then
    printError "Cannot specify --modules and --loaded!" && exit 1
fi

if [ -d "$easyconfigFolder/easybuild/easyconfigs" ]; then
    easyconfigFolder="$easyconfigFolder/easybuild/easyconfigs"
fi

if (( checkLoadedModules == 1 )); then
    for varname in $(compgen -A variable | grep '^EBROOT'); do
        checkModule "${!varname}"
    done
else
    for module in "$modulesFolder"/*/*/easybuild; do
        checkModule "$(dirname "$module")"
    done
fi
