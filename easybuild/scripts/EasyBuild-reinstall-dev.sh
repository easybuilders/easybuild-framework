#!/bin/bash

if [ $# -ne 1 ]
then
    echo "Usage: source <script> <installation prefix>"
else
    PREFIX=$1

    lib64path=`python -c "import distutils.sysconfig; print distutils.sysconfig.get_python_lib(prefix='$PREFIX');"`
    libpath=`echo $lib64path | sed 's/lib64/lib/g'`
    mkdir -p $libpath
    mkdir -p $lib64path

    export PYTHONPATH=$lib64path:$libpath:$PYTHONPATH
    export PATH=$PREFIX/bin:$PATH

    for pkg in easyconfigs easyblocks framework;
    do
        echo "installing easybuild-$pkg ..."
        easy_install --prefix=$PREFIX http://github.com/hpcugent/easybuild-${pkg}/archive/develop.tar.gz > $PREFIX/EB-install-${pkg}.log 2>&1
    done

    echo "Please make sure you have the following settings in place for future sessions:"
    echo "  export PYTHONPATH=$lib64path:$libpath:\$PYTHONPATH"
    echo "  export PATH=$PREFIX/bin:\$PATH"
fi
