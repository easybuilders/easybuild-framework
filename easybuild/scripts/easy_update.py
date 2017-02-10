#!/usr/bin/env python

import re
import os
import sys
import getopt
import imp
import json
import requests
import urllib2
import xmlrpclib


class ExtsList(object):
    """ Extension List Update is a utilty program for maintaining EasyBuild
    easyconfig files for R, Python and Bioconductor.  R, Python and
    Bioconductor langueges support package extensions.  Easyconfig supports
    the building of the language with a list of extions. This program automates
    the the updating of extension lists for R and Python by using API for
    resolving current version for each package.

    command line arguments -> arguments
    --add [file] ->add_packages. add_packages is a list of package names to
          be added to exts_list.
    --check [package name] -> package.  If package is not None just check
            this one package and exit.

    Issues
       There are many small inconsistancies with PyPI which make it difficult
       to fully automate building of easyconfig files.
       - dependancy checking - check for extras=='all'
       - Not all Python modules usr tar.gz so modules added can be incorrect.
       - pypi projects names do not always match module names and or file names
         project: liac-arff, module: arff,  file_name: liac_arff.zip
    """
    def __init__(self, file_name, add_packages, package, verbose):
        self.verbose = verbose
        self.debug = False
        self.checkpackage = False
        self.code = None
        self.ext_list_len = 0
        self.ext_counter = 0
        self.pkg_update = 0
        self.pkg_new = 0

        self.exts_processed = []  # single list of package names
        self.depend_exclude = []  # built in packages not be added to exts_list
        self.prolog = '## remove ##\n'
        self.ptr_head = 0
        self.indent_n = 4
        self.indent = ' ' * self.indent_n
        self.pkg_top = None

        eb = self.parse_eb(file_name, primary=True)
        self.exts_orig = eb.exts_list
        self.toolchain = eb.toolchain
        self.dependencies = eb.dependencies
        self.version = eb.version
        self.name = eb.name
        self.pkg_name = eb.name + '-' + eb.version
        self.pkg_name += '-' + eb.toolchain['name']
        self.pkg_name += '-' + eb.toolchain['version']
        self.bioconductor = False

        # compare easyconfig name with file name
        try:
            self.pkg_name += eb.versionsuffix
        except (AttributeError, NameError):
            pass
        f_name = os.path.basename(file_name)[:-3]
        if f_name != self.pkg_name:
            sys.stderr.write("Warning: file name does not match easybuild " +
                             "module name\n"),
            sys.stderr.write(" file name: %s, module name: %s\n" % (
                             f_name, self.pkg_name))
            sys.stderr.write('Writing output to: %s' % self.pkg_name +
                             '.update\n')

        # process command line arguments
        for pkg_name in add_packages:
            self.exts_orig.append((pkg_name, 'add'))
        if package:
            self.checkpackage = True
            self.verbose = True
            self.exts_orig = [(package, 'add')]
        else:
            self.out = open(self.pkg_name + ".update", 'w')

    def parse_eb(self, file_name, primary):
        """ interpret easyconfig file with 'exec'.  Interperting fails if
        constants that are not defined within the easyconfig file.  Add
        undefined constants to <header>.
        """
        header = 'SOURCE_TGZ  = "%(name)s-%(version)s.tgz"\n'
        header += 'SOURCE_TAR_GZ = "%(name)s-%(version)s.tar.gz"\n'
        header += self.prolog
        code = header

        eb = imp.new_module("easyconfig")
        with open(file_name, "r") as f:
            code += f.read()
        try:
            exec (code, eb.__dict__)
        except Exception as err:
            print("interperting easyconfig error: %s" % err)
        if primary:     # save original text of source code
            self.code = code
            self.ptr_head = len(header)
        return eb

    def get_package_info(self, pkg):
        pass

    def check_package(self, pkg):
        pkg_name = pkg[0]
        if pkg_name in [i[0] for i in self.exts_processed] or (
           pkg_name in self.depend_exclude):
            if pkg_name == self.pkg_top:
                pkg.append('duplicate')
                self.exts_processed.append(pkg)
            return
        pkg_ver, depends = self.get_package_info(pkg)
        if pkg_ver == "error" or pkg_ver == 'not found':
            if pkg_name == self.pkg_top and pkg[1] != 'add':
                pkg.append('keep')
            else:
                sys.stderr.write("Warning: %s Not in CRAN.\n" % pkg_name)
                return
        else:
            if self.pkg_top == pkg_name and pkg[1] != 'add':
                if pkg[1] == pkg_ver:
                    pkg.append('keep')
                else:
                    pkg[1] = pkg_ver
                    pkg.append('update')
                    self.pkg_update += 1
            else:
                pkg[1] = pkg_ver
                if self.name == "Python":
                    ext_url = "{\n%s'source_urls': " % (self.indent * 2)
                    ext_url += "['https://pypi.python.org/packages/source/"
                    ext_url += "%s/%s/'],\n%s}" % (pkg_name[0], pkg_name,
                                                   self.indent)
                    pkg.append(ext_url)
                pkg.append('new')
                self.pkg_new += 1

        for depend in depends:
            if depend not in self.depend_exclude:
                self.check_package([depend, 'x'])
        self.exts_processed.append(pkg)
        self.ext_counter += 1
        if self.verbose:
            if len(pkg) < 4:
                print("Error:"),
            print("%20s : %-8s (%s) [%2d, %d]" % (pkg[0], pkg[1], pkg[-1],
                  self.ext_list_len, self.ext_counter))

    def update_exts(self):
        """
        """
        self.ext_list_len = len(self.exts_orig)
        for pkg in self.exts_orig:
            if isinstance(pkg, tuple):
                if self.debug:
                    print("update_exts loop package: %s" % pkg[0])
                self.pkg_top = pkg[0]
                self.check_package(list(pkg))
            else:
                self.exts_processed.append(pkg)

    def write_chunk(self, indx):
        self.out.write(self.code[self.ptr_head:indx])
        self.ptr_head = indx

    def rewrite_extension(self, pkg):
        name_indx = self.code[self.ptr_head:].find(pkg[0])
        name_indx += self.ptr_head + len(pkg[0]) + 1
        indx = self.code[name_indx:].find("'") + name_indx + 1
        self.write_chunk(indx)
        self.out.write("%s'," % pkg[1])  # write version Number
        self.ptr_head = self.code[self.ptr_head:].find(',') + self.ptr_head + 1
        indx = self.code[self.ptr_head:].find('),') + self.ptr_head + 3
        self.write_chunk(indx)

    def print_update(self):
        """ this needs to be re-written in a Pythonesque manor

        if check package [self.checkpackage] is set nothing needs to be written
        """
        if self.checkpackage:
            return
        indx = self.code.find('exts_list')
        indx += self.code[indx:].find('[')
        indx += self.code[indx:].find('\n') + 1
        self.write_chunk(indx)

        for extension in self.exts_processed:
            if isinstance(extension, str):  # base library with no version
                indx = self.code[self.ptr_head:].find(extension)
                indx += self.ptr_head + len(extension) + 2
                self.write_chunk(indx)
                continue
            action = extension.pop()
            if action == 'keep' or action == 'update':
                self.rewrite_extension(extension)
                # sys.exit(0)
            elif action == 'duplicate':
                print("duplicate: %s" % extension[0])
                name_indx = self.code[self.ptr_head:].find(extension[0])
                name_indx += self.ptr_head + len(extension[0])
                indx = self.code[name_indx:].find('),') + name_indx + 3
                self.ptr_head = indx
                continue
            elif action == 'new':
                if self.bioconductor and extension[2] == 'ext_options':
                    print(" CRAN depencancy: %s" % extension[0])
                else:
                    self.out.write("%s('%s', '%s', %s),\n" % (self.indent,
                                                              extension[0],
                                                              extension[1],
                                                              extension[2]))
        self.out.write(self.code[self.ptr_head:])
        print("Updated Packages: %d" % self.pkg_update)
        print("New Packages: %d" % self.pkg_new)


class R(ExtsList):
    """extend ExtsList class to update package names from CRAN
    """
    def __init__(self, file_name, add_packages, package, verbose):
        ExtsList.__init__(self, file_name, add_packages, package, verbose)
        self.bioc_data = {}
        self.depend_exclude = ['R', 'parallel', 'methods', 'utils', 'stats',
                               'stats4', 'graphics', 'grDevices', 'tools',
                               'tcltk', 'grid', 'splines']

        if 'bioconductor' in self.pkg_name.lower():
            self.bioconductor = True
            self.R_modules = []

            #  Read the R package list from the dependent R package
            for dep in self.dependencies:
                if dep[0] == 'R':
                    R_name = dep[0] + '-' + dep[1] + '-'
                    R_name += (self.toolchain['name'] + '-' +
                               self.toolchain['version'])
                    if len(dep) > 2:
                        R_name += dep[2]
                    R_name += '.eb'
                    print('Required R module: %s' % R_name)
                    if os.path.dirname(file_name):
                        R_name = os.path.dirname(file_name) + '/' + R_name
                    eb = self.parse_eb(R_name, primary=False)
                    break
            for pkg in eb.exts_list:
                if isinstance(pkg, tuple):
                    self.R_modules.append(pkg[0])
                else:
                    self.R_modules.append(pkg)
            self.read_bioconductor_pacakges()
        else:
            self.bioconductor = False

    def read_bioconductor_pacakges(self):
            """ read the Bioconductor package list into bio_data dict
            """
            bioc_urls = {'https://bioconductor.org/packages/json/3.4/bioc/packages.json',
                         'https://bioconductor.org/packages/json/3.4/data/annotation/packages.json',
                         'https://bioconductor.org/packages/json/3.4/data/experiment/packages.json'}
            self.bioc_data = {}
            for url in bioc_urls:
                try:
                    response = urllib2.urlopen(url)
                except IOError as e:
                    print('URL request: %s' % url)
                    sys.exit(e)
                self.bioc_data.update(json.loads(response.read()))

    def check_CRAN(self, pkg):
        cran_list = "http://crandb.r-pkg.org/"
        resp = requests.get(url=cran_list + pkg[0])

        cran_info = json.loads(resp.text)
        if 'error' in cran_info and cran_info['error'] == 'not_found':
            return "not found", []
        try:
            pkg_ver = cran_info[u'Version']
        except KeyError:
            return "error", []
        depends = []
        if u'License' in cran_info and u'Part of R' in cran_info[u'License']:
            return 'base package', []
        if u"Depends" in cran_info:
            depends = cran_info[u"Depends"].keys()
        if u"Imports" in cran_info:
            depends += cran_info[u"Imports"].keys()
        if u"LinkingTo" in cran_info:
            depends += cran_info[u"LinkingTo"].keys()
        return pkg_ver, depends

    def check_BioC(self, pkg):
        """Extract <Depends> and <Imports> from BioCondutor json metadata
        Example:
        bioc_data['pkg']['Depends']
                 [u'R (>= 2.10)', u'BiocGenerics (>= 0.3.2)', u'utils']
        bioc_data['pkg']['Depends']['Imports'] [ 'Biobase', 'graphics']
        """
        depends = []
        if pkg[0] in self.bioc_data:
            pkg_ver = self.bioc_data[pkg[0]]['Version']
            if 'Depends' in self.bioc_data[pkg[0]]:
                depends = [re.split('[ (><=,]', s)[0]
                           for s in self.bioc_data[pkg[0]]['Depends']]
            if 'Imports' in self.bioc_data[pkg[0]]:
                depends = [re.split('[ (><=,]', s)[0]
                           for s in self.bioc_data[pkg[0]]['Imports']]
        else:
            pkg_ver = "not found"
        return pkg_ver, depends

    def print_depends(self, pkg, depends):
        for p in depends:
            if p not in self.depend_exclude:
                print("%20s : requires %s" % (pkg, p))

    def get_package_info(self, pkg):
        if self.bioconductor:
            pkg_ver, depends = self.check_BioC(pkg)
            pkg[2] = 'bioconductor_options'
            if pkg_ver == 'not found':
                if pkg[0] in self.R_modules:
                    return pkg_ver, []
                pkg_ver, depends = self.check_CRAN(pkg)
                pkg[2] = 'ext_options'
        else:
            if self.debug:
                print("get_package_info: %s" % pkg)
            pkg_ver, depends = self.check_CRAN(pkg)
            if len(pkg) < 3:
                pkg.append('ext_options')
            else:
                pkg[2] = 'ext_options'
        if self.verbose:
            self.print_depends(pkg[0], depends)
        return pkg_ver, depends


class PythonExts(ExtsList):
    """extend ExtsList class to update package names from PyPI
    """
    def __init__(self, file_name, add_package, package, verbose):
        ExtsList.__init__(self, file_name, add_packages, package, verbose)
        self.verbose = verbose
        self.pkg_dict = None
        self.client = xmlrpclib.ServerProxy('https://pypi.python.org/pypi')
        (nums) = self.version.split('.')
        self.python_version = "%s.%s" % (nums[0], nums[1])

    def parse_pypi_requires(self, pkg_name, requires):
        """pip requirement specifier is defined in full in PEP 508
        The project name is the only required portion of a requirement string.

        Only install the latest version so ignore all version information
        input: 'numpy (>=1.7.1)'  output: 'numpy'

        Test that <python_version> and <sys_platform> conform.
        If <extra> is present and required check that extra is contained
        in "exts_list".
        wincertstore (==0.2); sys_platform=='win32' and extra == 'ssl'
        futures (>=3.0); (python_version=='2.7' or python_version=='2.6')
        requests-kerberos (>=0.6); extra == 'kerberos'
        trollius; python_version == "2.7" and extra == 'asyncio'
        asyncio; python_version == "3.3" and extra == 'asyncio'
        """
        sys_platform = 'Linux'
        python_version = self.python_version
        extra = ''
        require_re = '^([A-Za-z0-9_\-\.]+)(?:.*)$'
        extra_re = "and\sextra\s==\s'([A-Za-z0-9_\-\.]+)'"  # only if the
        targets = ['python_version', 'sys_platform', 'extra']
        ans = re.search(require_re, requires)
        name = ans.group(1)
        test = False    # do we need to test extra requires field?
        state = True    # result of eval(requires)

        version = requires.split(';')
        if len(version) > 1:
            for target in targets:
                if target in version[1]:
                    test = True
                    if target == 'extra':
                        extra = re.search(extra_re, version[1])
                        extra = extra.group(1) if extra else None
                        if extra not in [i[0] for i in self.exts_processed]:
                            extra = None
            if test:
                state = eval(version[1])
        if state:
            if self.debug:
                if name not in [i[0] for i in self.exts_processed] and (
                   name not in self.depend_exclude):
                    print('Add dependent package: %s ' % name +
                          'for: %s, Expression: %s' % (pkg_name, requires))
            return name
        else:
            if self.debug:
                print('Do not install: %s, ' % name +
                      'for package: %s, Expression: %s' % (pkg_name, requires))
            return None

    def get_package_info(self, pkg):
        """Python pypi API for package version and dependancy list
           pkg is a list; ['package name', 'version', 'other stuff']
           return the version number for the package and a list of dependancie
        """
        pkg_name = pkg[0]
        pkg_version = pkg[1]
        depends = []
        xml_vers = self.client.package_releases(pkg_name)
        if xml_vers:
            pkg_ver = xml_vers[0]
            xml_info = self.client.release_data(pkg_name, pkg_ver)
            if 'requires_dist' in xml_info.keys():
                for requires in xml_info['requires_dist']:
                    pkg_requires = self.parse_pypi_requires(pkg_name, requires)
                    if pkg_requires:
                        depends.append(pkg_requires)
        else:
            self.depend_exclude.append(pkg[0])
            sys.stderr.write("Warning: %s Not in PyPi. " % pkg[0])
            sys.stderr.write("No depdancy checking performed\n")
            pkg_ver = 'not found'
        return pkg_ver, depends


def help():
    print("usage: easy_update  easyconfig.eb [flags]")
    print("easy_update Updates ext_list information of EasyBuild " +
          "easyconfig  files")
    print("easy_update works with R, Python and R-bioconductor " +
          "easyconfig files")
    print("  --verbose  diplay status for each package")
    print("  --add [filename]  filename contains list of package names to add")
    print("  --check [package name] print update actions for a single package")
    print("          option is used for debugging single packages")


def get_package_list(fname, add_packages):
    """read package names from <fname>
    return list
    """
    with open(fname, "r") as pkg_file:
        for pkg in pkg_file:
            add_packages.append(pkg[:-1])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        help()
        sys.exit(0)

    vflag = False
    add_packages = []
    package = None
    file_name = os.path.basename(sys.argv[1])
    myopts, args = getopt.getopt(sys.argv[2:], "",
                                 ['verbose',
                                  'add=',
                                  'check='])
    for opt, arg in myopts:
        if opt == "--add":
            get_package_list(arg, add_packages)
        elif opt == "--verbose":
            vflag = True
        elif opt == "--check":
            package = arg
    if file_name[:2] == 'R-':
        module = R(sys.argv[1], add_packages, package, verbose=vflag)
    elif file_name[:7] == 'Python-':
        module = PythonExts(sys.argv[1], add_packages, package, verbose=vflag)
    else:
        print("Module name must begin with R- or Python-")
        sys.exit(1)
    module.update_exts()
    module.print_update()
