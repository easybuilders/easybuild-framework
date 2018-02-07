#!/bin/bash

set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <name>-<version> <prefix>"
    exit 1
fi
PKG=$1
PREFIX=$2

PKG_NAME=`echo $PKG | sed 's/-[^-]*$//g'`
PKG_VERSION=`echo $PKG | sed 's/.*-//g'`

CONFIG_OPTIONS=
PRECONFIG_CMD=

if [ x$PKG_NAME == 'xmodules' ] && [ x$PKG_VERSION == 'x3.2.10' ]; then
    PKG_URL="http://prdownloads.sourceforge.net/modules/${PKG}.tar.gz"
    BACKUP_PKG_URL="https://easybuilders.github.io/easybuild/files/${PKG}.tar.gz"
    export PATH=$PREFIX/Modules/$PKG_VERSION/bin:$PATH
    export MOD_INIT=$HOME/Modules/$PKG_VERSION/init/bash

elif [ x$PKG_NAME == 'xmodules' ]; then
    PKG_URL="http://prdownloads.sourceforge.net/modules/${PKG}.tar.gz"
    export PATH=$PREFIX/bin:$PATH
    export MOD_INIT=$HOME/init/bash

elif [ x$PKG_NAME == 'xlua' ]; then
    PKG_URL="http://downloads.sourceforge.net/project/lmod/${PKG}.tar.gz"
    BACKUP_PKG_URL="https://easybuilders.github.io/easybuild/files/${PKG}.tar.gz"
    PRECONFIG_CMD="make clean"
    CONFIG_OPTIONS='--with-static=yes'
    export PATH=$PWD/$PKG:$PREFIX/bin:$PATH

elif [ x$PKG_NAME == 'xLmod' ]; then
    PKG_URL="https://github.com/TACC/Lmod/archive/${PKG_VERSION}.tar.gz"
    export PATH=$PREFIX/lmod/$PKG_VERSION/libexec:$PATH
    export MOD_INIT=$HOME/lmod/$PKG_VERSION/init/bash

elif [ x$PKG_NAME == 'xmodules-tcl' ]; then
    # obtain tarball from upstream via http://modules.cvs.sourceforge.net/viewvc/modules/modules/?view=tar&revision=1.147
    PKG_URL="https://easybuilders.github.io/easybuild/files/modules-tcl-${PKG_VERSION}.tar.gz"
    export MODULESHOME=$PREFIX/$PKG/tcl  # required by init/bash source script
    export PATH=$MODULESHOME:$PATH
    export MOD_INIT=$MODULESHOME/init/bash.in
else
    echo "ERROR: Unknown package name '$PKG_NAME'"
    exit 2
fi

echo "Installing ${PKG} @ ${PREFIX}..."
mkdir -p ${PREFIX}
set +e
wget ${PKG_URL} && tar xfz *${PKG_VERSION}.tar.gz
if [ $? -ne 0 ] && [ ! -z $BACKUP_PKG_URL ]; then
    rm -f *${PKG_VERSION}.tar.gz
    wget ${BACKUP_PKG_URL} && tar xfz *${PKG_VERSION}.tar.gz
fi
set -e

# environment-modules needs a patch to work with Tcl8.6
if [ x$PKG_NAME == 'xmodules' ] && [ x$PKG_VERSION == 'x3.2.10' ]; then
    wget -O 'modules-tcl8.6.patch' 'https://easybuilders.github.io/easybuild/files/modules-3.2.10-tcl8.6.patch'
    patch ${PKG}/cmdModule.c modules-tcl8.6.patch
fi

if [ x$PKG_NAME == 'xmodules-tcl' ]; then
    mv modules $PREFIX/${PKG}
else
    cd ${PKG}
    if [[ ! -z $PRECONFIG_CMD ]]; then
        eval ${PRECONFIG_CMD}
    fi
    ./configure $CONFIG_OPTIONS --prefix=$PREFIX && make && make install
fi
