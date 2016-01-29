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


LDWRAPPER=$EB_LD_FLAG
LDORIG=${EB_LD:-/usr/bin/ld}
LINKER=$EB_LINKER_NAME   ## not yet implemented 
EB_LD_VERBOSE=${EB_LD_VERBOSE:-false}

#######################################################

function create_symbol_array(){
  declare -A dict
  ## extract all environment vars starting with NSC_
  ## and store them in a bash dictionary.
  for i in $(env | grep NSC_)
  do
    j=(${i//=/ }) 
    j0=${j[0]}
    j1=${j[1]}
    dict[$j0]=$j1
  done

  ## *_tag variables control which symbols are
  ## written to the binary. 
  mpi_tag="0"
  mkl_tag="0"
  com_tag="0"

  #NSC_COMP, NSC_COMP_VER, NSC_COMP_BIN_PATH, NSC_COMP_LIB_PATH, 
  #NSC_MPI, NSC_MPI_VER, NSC_MPI_LIB_PATH, 
  #NSC_MKL_VER, NSC_MKL_LIB_PATH should be 
  #defined in the corresponding module file.

  ### check which components are used in actual compilation
  ### e.g., mkl may be loaded but not used in compilation 
  for key in "${!dict[@]}"
  do
    if [ "$key" == "NSC_COMP_LIB_PATH" ]; then
      if [[ "$@" =~ ${dict[$key]} ]]; then
	  com_tag="1" ## compiler is used
      fi
    elif [ "$key" == "NSC_MPI_LIB_PATH" ]; then
      if [[ "$@" =~ ${dict[$key]} ]]; then
	  mpi_tag="1" ## mpi is used 
      fi
    elif [ "$key" == "NSC_MKL_LIB_PATH" ]; then
      if [[ "$@" =~ ${dict[$key]} ]]; then
	  mkl_tag="1" ## mkl is used 
      fi
    fi
  done 

  sym_array=()
  for key in "${!dict[@]}"
  do
    val=$(echo ${dict[$key]} |sed -e 's/\./_/g')
    if [ "$key" == "NSC_COMP" ]; then
      if [ "$com_tag" == "1" ]; then 
        str="__${key}_${val}=0"
        sym_array=( "${sym_array[@]}" "$str" )
      fi
    elif [ "$key" == "NSC_COMP_VER" ]; then
      if [ "$com_tag" == "1" ]; then
        str="__NSC_COMPVER_${val}=0"
        sym_array=( "${sym_array[@]}" "$str" )
      fi
    elif [ "$key" == "NSC_MPI" ]; then
      if [ "$mpi_tag" == "1" ]; then
	str="__${key}_${val}=0"
        sym_array=( "${sym_array[@]}" "$str" )
       fi
    elif [ "$key" == "NSC_MPI_VER" ]; then
      if [ "$mpi_tag" == "1" ]; then
	str="__NSC_MPIVER_${val}=0"
        sym_array=( "${sym_array[@]}" "$str" )
       fi
    elif [ "$key" == "NSC_MKL_VER" ]; then
      if [ "$mkl_tag" == "1" ]; then
	str="__NSC_MKLVER_${val}=0"
        sym_array=( "${sym_array[@]}" "$str" )
       fi
    fi
  done
  if [ "${#sym_array[@]}" -ne 0 ]; then
    sym_array=( "${sym_array[@]}" "__NSC_TAGVER_5=0" )
    sym_array=( "${sym_array[@]}" "__NSC_BDATE_$(date +%y%m%d_%H%M%S)=0" )
  fi
  echo "${sym_array[@]}"
}

##################################################

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

  for x in $(create_symbol_array ${lib_array[@]})
  do
    sym_str="$sym_str --defsym $x"
  done

  $EB_LD_VERBOSE && echo "INFO: linking with rpath and NSC symbols"
  $LDORIG "$RPATH" "$@" "$sym_str"
 
