#!/bin/bash
##
# Copyright 2012-2014 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##

# @author: Kenneth Hoste (Ghent University)

if [ $# -ne 1 ]
then
    echo "Usage: $0 <regtest results dir <branch (e.g. develop, master)>"
    exit 1
fi
branch=$1

if [ ! -z $PBS_OWORKDIR ]
then
    cd $PBS_OWORKDIR
fi

EBHOME=$HOME/scratch/easybuild_easy_installed

# clean up old installation, prepare for new installation
echo "Cleaning up old EasyBuild installation in $EBHOME..."
rm -rf $EBHOME/*
PYLIB=`python -c "import distutils.sysconfig; print distutils.sysconfig.get_python_lib(prefix='$EBHOME');"`
mkdir -p $PYLIB

# make sure paths are set correctly in .bashrc
source ~/.bashrc
echo "Checking PYTHONPATH, PATH and MODULEPATH settings in .bashrc..."
echo $PYTHONPATH | grep "$PYLIB" &> /dev/null
if [ $? -ne 0 ]; then
    echo "Directory $PYLIB not in Python search path, please add PYTHONPATH=$PYLIB:\$PYTHONPATH to your .bashrc."
    exit 1
fi
echo $PATH | grep "$EBHOME/bin" &> /dev/null
if [ $? -ne 0 ]; then
    echo "Directory $EBHOME/bin not in PATH, please add PATH=$EBHOME/bin:\$PATH to your .bashrc.";
    exit 1;
fi
if [ "x$MODULEPATH" != "x$EASYBUILDPREFIX/modules/all" ]
then
    echo "MODULEPATH is not set correctly, please add MODULEPATH=$EASYBUILDPREFIX/modules/all to your .bashrc"
    exit 1
fi

# install EasyBuild
echo "Installing EasyBuild in $EBHOME from GitHub ($branch branch)..."
for package in easybuild-framework easybuild-easyblocks easybuild-easyconfigs
do
    echo "+++ installing $package (output, see install_${package}.out)..."
    easy_install --prefix=$EBHOME http://github.com/hpcugent/${package}/archive/${branch}.tar.gz &> install_${package}.out
    if [ $? -ne 0 ]
    then
        echo "Installation of $package failed?"
        exit 1
    fi
done

# clean up the mess from last run
echo -n "Cleaning up $EASYBUILDPREFIX... "
cd $EASYBUILDPREFIX
chmod -R 755 software  # required for e.g. WIEN2k
rm -rf software modules ebfiles_repo
cd -
echo "done"

# submit regtest
outfile="full_regtest_`date +%Y%m%d`_submission.txt"
echo "Submitting regtest, output goes to $outfile"
eb --regtest --robot -ld 2>&1 | tee $outfile

# submit trigger for Jenkins test
echo "Submitting extra job to trigger Jenkins to pull in test results when regression test is completed..."
results_dir=`grep "Submitted regression test as jobs, results in" $outfile | tail -1 | sed 's@.*/@@g'`

after_anys=`grep "Job ids of leaf nodes in dep. graph:" $outfile | tail -1 | sed 's/.*: //g' | tr ',' ':' | sed 's/^/afterany:/g'`

# submit via stdin
# note: you'll need to replace TOKEN with the actual token to allow for triggering a Jenkins test
qsub -W depend=$after_anys << EOF
cd $PWD

# aggregate results
echo "eb --aggregate-regtest=$results_dir 2>&1"
eb --aggregate-regtest=$results_dir > /tmp/aggregate-regtest.out 2>&1
ec=\$?
if [ \$ec -ne 0 ]; then echo "Failed to aggregate regtest results!"; exit \$ec; fi

fn=\`cat /tmp/aggregate-regtest.out | sed 's/.* //g'\`
datestamp=\`date +%Y%m%d\`
outfn=\`echo ~/easybuild-full-regtest_\${datestamp}.xml\`
rm -f \$outfn

# move to home dir with standard name
echo "mv \$fn \$outfn"
mv \$fn \$outfn
ec=\$?
if [ \$ec -ne 0 ]; then echo "Failed to move regtest result for Jenkins!"; exit \$ec; fi

echo "Aggregate test results made available for Jenkins in \$outfn"

# trigger Jenkins test to pull in aggregated regtest result
echo "wget https://jenkins1.ugent.be/view/EasyBuild/job/easybuild-full-regtest_$branch/build?token=TOKEN &> /dev/null"
wget https://jenkins1.ugent.be/view/EasyBuild/job/easybuild-full-regtest_$branch/build?token=TOKEN &> /dev/null
rm -f index.html index.html.*
echo "Triggered Jenkins to pull in regtest results."

EOF
