#!/bin/bash

if [ $# -ne 1 ]
then
    echo "Usage: source <script> <installation prefix>"
else
    PREFIX=$1

    libpath=`python -c "import distutils.sysconfig; print distutils.sysconfig.get_python_lib(prefix='$PREFIX');"`
    mkdir -p $libpath

    export PYTHONPATH=$libpath:$PYTHONPATH
    export PATH=$PREFIX/bin:$PATH

    for pkg in easyconfigs easyblocks framework;
    do
        echo "installing easybuild-$pkg ..."
        easy_install --prefix=$PREFIX http://github.com/hpcugent/easybuild-${pkg}/archive/develop.tar.gz > $PREFIX/EB-install-${pkg}.log 2>&1
    done

    echo "Please make sure you have the following settings in place for future sessions:"
    echo "  export PYTHONPATH=$libpath:\$PYTHONPATH"
    echo "  export PATH=$PREFIX/bin:\$PATH"
fi
