#!/bin/bash
#
# Chandan Basu, cbasu@nsc.liu.se.
# Consider this piece of script GPL.
#
# Time-stamp: <2015-02-12 16:00:00>

# This is a linker-wrapper.
#
# The wrapped linker gets lib paths from compiler
# (e.g., gcc, gfortran, icc, ifort etc.) and adds
# rpaths to binary.

SCRIPTNAME=$(basename $0)

LDWRAPPER=$EB_LD_FLAG
LDORIG=${EB_LD:-/bin/$SCRIPTNAME}
LINKER=$EB_LINKER_NAME   ## not yet implemented
EB_LD_VERBOSE=${EB_LD_VERBOSE:-false}


$EB_LD_VERBOSE && echo "INFO: linking with rpath "

  if [ -z "$LDWRAPPER" ] || [ "$LDWRAPPER" == 0 ]; then
## call the system linker
    $LDORIG "$@"
    exit
  elif [ "$LDWRAPPER" == 1 ]; then
## Default rpath-ing option.
    exclude_lib_paths=("/lib" "/lib64" "/usr" "/home" "/tmp" "/opt" "/proj")
  elif [ "$LDWRAPPER" == 2 ]; then
## More aggressive rpath-ing
    exclude_lib_paths=("/tmp" "/opt")
  fi

  L=""
  lib_array=()
  dir=`pwd`
  for (( i=${#@}; i >= 0; i-- )); do
    if [[ ${!i} == "--enable-new-dtags" ]]; then
	## we are removing this flag if passed as it creates a copy of rpath to runpath.
	## If runpath exists in the binary it can be controlled by LD_LIBRARY_PATH.
	## We want only rpath in the binary and no runpath.
	## If the user wants to use runpath he should disable linker warpper
	## by using EB_LD_FLAG=0
        set -- "${@:1:$(( $i - 1 ))}" "${@:$(( $i + 1 ))}"
    fi
  done

  for i in `echo $*`
  do
    x=`echo $i| cut -c -3`
    if [ "$x" == "-L/"  -o  "$x" == "-L." ] ; then
      x=`echo $i| cut -c 3-`
      if [ -d "$x" ]; then
        p=`cd $x; pwd -P`
        lib_array=( "${lib_array[@]}" "$p" )
      fi
    fi
  done

  lib_array=( $(for x in "${lib_array[@]}"
            do
              echo "$x"
            done | sort -u) )

  for y in "${exclude_lib_paths[@]}"
  do
    lib_array=( $(for x in "${lib_array[@]}"
    do
      if [[ "${x:0:${#y}}" != "$y" ]]; then
        echo "$x"
      fi
    done))
  done

  #### check extra libpaths and add to the lib_array ####
  extra_lib_paths=(${NSC_LD_EXTRA_LIBPATH//:/ })
  lib_array=( "${lib_array[@]}" "${extra_lib_paths[@]}" )
  #######################################################

  RPATH=""
  for x in "${lib_array[@]}"
  do
    if [ "$RPATH" == "" ]; then
      L=$x
      RPATH="-rpath=$x"
    else
      L=$L:$x
      RPATH="$RPATH -rpath=$x"
    fi
  done

  sym_str=""

  $EB_LD_VERBOSE && echo "INFO: linking with rpath and NSC symbols "
  $EB_LD_VERBOSE && echo "INFO: RPATH : $RPATH sym_str: $sym_str @: $@ ::"
  $LDORIG "$RPATH" "$@"
