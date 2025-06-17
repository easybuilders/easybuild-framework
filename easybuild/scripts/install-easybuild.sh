#!/bin/bash

## Install EasyBuild and create a file "setup-env.sh" to use it

# Examples:
#
# To install latest stable release to /tmp/eb-stable
# ./install-easybuild.sh /tmp/eb-stable stable
#
# To install latest devel release to /tmp/eb-devel
# ./install-easybuild.sh /tmp/eb-devel develop

if [ $# -ne 2 ]
then
    echo "Usage: $0 <full install path> <stable|develop>"
    exit 1
fi

if [ "$2" != "stable" ] && [ "$2" != "develop" ]
then
    echo "Branch name must be stable or develop"
    echo "Usage: $0 <full install path> <stable|develop>"
    exit 1
fi

INSTALL_DIR=`readlink -f $1`
BRANCH=$2
LOGFILE=$INSTALL_DIR/install.log
DATE=$(date +"%d_%m_%Y")

if [ "$2" == "stable" ]
then
    BRANCH="master"
fi

echo -e "starting installation. Logging to ${LOGFILE}\n"

if [ ! -d "$INSTALL_DIR" ]; then
    mkdir $INSTALL_DIR
fi

for repo in framework easyconfigs easyblocks;
do
    REPOURL="http://github.com/hpcugent/easybuild-${repo}/archive/${BRANCH}.tar.gz"
    echo "downloading ${REPOURL}"
    wget ${REPOURL} -O /tmp/eb-${repo}-${BRANCH}_${DATE}.tar.gz >> $LOGFILE 2>&1
    
    echo -e "uncompressing ${repo}\n"
    tar xf /tmp/eb-${repo}-${BRANCH}_${DATE}.tar.gz -C $INSTALL_DIR --strip-components=1
done

rm -fr /tmp/eb-{framework,easyconfigs,easyblocks}-${BRANCH}_${DATE}.tar.gz

cat > $INSTALL_DIR/setup-env.sh << EOF
export PYTHONPATH=${INSTALL_DIR}:\$PYTHONPATH
export PATH=${INSTALL_DIR}:\$PATH
EOF

echo -e "Installation complete. To start using it do \"source $INSTALL_DIR/setup-env.sh\"\n"

touch $INSTALL_DIR/INSTALLED_${DATE}
