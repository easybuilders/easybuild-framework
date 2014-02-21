##
# Copyright 2009-2014 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
"""
This module provides the extract_archive command
and it's helper functions.

This will help you to extract archives in pure python, but

@author: Jens Timmerman (Ghent University)
"""
import bz2
import os
import copy
import gzip
import operator
import tarfile
import zipfile

from easybuild.tools import run

from vsc.utils.missing import get_subclasses
from vsc.utils import fancylogger

_log = fancylogger.getLogger('filetools', fname=False)

BUFFERSIZE = 10240


def get_extractor(filename):
    """Returns the extractor if the file is an archive, or None otherwise
    """
    if not filename:
        return None
    for cls in get_subclasses(Extractor):
        if cls.can_handle(filename):
            return cls
    return None


def extract_archive(filename, destination_dir):
    """Extracts a given archive to the destination directory"""
    if not os.path.isfile(filename):
        _log.debug("Can't extract file %s: no such file" % filename)
        return None

    if not os.path.isdir(destination_dir):
        try:
            os.makedirs(destination_dir)
        except OSError, err:
            _log.exception("Can't extract file %s: directory %s can't be created: %err ", filename, destination_dir, err)

    destination_dir = os.path.abspath(destination_dir)

    # recursive extracting please
    # if we get a .tar.gz we should return the output dir
    cls = get_extractor(filename)
    if cls:
        out = cls.extract(filename, destination_dir)
        out2 = extract_archive(out, destination_dir)
        return out2 or out
    # not an archive
    return None


class Extractor(object):
    """"This is an abstract implementation for an extractor class
    it's purpose is to extract compressed archives
    """
    # magic number identifying files this class can handle
    # you can find magic numbers in from http://www.garykessler.net/library/file_sigs.html
    # e.g.,
    # LZW: "\x1F\x9D",
    # LZH: "\x1F\xA0",
    MAGIC = "This is not a magic numbers string"
    # MAGIC starts at offset
    OFFSET = 0

    @classmethod
    def can_handle(cls, filename):
        """Returns True if this class can handle the given file
        This uses magic numbers"""
        f = open(filename)
        f.seek(cls.OFFSET)
        can_handle = f.read(len(cls.MAGIC)) == cls.MAGIC
        f.close()
        return can_handle

    @classmethod
    def extract(cls, filename, destination):
        """
        Do the actual extraction
        This is an abstract method, it will return the result of _extract
        which has to be implemented in a class extending Extractor
        """
        outfile = os.path.join(destination, filename)
        if filename.endswith(cls.EXTENTION):
            outfile = outfile[:len(outfile)-len(cls.EXTENTION)]
        return cls._extract(filename, outfile)


class UnZIP(Extractor):
    """
    Implementation of the Extractor class for unzipping files
    uses zipfile
    """
    MAGIC = "\x50\x4B\x03\x04"

    @classmethod
    def extract(cls, filename, destination):
        """Do the actual extraction uzing zipfile"""
        zfile = zipfile.ZipFile(filename)
        for name in zfile.namelist():
            dirname, filename = os.path.split(name)
            dirname = os.path.join(destination, dirname)
            dest_name = os.path.join(dirname, filename)
            _log.debug("Decompressing %s on %s", filename, dest_name)
            if not os.path.exists(dirname):
                os.mkdir(dirname)
            fd = open(dest_name, "w")
            fd.write(zfile.read(name))
            fd.close()
        return destination


class UnTAR(Extractor):
    """Implementation of the Extractor class for extracting (possibly compressed) tarballs"""
    MAGIC = None
    EXTENTION = ".tar"

    @classmethod
    def can_handle(cls, filename):
        """Returns True if this class can handle the given file
        This uses the built in tarfile.is_tarfile method"""
        return tarfile.is_tarfile(filename)

    @classmethod
    def extract(cls, filename, destination):
        """Do the actual extraction using TarFile.extractAll
        (copied from the python 2.5 implementation, since this is not available in python 2.4"""
        tar_file = tarfile.open(filename, mode='r:*')
        directories = []
        for tarinfo in tar_file:
            if tarinfo.isdir():
                directories.append(tarinfo)
                tarinfo = copy.copy(tarinfo)
                tarinfo.mode = 0700  # 0o700 is invalid in python 2.4
            tar_file.extract(tarinfo, destination)
        directories.sort(key=operator.attrgetter('name'))
        directories.reverse()

        for tarinfo in directories:
            dirpath = os.path.join(destination, tarinfo.name)
            tar_file.chown(tarinfo, dirpath)
            tar_file.utime(tarinfo, dirpath)
            tar_file.chmod(tarinfo, dirpath)
        return destination


class UnBZIP2(Extractor):
    """
    Implementation of the Extractor class for extracting BZIP2 compressed files
    bzip2 unpacking always returns a single file
    """
    MAGIC = "\x42\x5A\x68"
    EXTENTION = ".bz2"

    @classmethod
    def _extract(cls, filename, destination):
        """Do the actuall extracting using bzip2 library"""
        infile = bz2.BZ2File(filename)
        block = infile.read(BUFFERSIZE)
        outfile = open(destination, 'w')
        while block:
            outfile.write(block)
            block = infile.read(BUFFERSIZE)
        outfile.close()
        return destination


class UnGZIP(Extractor):
    """
    Implementation of the Extractor class for extracting GZIP compressed files

    UnGZIP always returns a single file
    """
    MAGIC = "\x1f\x8b\x08"
    EXTENTION = ".gz"

    @classmethod
    def _extract(cls, filename, destination):
        """
        Do the actuall extracting using gzip library
        """
        infile = gzip.open(filename)
        block = infile.read(BUFFERSIZE)
        outfile = open(destination, 'w')
        while block:
            outfile.write(block)
            block = infile.read(BUFFERSIZE)
        outfile.close()
        return destination


class SystemExtractor(Extractor):
    """
    Abstract Extractor implementation,
    this uses a subprocess to run the extraction command,
    this is usefull for extracting files that have no simple python extraction libraries yet
    """
    EXTRACT_COMMAND = None

    @classmethod
    def _extract(cls, filename, destination):
        """Extract the given file to destination using a shell command"""
        #TODO: error checking
        run.run_cmd(cls.EXTRACT_COMMAND % {'filename': filename, 'destination': destination})[0]
        return destination


class UnXZ(SystemExtractor):
    """Use system tools to extract XZ files, since this is not easily done in python yet"""
    MAGIC = "\xFD7zXZ"
    EXTRACT_COMMAND = "unxz --to-stdout %(filename)s > %(destination)s"
    EXTENTION = ".xz"

#TODO: extract .iso, .deb and .rpm
