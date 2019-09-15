#!/bin/bash

if [ $# -ne 1 ]
then
    echo "Usage: source <script> <installation prefix>"
    exit 1
else
    PREFIX=$1

    libpath=`python -c "import distutils.sysconfig; print distutils.sysconfig.get_python_lib(prefix='$PREFIX');"`
    # easy_install will install to '/lib/', even if the above specifies '/lib64/'
    if [[ $libpath =~ .*/lib64/.* ]]
    then
        libpath=`echo $libpath | sed 's/lib64/lib/g'`
    fi
    mkdir -p $libpath

    export PYTHONPATH=$libpath:$PYTHONPATH
    export PATH=$PREFIX/bin:$PATH

    for pkg in easyconfigs easyblocks framework;
    do
        logfile=$PREFIX/EasyBuild-dev-install-${pkg}.log
        echo "installing easybuild-$pkg (output goes to $logfile)..."
        easy_install --prefix=$PREFIX https://github.com/easybuilders/easybuild-${pkg}/archive/develop.tar.gz > $logfile 2>&1
        exit_code=$?
        if [ $exit_code -ne 0 ]
        then
            echo
            echo "ERROR: installation of easybuild-$pkg failed, see error messages in ${logfile}"
            exit $exit_code
        fi
    done

    set_env_script=$PREFIX/set-env-for-EasyBuild-dev.sh
    echo "# set environment for EasyBuild dev installation @ $PREFIX" > $set_env_script
    echo "# note: source this script, don't execute it" >> $set_env_script
    echo >> $set_env_script

    echo "Please make sure you have the following settings in place for future sessions:"
    echo
    echo "  export PYTHONPATH=$libpath:\$PYTHONPATH" | tee -a $set_env_script
    echo "  export PATH=$PREFIX/bin:\$PATH" | tee -a $set_env_script
    echo
    echo "Tip: just use 'source $set_env_script'"

    echo
    echo "sanity check:"; echo -n "    "
    eb --version
    ec=$?
    if [ $ec -ne 0 ]
    then
        echo "ERROR: Sanity check failed."
        exit $ec
    fi
fi
