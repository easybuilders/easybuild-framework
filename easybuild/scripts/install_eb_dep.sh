#!/bin/bash

if [ $# -ne 2 ]; then
    echo "Usage: $0 <name>-<version> <prefix>"
    exit 1
fi

set -eu

PKG="$1"
PREFIX="$2"

PKG_NAME="${PKG%-*}"
PKG_VERSION="${PKG##*-}"

CONFIG_OPTIONS=
PRECONFIG_CMD=

if [ "$PKG_NAME" == 'modules' ] && [ "$PKG_VERSION" == '3.2.10' ]; then
    PKG_URL="http://prdownloads.sourceforge.net/modules/${PKG}.tar.gz"
    BACKUP_PKG_URL="https://easybuilders.github.io/easybuild/files/${PKG}.tar.gz"
    export PATH="$PREFIX/Modules/$PKG_VERSION/bin:$PATH"
    export MOD_INIT="$PREFIX/Modules/$PKG_VERSION/init/bash"

elif [ "$PKG_NAME" == 'modules' ]; then
    PKG_URL="http://prdownloads.sourceforge.net/modules/${PKG}.tar.gz"
    export PATH="$PREFIX/bin:$PATH"
    export MOD_INIT="$PREFIX/init/bash"

elif [ "$PKG_NAME" == 'lua' ]; then
    PKG_URL="http://downloads.sourceforge.net/project/lmod/${PKG}.tar.gz"
    BACKUP_PKG_URL="https://easybuilders.github.io/easybuild/files/${PKG}.tar.gz"
    PRECONFIG_CMD="make clean"
    CONFIG_OPTIONS='--with-static=yes'
    export PATH="$PWD/$PKG:$PREFIX/bin:$PATH"

elif [ "$PKG_NAME" == 'Lmod' ]; then
    PKG_URL="https://github.com/TACC/Lmod/archive/${PKG_VERSION}.tar.gz"
    export PATH="$PREFIX/lmod/$PKG_VERSION/libexec:$PATH"
    export MOD_INIT="$PREFIX/lmod/$PKG_VERSION/init/bash"

elif [ "$PKG_NAME" == 'modules-tcl' ]; then
    # obtain tarball from upstream via http://modules.cvs.sourceforge.net/viewvc/modules/modules/?view=tar&revision=1.147
    PKG_URL="https://easybuilders.github.io/easybuild/files/modules-tcl-${PKG_VERSION}.tar.gz"
    export MODULESHOME="$PREFIX/$PKG/tcl"  # required by init/bash source script
    export PATH="$MODULESHOME:$PATH"
    export MOD_INIT="$MODULESHOME/init/bash.in"
else
    echo "ERROR: Unknown package name '$PKG_NAME'"
    exit 2
fi

echo "Installing ${PKG} @ ${PREFIX}..."
mkdir -p "${PREFIX}"
if ! wget "${PKG_URL}" && [ -n "$BACKUP_PKG_URL" ]; then
    rm -f ./*"${PKG_VERSION}".tar.gz
    wget "${BACKUP_PKG_URL}"
fi

tar xfz ./*"${PKG_VERSION}".tar.gz
rm ./*"${PKG_VERSION}".tar.gz

# environment-modules needs a patch to work with Tcl8.6
if [ "$PKG_NAME" == 'modules' ] && [ "$PKG_VERSION" == '3.2.10' ]; then
    wget -O 'modules-tcl8.6.patch' 'https://easybuilders.github.io/easybuild/files/modules-3.2.10-tcl8.6.patch'
    patch "${PKG}/cmdModule.c" modules-tcl8.6.patch
fi

if [ "$PKG_NAME" == 'modules-tcl' ]; then
    mv modules "$PREFIX/${PKG}"
else
    cd "${PKG}"
    if [[ -n "$PRECONFIG_CMD" ]]; then
        eval "${PRECONFIG_CMD}"
    fi
    ./configure $CONFIG_OPTIONS --prefix="$PREFIX" && make && make install
    cd - > /dev/null
    rm -r "${PKG}"
fi

set +eu
