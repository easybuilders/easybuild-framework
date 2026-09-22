#!/usr/bin/env bash

check_no_glob_matches() {
    local label="$1"
    local pattern="$2"

    echo ">>> CHECK: $label"
    echo "    glob: $pattern"

    if compgen -G "$pattern" > /dev/null; then
        echo "FAIL: files/directories matched"
        compgen -G "$pattern" | sort
        return 1
    fi

    echo "PASS: no files/directories matched"
    echo
}

check_path_exists() {
    local label="$1"
    local path="$2"

    echo ">>> CHECK: $label"
    echo "    path: $path"

    if [[ -e "$path" ]]; then
        echo "PASS: path exists"
        ls -ld "$path"
        echo
        return 0
    fi

    echo "FAIL: path does not exist"
    echo "Parent contents:"
    ls -la "$(dirname "$path")" || true
    echo
    return 1
}

check_bwrap_info_contains() {
    local label="$1"
    local option="$2"
    local bwrap_info="/tmp/bwrap-installpath/bwrap_info.json"

    echo ">>> CHECK: $label"
    echo "    option: $option"

    if python3 -c "import json, sys; sys.exit(0 if '$option' in json.load(open('$bwrap_info'))['bwrap_cmd'] else 1)"; then
        echo "PASS: '$option' found in bwrap_cmd"
        echo
        return 0
    fi

    echo "FAIL: '$option' not found in bwrap_cmd"
    echo
    return 1
}

check_glob_exists() {
    local label="$1"
    local pattern="$2"

    echo ">>> CHECK: $label"
    echo "    glob: $pattern"

    if compgen -G "$pattern" > /dev/null; then
        echo "PASS: matches found"
        compgen -G "$pattern" | sort | xargs -r ls -l
        echo
        return 0
    fi

    echo "FAIL: no matches found"
    echo
    return 1
}

main() {
    local failures=0

    echo "=== Host-side EasyBuild path state ==="
    find "$HOME/.local/easybuild" -maxdepth 5 -print || true
    echo

    echo "=== bwrap install path state ==="
    find /tmp/bwrap-installpath -maxdepth 5 -print || true
    echo

    check_no_glob_matches "no host UnZip modules" \
        "$HOME/.local/easybuild/modules/all/UnZip/*" || failures=$((failures + 1))

    check_no_glob_matches "no host bzip2 modules" \
        "$HOME/.local/easybuild/modules/all/bzip2/*" || failures=$((failures + 1))

    check_no_glob_matches "no host UnZip software files" \
        "$HOME/.local/easybuild/software/UnZip/6.0/*" || failures=$((failures + 1))

    check_no_glob_matches "no host bzip2 software files" \
        "$HOME/.local/easybuild/software/bzip2/1.0.8/*" || failures=$((failures + 1))

    check_path_exists "bwrap bzip2 module file exists" \
        "/tmp/bwrap-installpath/modules/all/bzip2/1.0.8.lua" || failures=$((failures + 1))

    check_path_exists "bwrap UnZip module file exists" \
        "/tmp/bwrap-installpath/modules/all/UnZip/6.0.lua" || failures=$((failures + 1))

    check_glob_exists "bwrap UnZip installed binaries exist" \
        "/tmp/bwrap-installpath/software/UnZip/*/bin/*" || failures=$((failures + 1))

    check_glob_exists "bwrap bzip2 installed binaries exist" \
        "/tmp/bwrap-installpath/software/bzip2/*/bin/*" || failures=$((failures + 1))

    check_glob_exists "bwrap UnZip EasyBuild logs exist" \
        "/tmp/bwrap-installpath/software/UnZip/*/easybuild/*log*" || failures=$((failures + 1))

    check_glob_exists "bwrap bzip2 EasyBuild logs exist" \
        "/tmp/bwrap-installpath/software/bzip2/*/easybuild/*log*" || failures=$((failures + 1))

    check_bwrap_info_contains "bwrap-options value was passed through to bwrap command" \
        "--die-with-parent" || failures=$((failures + 1))

    if [[ "$failures" -ne 0 ]]; then
        echo "ERROR: $failures bwrap validation check(s) failed"
        return 1
    fi

    echo "All bwrap validation checks passed"
}

main "$@"
