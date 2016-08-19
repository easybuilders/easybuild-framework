#!/usr/bin/env bash

##### Set any variables #####
tclmod_url='https://sourceforge.net/p/modules/modules-tcl/ci/master/tree/modulecmd.tcl?format=raw'
# Allow the user to set the Python version via an ENVVAR
if [ -z ${INSTALL_PYTHON_VERSION+x} ]; then
  # Unset this variable if you don't want a custom python at all
  INSTALL_PYTHON_VERSION='2.7.12'
fi
# There are our python module dependencies
setuptools_version='25.2.0'
setuptools_version_url='https://pypi.python.org/packages/9f/32/81c324675725d78e7f6da777483a3453611a427db0145dfb878940469692/setuptools-25.2.0.tar.gz#md5=a0dbb65889c46214c691f6c516cf959c'
vscinstall_version='0.10.11'
vscinstall_version_url='https://pypi.python.org/packages/03/d0/291da76d7da921cf8e70dd7db79b0838e0f633655e8f2dd06093d99ce851/vsc-install-0.10.11.tar.gz'
# Where do we get the EasyBuild bootstrap script
#eb_bootstrap_url='https://raw.githubusercontent.com/hpcugent/easybuild-framework/develop/easybuild/scripts/bootstrap_eb.py'
eb_bootstrap_url='https://raw.githubusercontent.com/ocaisa/easybuild-framework/d2734f33613332ff283b24faabd84a727d7883f9/easybuild/scripts/bootstrap_eb.py'
distribute_url='http://hpcugent.github.io/easybuild/files/distribute-0.6.49-patched1.tar.gz' # Needs to be downloaded for an offline install

##### Define the functions we use #####
# Check a program exists on the system
function check_program_exists {
  command -v $1 >/dev/null 2>&1 || { echo >&2 "I require $1 but it's not installed.  Aborting."; exit 1; }
}

function download_file {
  check_program_exists wget
  wget $1
  if [ "$?" != 0 ]; then
    echo "Command"
    echo "  wget $1"
    echo "failed. You might have an internet connectivity problem"
    exit 1
  fi
}

# Install a Python module in our new Python installation
function install_python_module {
  module_name=$1
  module_version=$2
  download_url=$3
  working_dir=$(pwd)
  target_dir=$4
  sources=$5

  # Log the output of the python install
  mkdir -p $target_dir/logs
  pythonm_stdout=$target_dir/logs/python_${module_name}_install_stdout.log
  pythonm_stderr=$target_dir/logs/python_${module_name}_install_stderr.log

  echo
  echo "Installing the requested Python module ${module_name}-${module_version} and storing stdout in" 
  echo "  $pythonm_stdout"
  echo "and stderr in"
  echo "  $pythonm_stderr"
  echo
  echo
  if [ ! -f $sources/${module_name}-${module_version}.tar.gz ] ; then
    mkdir -p $sources
    cd $sources
    download_file $download_url
    cd $target_dir
  fi
  mkdir -p $target_dir/tempPythonModule
  cd $target_dir/tempPythonModule
  tar zxf $sources/${module_name}-${module_version}.tar.gz >> $pythonm_stdout 2>> $pythonm_stderr
  cd ${module_name}-${module_version}
  # Install in the same location as our (new) python installation
  python setup.py install --prefix=${target_dir}/Python/ >> $pythonm_stdout 2>> $pythonm_stderr
  
  # Clean up
  cd ${working_dir}
  rm -rf $target_dir/tempPythonModule
}


# Install our own Python version, in a Python subdir of the target
function install_python {
  python_version=$1
  working_dir=$(pwd)
  target_dir=$2
  sources=$3
 
  # Log the output of the python install
  mkdir -p $target_dir/logs
  python_stdout=$target_dir/logs/python_install_stdout.log
  python_stderr=$target_dir/logs/python_install_stderr.log
  echo
  echo "Installing the requested version of Python and storing stdout in" 
  echo "  $python_stdout"
  echo "and stderr in"
  echo "  $python_stderr"
  echo
  echo
  cd $target_dir
  if [ ! -f $sources/Python-${python_version}.tgz ] ; then
    mkdir -p $sources
    cd $sources
    download_file 'https://www.python.org/ftp/python/'$python_version'/Python-'$python_version'.tgz'
    cd $target_dir
  fi

  mkdir -p $target_dir/tempPython
  cd $target_dir/tempPython
  tar zxf $sources/Python-$python_version.tgz > $python_stdout 2> $python_stderr
  cd Python-${python_version}
  # Install in our target location in a Python subdir
  ./configure --prefix=${target_dir}/Python >> $python_stdout 2>> $python_stderr
  if [ "$?" != 0 ]; then
    echo "Command"
    echo "  configure --prefix=$wd/Python"
    echo "failed in directory $(pwd). Please check the output"
    exit 1
  else
    make >> $python_stdout 2>> $python_stderr && \
      make install >> $python_stdout 2>> $python_stderr
  fi

  # Clean up
  cd ${working_dir}
  rm -rf $target_dir/tempPython
}

##### START THE REAL WORK #####
echo
echo This script is intended for installing Python, EasyBuild and Lmod in a bash environment
echo If that\'s not the shell you use then it may not work properly for you!
echo
echo

check_program_exists "readlink"
# Grab location of this script
this_script=$(readlink -m $0)

# Set the installation directory
if [ "$#" -gt 1 ]; then
  echo "Illegal number of parameters"
  echo "Expecting path of target directory only"
  exit 1
fi
if [ -z "$1" ] ; then 
  echo "No argument supplied, you must supply a target directory to use as an EasyBuild prefix:"
  echo "  $0 <Target Directory>"
  echo
  exit 1
else
  ROOT_INSTALL_DIR=$(readlink -m $1)
fi

mkdir -p $ROOT_INSTALL_DIR
# Check we have write permissions there and change to that directory
if [ -w $ROOT_INSTALL_DIR ] ; then 
  echo "Using $ROOT_INSTALL_DIR as your \$EASYBUILD_PREFIX"
  echo 
else
  echo "You do not have permission to write to $ROOT_INSTALL_DIR"
  echo "Please use an argument to the script to give the path of your target!"
  echo "(or move to a directory where you have write permissions)"
  exit 1
fi
# Change directory
echo Moving to installation directory:
pushd $ROOT_INSTALL_DIR
echo

# Set up a sources directory for this script
if [ -z ${EASYBUILD_BOOTSTRAP_SOURCEPATH+x} ]; then
  sources=$ROOT_INSTALL_DIR/sources/bootstrap_script
else
  sources=$(readlink -m $EASYBUILD_BOOTSTRAP_SOURCEPATH)
fi
mkdir -p $sources


# If requested install our own Python version
if [ -z ${INSTALL_PYTHON_VERSION+x} ]; then 
  echo "Please set the environment variable INSTALL_PYTHON_VERSION to a valid python version"
  echo "if you would like to install and use a custom python installation"
  echo "...continuing with system python $(which python)"
else 
  # Check it's Python 2, no support for Python 3 yet
  py_maj_ver=${INSTALL_PYTHON_VERSION:0:1}
  if [ $py_maj_ver -eq 2 ]; then 
    install_python $INSTALL_PYTHON_VERSION $ROOT_INSTALL_DIR $sources
    # Put the new Python in our path
    export PYTHONPATH=$ROOT_INSTALL_DIR/Python/lib:$PYTHONPATH
    export PATH=$ROOT_INSTALL_DIR/Python/bin:$PATH
  else
    echo Only support for Python2 in EasyBuild!
    echo Please choose a different version in your INSTALL_PYTHON_VERSION envvar...exiting
    exit 1
  fi
  # Install the minimal requirements of EasyBuild
  install_python_module setuptools $setuptools_version $setuptools_version_url $ROOT_INSTALL_DIR $sources
  install_python_module vsc-install $vscinstall_version $vscinstall_version_url $ROOT_INSTALL_DIR $sources

  # TODO: In theory the below is true but because the bootstrap empties our PYTHONPATH it doesn't work
  # With our Python and modules, it should be safe to skip Stage0 of the EasyBuild bootstrap
  # export EASYBUILD_BOOTSTRAP_SKIP_STAGE0=1  
fi

# Test that we have essential things
check_program_exists "python"
check_program_exists "tclsh"
check_program_exists "awk"
check_program_exists "tee"
check_program_exists "grep"
check_program_exists "tail"

# Do any necessary downloading
if [ ! -f $sources/TCL_MOD/modulecmd.tcl ] ; then
  mkdir -p $sources/TCL_MOD
  cd $sources
  # Grab the file from sourceforge
  download_file $tclmod_url
  # It has a funky name because of the URL, let's rename appropriately
  mv modulecmd.tcl*raw $sources/TCL_MOD/modulecmd.tcl
fi
chmod +x $sources/TCL_MOD/modulecmd.tcl 
export PATH=$PATH:$sources/TCL_MOD
eval `tclsh $(which modulecmd.tcl) sh autoinit`

echo "Installing EasyBuild using EasyBuild bootstrapping script"
if [ ! -f $sources/bootstrap_eb.py ] ; then
  cd $sources
  download_file $eb_bootstrap_url
  cd $ROOT_INSTALL_DIR
fi
# Log the output of the bootstrapping and grab the change that needs to be made to the MODULEPATH
mkdir -p $ROOT_INSTALL_DIR/logs
eb_boot_stdout=$ROOT_INSTALL_DIR/logs/eb_bootstrap_stdout.log
eb_boot_stderr=$ROOT_INSTALL_DIR/logs/eb_bootstrap_stderr.log
echo
echo "Bootstrapping EasyBuild and storing stdout in" 
echo "  $eb_boot_stdout"
echo "and stderr in"
echo "  $eb_boot_stderr"
echo
echo

export EASYBUILD_PREFIX=$ROOT_INSTALL_DIR
new_module_path=$(python $sources/bootstrap_eb.py $EASYBUILD_PREFIX > >(tee $eb_boot_stdout) 2> >(tee $eb_boot_stderr) |grep MODULEPATH|awk '{print $NF}')
if [ "$?" != 0 ]; then
  echo "ERROR: The easybuild bootstrap command has failed, you need to check the logs:"
  echo "  $eb_boot_stdout"
  echo "  $eb_boot_stderr"
  exit 1
fi

# If bootstrap sources variable is set, unset it
bootstrap_sources_set=0
if [ ! -z ${EASYBUILD_BOOTSTRAP_SOURCEPATH+x} ]; then
  bootstrap_sources_set=1
  unset EASYBUILD_BOOTSTRAP_SOURCEPATH
fi

# If skip Stage0 variable is set, unset it
if [ ! -z ${EASYBUILD_BOOTSTRAP_SKIP_STAGE0+x} ]; then
  unset EASYBUILD_BOOTSTRAP_SKIP_STAGE0
fi


# Set the MODULEPATH to our newly installed modules (we don't care about other system modules)
export MODULEPATH=$new_module_path

echo Loading EasyBuild and using to install Lmod
echo
# Load EasyBuild and set necessary options
module load EasyBuild
export EASYBUILD_MODULES_TOOL=EnvironmentModulesTcl
export EASYBUILD_ROBOT=$EASYBUILD_ROBOT: 
# Install the most recent working version of Lmod at the dummy level
lmod_easyconfig=$(eb --allow-modules-tool-mismatch --search ^Lmod-[^-]*$ |grep Lmod|tail -1 |awk '{print $NF}')
# Move to the sources directory in case we are offline and need to find sources
cd $sources
# Potentially could install Lmod to another path, so that the default view isn't cluttered
eb --allow-modules-tool-mismatch $lmod_easyconfig
module load Lmod

# Let's gather the remaining sources in case someone wants to do an offline installation
if [ $bootstrap_sources_set -eq 0 ]; then
  echo
  echo
  echo Gathering sources in case you would like to do an offline installation in future.
  echo

  # The EB sources are somewhere else so need to redownload them
  eb --allow-modules-tool-mismatch --stop fetch --force $EBROOTEASYBUILD/easybuild/Easy*.eb
  # Find all sources EB downloaded and copy them to our own sources directory
  ls $ROOT_INSTALL_DIR/sources/*/*/*|grep -v .tcl|xargs -i cp {} $sources
  # I don't see any way around doing this manually, this is required by the bootstrap script
  cd $sources
  download_file $distribute_url
  # Finally let's add this script to that path so everything is self-contained
  cp $this_script $sources
  echo
  echo You can now perform an offline install simply by making a copy of the directory
  echo "  $sources"
  echo on the remote host, entering the directory on the remote host and then running:
  check_program_exists "basename"
  echo "  EASYBUILD_BOOTSTRAP_SOURCEPATH=\$(pwd) ./$(basename $this_script) <Target Directory>"
fi

echo
echo
echo --------------------------------------------------------------------------------
echo \# Add the following to your .bashrc
echo --------------------------------------------------------------------------------
# If requested include the python definition
if [ ! -z ${INSTALL_PYTHON_VERSION+x} ]; then 
  # Put the new Python in our path
  echo export PYTHONPATH=$ROOT_INSTALL_DIR/Python/lib:\$PYTHONPATH
  echo export PATH=$ROOT_INSTALL_DIR/Python/bin:\$PATH
  echo export PYTHONPATH=$ROOT_INSTALL_DIR/Python/lib:\$PYTHONPATH > $ROOT_INSTALL_DIR/source_me
  echo export PATH=$ROOT_INSTALL_DIR/Python/bin:\$PATH >> $ROOT_INSTALL_DIR/source_me
fi
#
echo export EASYBUILD_MODULES_TOOL=Lmod
echo export EASYBUILD_PREFIX=$EASYBUILD_PREFIX
echo export MODULEPATH=$new_module_path:\$MODULEPATH
echo . $EBROOTLMOD/lmod/lmod/init/bash
echo . $EBROOTLMOD/lmod/lmod/init/lmod_bash_completions 
echo export EASYBUILD_MODULES_TOOL=Lmod >> $ROOT_INSTALL_DIR/source_me
echo export EASYBUILD_PREFIX=$EASYBUILD_PREFIX >> $ROOT_INSTALL_DIR/source_me
echo export MODULEPATH=$new_module_path:\$MODULEPATH >> $ROOT_INSTALL_DIR/source_me
echo . $EBROOTLMOD/lmod/lmod/init/bash >> $ROOT_INSTALL_DIR/source_me
echo . $EBROOTLMOD/lmod/lmod/init/lmod_bash_completions >> $ROOT_INSTALL_DIR/source_me
echo --------------------------------------------------------------------------------
echo
echo
echo If you use another type of shell you will need to adjust the above lines!!!
echo
echo
echo You can also:
echo "  source $ROOT_INSTALL_DIR/source_me"
echo if only wish to use this installation in a particular shell
echo


# In case this file was sourced, do a popd
echo Exiting the installation directory
popd
