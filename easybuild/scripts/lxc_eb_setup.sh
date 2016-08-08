#!/bin/bash

# variables

# Internal
LUA_BASE_URL="http://www.lua.org/ftp/lua-"
LUAROCKS_BASE_URL="http://luarocks.org/releases/luarocks-"
LMOD_BASE_URL="https://github.com/TACC/Lmod/archive/"
EB_BASE_URL="https://github.com/hpcugent/easybuild-framework/raw/easybuild-framework-v%s/easybuild/scripts/bootstrap_eb.py"
LM_LIC_REGEX="^[/]"   # check if LM_LICENSE_FILE is a path
UBUNTU_DEBIAN_REGEX="(([Uu][Bb][Uu][Nn][Tt][Uu])|([Dd][Ee][Bb][Ii][Aa][Nn]))"

IMPORT_USER="$USER"   # user list to import
IMPORT_GROUP=""   # group list to import
IMG_NAME=""   # LXD 'launch'able image to use
CT_NAME=""   # name/alias for the new container
EPHEMERAL="yes"   # create ephemeral containers
LUA_VER="5.3.3"   # verion of lua to install into the container
LUAROCKS_VER="2.3.0"   # version of luarocks package manager to install into the container
LMOD_VER="6.3"   # version of Lmod to install into the container
EB_VER="2.8.2"   # verison of EasyBuild to bootstrap in the container
LM_LICENSE_FILE=""   # value of LM_LICENSE_FILE in container
LICENSE_FILE=""   # location on host system of actual license file, if used
TOOLCHAIN=""   # EB toolchain to pre-build in container
EB_DIR="/easybuild"   # location for EasyBuild directory tree
SOURCES_DIR=""   # location of sources to copy into container for toolchain build (like intel)
MAC_ADDR=""   # override MAC address in container (needed for host-based licensing)

# usage: lxc_eb_setup.sh <container name> <source path to app>
function usage {
  printf "\nUsage: %s [options]\n" "$0"
  printf "    %-18.18s  %-18.18s  %-s\n" "Param" "Value" "Description"
  printf "  Required:\n"
  printf "    %-18.18s  %-18.18s  %-s\n" "--image-name" "$IMG_NAME" "LXD 'launch'able image to use"
  printf "    %-18.18s  %-18.18s  %-s\n" "--container-name" "$CT_NAME" "name for the new container"
  printf "  Optional:\n"
  printf "    %-18.18s  %-18.18s  %-s\n" "--group" "None" "import group to container (will own ebdir)"
  printf "    %-18.18s  %-18.18s  %-s\n" "--user" "None" "import user to container (more than one ok)"
  printf "    %-18.18s  %-18.18s  %-s\n" "--ephemeral" "$EPHEMERAL" "create container as ephemeral (yes/no)"
  printf "    %-18.18s  %-18.18s  %-s\n" "--luaver" "$LUA_VER" "version of Lua to install into the container"
  printf "    %-18.18s  %-18.18s  %-s\n" "--luarocksver" "$LUAROCKS_VER" "verison of LuaRocks to install into the container"
  printf "    %-18.18s  %-18.18s  %-s\n" "--lmodver" "$LMOD_VER" "version of Lmod to install into the container"
  printf "    %-18.18s  %-18.18s  %-s\n" "--ebver" "$EB_VER" "version of EasyBuild to bootstrap into the container"
  printf "    %-18.18s  %-18.18s  %-s\n" "--ebdir" "$EB_DIR" "location of EasyBuild dir tree in container"
  printf "    %-18.18s  %-18.18s  %-s\n" "--lm-license-file" "$LM_LICENSE_FILE" "value to set LM_LICENSE_FILE"
  printf "    %-18.18s  %-18.18s  %-s\n" "--license-file" "$LICENSE_FILE" "path to license file to copy into container"
  printf "    %-18.18s  %-18.18s  %-s\n" "--sources-dir" "$SOURCES_DIR" "dir of sources (copied to EB_DIR/sources)"
  printf "    %-18.18s  %-18.18s  %-s\n" "--toolchain" "$TOOLCHAIN" "EB toolchain to prebuild (more than one ok)"
  printf "    %-18.18s  %-18.18s  %-s\n" "--macaddr" "$MAC_ADDR" "MAC address override in container"
  printf "\n  Note: the current user will be moved into the container, and will be used to bootstrap EasyBuild\n"
  printf "\n  If the current user is not a member of the specified group, that might be a problem.\n"
  printf "\n  Ex: %s --image-name ubuntu:14.04/amd64 --container-name eb-trusty-master --toolchain foss-2016a\n\n" "$0"
  exit 1
}
# debugging
function debug {
  printf "\t--group %s\n" "$IMPORT_GROUP"
  printf "\t--user %s\n" "$IMPORT_USER"
  printf "\t--image-name %s\n" "$IMG_NAME"
  printf "\t--container-name %s\n" "$CT_NAME"
  printf "\t--ephemeral %s\n" "$EPHEMERAL"
  printf "\t--luaver %s\n" "$LUA_VER"
  printf "\t--luarocksver %s\n" "$LUAROCKS_VER"
  printf "\t--lmodver %s\n" "$LMOD_VER"
  printf "\t--ebver %s\n" "$EB_VER"
  printf "\t--ebdir %s\n" "$EB_DIR"
  printf "\t--lm-license-file %s\n" "$LM_LICENSE_FILE"
  printf "\t--license-file %s\n" "$LICENSE_FILE"
  printf "\t--toolchain %s\n" "$TOOLCHAIN"
  printf "\t--macaddr %s\n" "$MAC_ADDR"
  exit 1
}

# check arguments
while [[ $# > 1 ]]
do
case $1 in
  --group)
  if [ -z "$IMPORT_GROUP" ]; then
    IMPORT_GROUP="$2"
  else
    IMPORT_GROUP="$IMPORT_GROUP $2"
  fi
  shift
  ;;
  --user)
  if [ -z "$IMPORT_USER" ]; then
    IMPORT_USER="$2"
  else
    IMPORT_USER="$IMPORT_USER $2"
  fi
  shift
  ;;
  --image-name)
  IMG_NAME="$2"
  shift
  ;;
  --container-name)
  CT_NAME="$2"
  shift
  ;;
  --ephemeral)
  EPHEMERAL="$2"
  shift
  ;;
  --luaver)
  LUA_VER="$2"
  shift
  ;;
  --luarocksver)
  LUAROCKS_VER="$2"
  shift
  ;;
  --lmodver)
  LMOD_VER="$2"
  shift
  ;;
  --ebver)
  EB_VER="$2"
  shift
  ;;
  --ebdir)
  EB_DIR="$2"
  shift
  ;;
  --sources-dir)
  SOURCES_DIR="$2"
  shift
  ;;
  --lm-license-file)
  LM_LICENSE_FILE="$2"
  shift
  ;;
  --license-file)
  LICENSE_FILE="$2"
  shift
  ;;
  --toolchain)
  if [ -z "$TOOLCHAIN" ]; then
    TOOLCHAIN="$2"
  else
    TOOLCHAIN="$TOOLCHAIN $2"
  fi
  shift
  ;;
  --macaddr)
  MAC_ADDR="$2"
  shift
  ;;
  *)
  usage
  ;;
esac
shift
done


# various checks
# require names
if [ -z "$IMG_NAME" ] || [ -z "$CT_NAME" ]; then
  echo "You must specify --image-name and --container-name!" 1>&2
  usage
fi
# require 'lxc'
which lxc > /dev/null 2>&1
if [ "$?" != "0" ]; then
  echo "Cannot find or execute lxc - please ensure LXD is installed and configued!" 1>&2
  exit 1
fi
# check container for existence - also check for lxc working
lxc info $CT_NAME > /dev/null 2>&1
if [ "$?" == "0" ]; then
  echo "A container called $CT_NAME seems to already exist (or 'lxc' doesn't work right)!" 1>&2
  exit 1
fi
# LICENSE_FILE w/o LM_LICENSE_FILE makes no sense
if [ -n "$LICENSE_FILE" ] && [ -z "$LM_LICENSE_FILE" ]; then
  echo "You did not specify '--lm-license-file' so I don't know where to put $LICENSE_FILE"
  exit 1
fi
# must be able to read LICENSE_FILE
if [ -n "$LICENSE_FILE" ] && [ ! -r "$LICENSE_FILE" ]; then
  echo "Cannot read $LICENSE_FILE"
  exit 1
fi
# must be able to read SOURCES_DIR
if [ -n "$SOURCES_DIR" ] && [ ! -r "$SOURCES_DIR" ]; then
  echo "Cannot read $SOURCES_DIR"
  exit 1
fi
# SOURCES_DIR must be a directory
if [ -n "$SOURCES_DIR" ] && [ ! -d "$SOURCES_DIR" ]; then
  echo "$SOURCES_DIR not a directory"
  exit 1
fi

# functions to support os-level packages
# override here to handle different package names for different OSes?
function os_pkg_update_pkgs {
  if [[ "$IMG_NAME" =~ $UBUNTU_DEBIAN_REGEX ]]; then
    lxc exec $CT_NAME --env DEBIAN_FRONTEND=noninteractive -- bash -c "apt-get update"
  else
    echo "Not an os image I recognize - unable to update OS packages!" 1>&2
    exit 1
  fi
}

# install package in OS
function os_pkg_install () {
  if [[ "$IMG_NAME" =~ $UBUNTU_DEBIAN_REGEX ]]; then
    lxc exec $CT_NAME --env DEBIAN_FRONTEND=noninteractive -- bash -c "apt-get -y install $1"
  else
    echo "Not an os image I recognize - unable to install OS package $1!" 1>&2
    exit 1
  fi
} 

# remove package using apt-get in container
function os_pkg_remove () {
  if [[ "$IMG_NAME" =~ $UBUNTU_DEBIAN_REGEX ]]; then
    lxc exec $CT_NAME --env DEBIAN_FRONTEND=noninteractive -- bash -c "apt-get -y remove --purge $1"
  else
    echo "Not an os image I recognize - unable to remove OS package $1!" 1>&2
    exit 1
  fi
} 

# common functions
# create the container
function container_create {
  if [ "$EPHEMERAL" == "yes" ]; then
    EPHERERAL_TAG="-e"
  else
    EPHEMERAL_TAG=""
  fi

  if [ -n "$MAC_ADDR" ]; then
    MAC_TAG="-c volatile.eth0.hwaddr=$MAC_ADDR"
  else
    MAC_TAG=""
  fi

  lxc launch $IMG_NAME $CT_NAME $EPHEMERAL_TAG -c security.privileged=yes $MAC_TAG
  if [ "$?" == "0" ]; then
    printf "Container %s created...\n" "$CT_NAME"
  else
    echo "Ooops, could not create container - something is wrong!" 1>&2
    exit 1
  fi
}

# check on the container

# update /etc/passwd, /etc/group in container
function user_update {
  # pull the required files - safe since we have verified the container exists
  lxc file pull $CT_NAME/etc/passwd $mydir/passwd
  lxc file pull $CT_NAME/etc/group $mydir/group

  # get user info and add it
  for u in $IMPORT_USER
  do
    # add UID
    if ! grep -q "^$u" $mydir/passwd ; then
      uinfo=$(getent passwd $u)
      echo $uinfo >> $mydir/passwd
      printf "%s" "$u "
    fi
    # add user's primary group
    g=$(id -g -n)
    if ! grep -q "^$g" $mydir/group ; then
      ginfo=$(getent group $g)
      echo $ginfo >> $mydir/group
      printf "%s" "$g "
    fi
  done
  # get group info and add it
  for g in $IMPORT_GROUP
  do
    if ! grep -q "^$g" $mydir/group ; then
      ginfo=$(getent group $g)
      echo $ginfo >> $mydir/group
      printf "%s" "$g "
    fi
    # group implies members
    ulist=$(echo $ginfo | awk -F: '{print $4}' | tr ',' ' ')
    for u in $ulist
    do
      if ! grep -q "^$u" $mydir/passwd ; then
        uinfo=$(getent passwd $u)
        echo $uinfo >> $mydir/passwd
      fi
    printf "%s" "$u "
    done
  done

  # push files back in
  lxc file push $mydir/passwd $CT_NAME/etc/passwd
  lxc file push $mydir/group $CT_NAME/etc/group
}

# install lua, luarocks, luafilesystem, and luaposix
function lua_install {

  # install readline dev package
  os_pkg_install "libreadline-dev"

  # install unzip package - apparently luarocks silently requires this
  os_pkg_install "unzip"

  # get Lua
  lua_url="${LUA_BASE_URL}$LUA_VER.tar.gz"
  wget -O $mydir/lua-$LUA_VER.tar.gz $lua_url
  if [ "$?" != "0" ]; then
    echo "Oops, retrieving lua failed!" 1>&2
    exit 1
  fi

  # push into container
  lxc file push $mydir/lua-$LUA_VER.tar.gz $CT_NAME/tmp/lua-$LUA_VER.tar.gz

  # extract in container
  lxc exec $CT_NAME -- bash -c "tar -xf /tmp/lua-$LUA_VER.tar.gz -C /tmp"

  # build and install in container
  lxc exec $CT_NAME -- bash -c "cd /tmp/lua-$LUA_VER && make linux install"

  # get luarocks
  luarocks_url="${LUAROCKS_BASE_URL}$LUAROCKS_VER.tar.gz"
  wget -O $mydir/luarocks-$LUAROCKS_VER.tar.gz $luarocks_url
  if [ "$?" != "0" ]; then
    echo "Oops, retrieving luarocks failed!" 1>&2
    exit 1
  fi

  # push into container
  lxc file push $mydir/luarocks-$LUAROCKS_VER.tar.gz $CT_NAME/tmp/luarocks-$LUAROCKS_VER.tar.gz

  # extract in container
  lxc exec $CT_NAME -- bash -c "tar -xf /tmp/luarocks-$LUAROCKS_VER.tar.gz -C /tmp"

  # build and install in container
  lxc exec $CT_NAME -- bash -c "cd /tmp/luarocks-$LUAROCKS_VER && ./configure && make build && make install"

  # use luarocks to install luaposix and luafilesystem
  lxc exec $CT_NAME -- bash -c "luarocks install luaposix; luarocks install luafilesystem"

  # uninstall libreadline-dev for a clean system
  os_pkg_remove "libreadline-dev"
}

# install Lmod
function lmod_install {

  # install Tcl 
  os_pkg_install "tcl"

  # get Lmod
  lmod_url="${LMOD_BASE_URL}$LMOD_VER.tar.gz"
  wget -O $mydir/Lmod-$LMOD_VER.tar.gz $lmod_url
  if [ "$?" != "0" ]; then
    echo "Oops, retrieving Lmod failed!" 1>&2
    exit 1
  fi

  # push into container
  lxc file push $mydir/Lmod-$LMOD_VER.tar.gz $CT_NAME/tmp/Lmod-$LMOD_VER.tar.gz

  # extract in container
  lxc exec $CT_NAME -- bash -c "tar -xf /tmp/Lmod-$LMOD_VER.tar.gz -C /tmp"

  # build and install in container
  lxc exec $CT_NAME -- bash -c "cd /tmp/Lmod-$LMOD_VER && ./configure && make install"

  # build an /etc/profile.d init script to set MODULEPATH and inin Lmod
  (cat <<EOF
#!/bin/bash

LMOD_DIR=/usr/local/lmod/lmod

if [ -n "\$BASH_VERSION" ]; then
  export PATH=\$PATH:\$LMOD_DIR/libexec/
  export MODULEPATH=$EB_DIR/modules/all
  export BASH_ENV=\$LMOD_DIR/init/bash
  source \$BASH_ENV
fi
EOF
) > $mydir/bash_lmod_init.sh
  lxc file push $mydir/bash_lmod_init.sh $CT_NAME/etc/profile.d/bash_lmod_init.sh
  
}

# bootstrap easybuild
function eb_bootstrap {

  # get EB
  eb_url=$(printf "$EB_BASE_URL" "$EB_VER")
  wget -O $mydir/bootstrap_eb.py $eb_url
  if [ "$?" != "0" ]; then
    echo "Oops, retrieving bootstrap_eb.py failed!" 1>&2
    exit 1
  fi

  # push into container
  lxc file push $mydir/bootstrap_eb.py $CT_NAME/tmp/bootstrap_eb.py

  # create $EB_DIR
  lxc exec $CT_NAME -- bash -c "mkdir -p $EB_DIR"

  # fix up permissions for EB_DIR
  lxc exec $CT_NAME -- bash -c "chown -R $IMPORT_USER $EB_DIR"
  if [ -n "$IMPORT_GROUP" ]; then
    lxc exec $CT_NAME -- bash -c "chgrp -R $IMPORT_GROUP $EB_DIR"
    lxc exec $CT_NAME -- bash -c "chmod g+w $EB_DIR"
    lxc exec $CT_NAME -- bash -c "chmod g+s $EB_DIR"
  fi

  # bootstrap it as $IMPORT_USER
  lxc exec $CT_NAME -- su -s /bin/bash -c "python /tmp/bootstrap_eb.py $EB_DIR" - $IMPORT_USER

  # pop in some useful environment variables to our EasyBuild modulefile
  # pull the EB modulefile out of the container
  lxc file pull $CT_NAME/$EB_DIR/modules/all/EasyBuild/$EB_VER $mydir/eb-$EB_VER.lmod
  (cat <<EOF
set ebDir "$EB_DIR"
setenv EASYBUILD_SOURCEPATH "\$ebDir/sources"
setenv EASYBUILD_BUILDPATH "\$ebDir/build"
setenv EASYBUILD_INSTALLPATH_SOFTWARE "\$ebDir/software"
setenv EASYBUILD_INSTALLPATH_MODULES "\$ebDir/modules"
setenv EASYBUILD_REPOSITORYPATH "\$ebDir/ebfiles_repo"
setenv EASYBUILD_LOGFILE_FORMAT "\$ebDir/logs,easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log"
setenv EASYBUILD_MODULES_TOOL "Lmod"
EOF
  ) >> $mydir/eb-$EB_VER.lmod

  # if IMPORT_GROUP, set up for group use
  if [ -n "$IMPORT_GROUP" ] ; then
    (cat <<EOF
# keep group writable bit
setenv EASYBUILD_GROUP_WRITABLE_INSTALLDIR 1
# set umask to preserve group write permissions on modulefiles
setenv EASYBUILD_UMASK 002
EOF
    ) >> $mydir/eb-$EB_VER.lmod
  fi

  # if we match Ubuntu or Debian - icc does not look here by default
  # making 64-bit assumption...ok?
  if [[ $IMG_NAME =~ $UBUNTU_DEBIAN_REGEX ]]; then
    (cat <<EOF
# tell compilers about Ubuntu/Debian include arch
setenv C_INCLUDE_PATH "/usr/include/x86_64-linux-gnu"
setenv CPLUS_INCLUDE_PATH "/usr/include/x86_64-linux-gnu"
EOF
    ) >> $mydir/eb-$EB_VER.lmod
  fi

  # add LM_LICENSE_FILE value to modulefile
  if [ -n "$LM_LICENSE_FILE" ]; then
    (cat <<EOF
# find our licenses
setenv LM_LICENSE_FILE "$LM_LICENSE_FILE"
EOF
    ) >> $mydir/eb-$EB_VER.lmod
  fi

  # put LICENSE_FILE in the container and fix up permissions
  if [ -n "$LICENSE_FILE" ] && [[ $LM_LICENSE_FILE =~ $LM_LIC_REGEX ]]; then
    # create the directory for the license file
    LM_LIC_DIR=$(dirname $LM_LICENSE_FILE)
    lxc exec $CT_NAME -- bash -c "mkdir -p $LM_LIC_DIR"
    lxc file push $LICENSE_FILE $CT_NAME/$LM_LICENSE_FILE
    lxc exec $CT_NAME -- bash -c "chown -R $IMPORT_USER $LM_LIC_DIR"
    if [ -n "$IMPORT_GROUP" ]; then
      lxc exec $CT_NAME -- bash -c "chgrp -R $IMPORT_GROUP $LM_LIC_DIR"
    fi
  fi

  # copy in sources
  if [ -n "$SOURCES_DIR" ]; then
    lxc exec $CT_NAME -- bash -c "mkdir -p $EB_DIR/sources"
    for file in $(ls $SOURCES_DIR)
    do
      lxc file push $SOURCES_DIR/$file $CT_NAME/$EB_DIR/sources/$file
    done
    # fix up permissions
    lxc exec $CT_NAME -- bash -c "chown -R $IMPORT_USER $EB_DIR/sources"
    if [ -n "$IMPORT_GROUP" ]; then
      lxc exec $CT_NAME -- bash -c "chgrp -R $IMPORT_GROUP $EB_DIR/sources"
    fi
  fi

  # push the modified modulefile back into the container
  lxc file push $mydir/eb-$EB_VER.lmod $CT_NAME/$EB_DIR/modules/all/EasyBuild/$EB_VER

}

function toolchain_install () {

  IB_TC_REGEX="^(foss|intel)"
  if [[ $1 =~ $IB_TC_REGEX ]]; then
    printf "Installing libibverbs as most MPI toolchains need this...\n"
    os_pkg_install "libibverbs-dev"
  fi
  
  HOME_TC_REGEX="^intel"
  if [[ $1 =~ $HOME_TC_REGEX ]]; then
    printf "%s toolchain requires a user home directory for install - creating now..." "$1"
    lxc exec $CT_NAME -- bash -c "mkdir /home/$IMPORT_USER && cp -a /etc/skel /home/$IMPORT_USER && chown -R $IMPORT_USER /home/$IMPORT_USER"
  fi

  # finally, build the toolchain
  lxc exec $CT_NAME -- su -s /bin/bash -c "module load EasyBuild && eb $1.eb --robot" - $IMPORT_USER

}

function eb_fix_perms () {

  lxc exec $CT_NAME -- bash -c "chgrp -R $IMPORT_GROUP $EB_DIR"
  lxc exec $CT_NAME -- bash -c "chmod -R g+w $EB_DIR"

function sign_container () {

 (cat <<EOF
$*
EOF
    ) >> $mydir/lxc_eb_setup.sh_cmdline
  lxc file push $mydir/lxc_eb_setup.sh_cmdline $CT_NAME
  lxc file push $0 $CT_NAME
}  

# main

# set up temp dir
mydir=$(mktemp -d)

printf "Creating new container %s from image %s...\n" "$CT_NAME" "$IMG_NAME"
container_create
printf "Pausing for station identification (DNS to start working)...\n"
sleep 5
printf "Updating users and groups in %s..." "$CT_NAME"
user_update
printf "\nUpdating packages..."
os_pkg_update_pkgs
printf "Installing build-essential..."
os_pkg_install "build-essential"
printf "Ensuring python2 is installed..."
os_pkg_install "python-minimal"
printf "Ensuring python-pygraph is installed (for dependency graphs)..."
os_pkg_install "python-pygraph"
printf "\nInstalling Lua...\n"
lua_install
printf "Installing Lmod...\n"
lmod_install
printf "Bootstrapping EasyBuild...\n"
eb_bootstrap
for tc in $TOOLCHAIN
do
  printf "Building toolchain %s..." "$tc"
  toolchain_install "$tc"
done
printf "Fixing up perms...\n"
eb_fix_perms
printf "Signing conatiner...\n"
sign_container
printf "\nAll done - begin using your EasyBuild container by running:\n"
printf "\n\tlxc exec %s -- su -s /bin/bash - %s" "$CT_NAME" "$IMPORT_USER"
printf "\nMap a directory like this:\n"
printf "\n\tlxc config device add %s <device_name> disk path=<path in container> source=<path on host>\n" "$CT_NAME"
rm -rf $mydir
exit 0
