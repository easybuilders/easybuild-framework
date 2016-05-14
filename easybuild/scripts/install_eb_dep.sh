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

if [ x$PKG_NAME == 'xmodules' ]; then
    PKG_URL="http://prdownloads.sourceforge.net/modules/${PKG}.tar.gz"
    export PATH=$PREFIX/Modules/$PKG_VERSION/bin:$PATH
    export MOD_INIT=$HOME/Modules/$PKG_VERSION/init/bash

elif [ x$PKG_NAME == 'xlua' ]; then
    PKG_URL="http://downloads.sourceforge.net/project/lmod/${PKG}.tar.gz"
    CONFIG_OPTIONS='--with-static=yes'
    export PATH=$PREFIX/bin:$PATH

elif [ x$PKG_NAME == 'xLmod' ]; then
    PKG_URL="https://github.com/TACC/Lmod/archive/${PKG_VERSION}.tar.gz"
    export PATH=$PREFIX/lmod/$PKG_VERSION/libexec:$PATH
    export MOD_INIT=$HOME/lmod/$PKG_VERSION/init/bash

elif [ x$PKG_NAME == 'xmodules-tcl' ]; then
    # obtain tarball from upstream via http://modules.cvs.sourceforge.net/viewvc/modules/modules/?view=tar&revision=1.147
    PKG_URL="http://hpcugent.github.io/easybuild/files/modules-tcl-${PKG_VERSION}.tar.gz"
    export MODULESHOME=$PREFIX/$PKG/tcl  # required by init/bash source script
    export PATH=$MODULESHOME:$PATH
    export MOD_INIT=$MODULESHOME/init/bash.in
else
    echo "ERROR: Unknown package name '$PKG_NAME'"
    exit 2
fi

echo "Installing ${PKG} @ ${PREFIX}..."
mkdir -p ${PREFIX}
wget ${PKG_URL} && tar xfz *${PKG_VERSION}.tar.gz
if [ x$PKG_NAME == 'xmodules-tcl' ]; then
    mv modules $PREFIX/${PKG}
else
    cd ${PKG} && ./configure $CONFIG_OPTIONS --prefix=$PREFIX && make && make install
fi
