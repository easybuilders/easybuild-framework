# EasyBuild Singularity guide

To use easybuild with singularity see the following examples

.. code::

        #with centos 7.3
        eb Anaconda3-5.0.1.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611

.. code::

        # with centos 7.4
        eb Anaconda3-5.0.1.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.4.1708

Support for HierarchicalMNS

.. code::

        # Hierarchical MNS
        eb Anaconda3-5.0.1.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611 --module-naming-scheme=HierarchicalMNS


To use an alternative bootstrap such as localimage

.. code::

        # local bootstrap
        eb Anaconda3-5.0.1.eb --singularity --singularity-bootstrap localimage:/lustre/workspace/home/siddis14/eb_images/GCC-5.4.0-2.26.simg


To build singuality image use --buildimage

.. code::

        eb M4-1.4.18.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611 --buildimage

Example using ext3 image format

.. code::

        # ext3 image format
        eb M4-1.4.18.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611 --buildimage --imageformat=ext3

Example using sandbox image format

.. code::

        # ext3 image format
        eb M4-1.4.18.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611 --buildimage --imageformat=sandbox

use --singularitypath to alter where to write image. you can also set $EASYBUILD_SINGULARITYPATH to alter this path

.. code::

        eb Bison-3.0.4.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611 --buildimage --singularitypath=/lustre/workspace/home/siddis14/eb_images

Example using --imagename

.. code::

        # imagename
        eb Bison-3.0.4.eb --singularity --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611 --buildimage --imagename=Bison.img

custom easyconfig and easyblock inside singularity container

.. code::

   eb CUDA-9.0.176.eb --singularity --import-easyconfig-repo https://github.com/shahzebsiddiqui/easybuild-easyconfigs:master --import-easyblock-repo https://github.com/shahzebsiddiqui/easybuild-easyblocks:master:c/cuda.py --singularity-bootstrap shub:shahzebsiddiqui/eb-singularity:centos-7.3.1611
