#!/usr/bin/env python

# python3 declarations for python2
from __future__ import absolute_import,division,print_function,unicode_literals

import sys,os,re,time
import json,requests
import shutil

import xmlrpclib

# global dictionary of R packages and their respective dependencies
r_dict={}

# Find package in CRAN
# return empty list if no package match
def cran_version(package):
   global r_dict

   if package not in r_dict:
      cran_url="http://crandb.r-pkg.org/"

      #print("cran url",cran_url+package)
      resp=requests.get(url=cran_url+package)
      data=json.loads(resp.text)
      try:
         r_dict[package]=[data[u'Version']]
         dependency_list = []
         if u'Depends' in data:
            # many things (but not all!??!) depend "R", which must be removed
            depends = data[u'Depends'].keys()
            if 'R' in depends:
               depends.remove('R')
            if len(depends) > 0:
               dependency_list = dependency_list + depends
               #print("Depends:",depends)
         if u'Imports' in data:
            imports = data[u'Imports'].keys()
            if len(imports) > 0:
               dependency_list = dependency_list + imports
               #print("Imports:",imports)
         if len(dependency_list) > 0:
            r_dict[package].append(list(set(dependency_list)))
      except KeyError:
         print("Warning: could not find R package:",package)
         #print("CRAN response:",data)
         r_dict[package]=[]
 
   return r_dict[package]

# global dictionary of Python packages - no dependencies yet
py_dict={}

# parse format required in "requires" field by pypi
# return simple list of unencumbered packages or empty list if none
def parse_pypi_requires(requires_list):
   result=[]

   for r in requires_list:
      if ';' not in r:
         result.append(r.split(' ',1)[0])
     
   return result 

# Find package on PyPi
# return empty list if no package match
def pypi_version(package):
   global py_dict

   if package not in py_dict:
      client=xmlrpclib.ServerProxy('https://pypi.python.org/pypi')
      xml_vers=client.package_releases(package)
      if xml_vers:
         py_dict[package]=[xml_vers[0]]
         xml_info=client.release_data(package,xml_vers[0])
         if 'requires_dist' in xml_info:
            req=parse_pypi_requires(xml_info['requires_dist'])
            if req:
               py_dict[package].append(req)
               #print("requires_dist:",req)
      else:
         print("Warning: could not find Python package:",package)
         py_dict[package]=[]

   return py_dict[package]
  
def q(s):
   return("'"+s+"'")

def s(s):
   return("/"+s+"/")

# write simplest R exts_list record
# fp, 3 params from original, new version
def write3(f,indent,params,current):
   f.write(' '*indent)
   f.write("("+q(params[0])+", "+q(current)+", "+params[2]+"),\n")

def get_temp():
   return "/tmp/temp."+str(os.getpid())

def update_updated():
   return('# package versions updated '+time.strftime("%b %d %Y")+'\n')

def parse_ez(ez_file,parse_func,suffix=".updated"):
   not_exts_list=True
   changes=0
   pkgs=[]

   temp=get_temp()
   with open(temp,"w") as f_out:
      with open(ez_file,"r") as f_in:
         for line in f_in:
            if not_exts_list:
               if line.startswith("# package versions updated") or\
                  line.startswith("# packages updated on"):
                  line=update_updated()
               elif line.startswith("exts_list"):
                  not_exts_list=False
            else:
               if not line.startswith("]"):
                  cleaned=line.lstrip()
                  if not cleaned.startswith("#"):
                     indent=len(line)-len(cleaned)
                     cleaned=cleaned.rstrip()

                     changes,ret=parse_func(cleaned,indent,changes,f_out,pkgs)
                     if ret:
                        continue
               else:
                  not_exts_list=True

            f_out.write(line)

   if changes>0:
      shutil.move(temp,ez_file+suffix)
   else:
      os.remove(temp)

   print("%s: updated %d package%s" % (ez_file,changes,"" if changes==1 else "s"))

def parse_r_params(params,indent,f_out,pkgs):
   changes=0

   current=cran_version(params[0])
     
   # 2 items means dependency list 
   #print(params[0],"cran_version returned",len(current))
   if len(current)==2:
      #print(params[0],"needs",current[1])
      missing=list(set(current[1])-set(pkgs))
      for m in missing:
         #print("missing",m)
         changed=parse_r_params([m,"0","ext_options"],indent,f_out,pkgs)
         if changed>0:
            pkgs.append(m)
            changes=changes+changed

   if current!=[] and params[1]!=current[0]:
      #print("wrote",params[0],"to file! version",params[1],"to",current[0])
      write3(f_out,indent,params,current[0])
      changes=changes+1

   return changes

# R-specific exts_list item parser 
# pkgs is list of packages already loaded
# returns number of changes and echo line if 0
def parse_r(cleaned,indent,changes,f_out,pkgs):
   params_re="([^', \(\)]+)"

   params=re.findall(params_re,cleaned)

   # if package already seen, then skip it
   # deletion is considered a change
   if params[0] in pkgs:
      return changes+1,1

   pkgs.append(params[0])

   # only update simplest case with 3 parameters
   if len(params)==3:
      changed=parse_r_params(params,indent,f_out,pkgs)
      if changed>0:
         return changes+changed,1

   return changes,0

# doesn't have to be global but don't like idea of instantiating every call
py_template=[
   [4, "('name', '0', {"], 
   [8, "'source_urls': ['https://pypi.python.org/packages/source/'],"]
]

# create new Python entry using py_template
def create_py_group(package):
   global py_template
   pypi_url='https://pypi.python.org/packages/source/'

   new_entry=py_template
   new_entry[0][1]="("+q(package)+", '0', {"
   new_entry[1][1]="'source_urls': ["+q(pypi_url+package[0]+s(package))+'],'

   return new_entry

# stupidly write group to temp file
# if finalize, then close brackets indented to same as 1st group item
def dump_py_group(f,group,finalize=False):
   for item in group:
      f.write(' '*item[0]+item[1]+'\n')

   if finalize:
      f.write(' '*group[0][0]+'}),\n')

# determine if package from pypi
# if not dump to file else
# get package version, etc
def parse_py_group(f,group,pkgs):
   #print("DEBUG: parse_py_group: ",repr(group))
   params_re="([^', \(\)]+)"

   params=re.findall(params_re,group[0][1])

   # if package already seen, then skip it
   # deletion is considered a change
   if params[0] in pkgs:
      return 1

   pkgs.append(params[0])

   if len(group)!=2 or "pypi.python.org" not in group[1][1]:
      dump_py_group(f,group)
   else:
      current=pypi_version(params[0])

      # if package has associated dependencies
      if len(current)==2:
         missing=list(set(current[1])-set(pkgs))
         #print("parent",group)
         for m in missing:
            #print("missing",m)
            m_group=create_py_group(m)
            #print("m_group",m_group)
            dump_py_group(f,m_group,True)

      if current==[] or current[0]==params[1]:
         dump_py_group(f,group)
      else:
         f.write(' '*group[0][0]+'('+q(params[0])+", "+q(current[0])+", {\n")
         dump_py_group(f,group[1:])
         return 1

   return 0

# defined as global to conserve state between generic parser steps
py_group=[]

# Python-specific exts_list item parser 
# pkgs is list of packages already loaded
# returns number of changes and echo line if 0
def parse_py(cleaned,indent,changes,f_out,pkgs):
   global py_group
   cont=0

   # append to group until end, then parse and reset
   if cleaned=="}),":
      changes=changes+parse_py_group(f_out,py_group,pkgs)
      py_group=[]
   else:
      py_group.append([indent,cleaned])
      cont=1

   return changes,cont

def main(args):
   if len(args)==0:
      print("Usage: update_exts <R- or Python- .eb file(s)>")
   else:
      for arg in args:
         base=os.path.basename(arg)
         if base.startswith("R-"):
            parse_ez(arg,parse_r)
         elif base.startswith("Python-"):
            parse_ez(arg,parse_py)
         else:
            print("Error: only R & Python files supported, skipping",arg)

if __name__ == '__main__':
    main(sys.argv[1:])
