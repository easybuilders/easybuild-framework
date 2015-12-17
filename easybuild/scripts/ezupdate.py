#!/usr/bin/env python3

import sys,os,re,time
import json,requests
import shutil

r_dict={}

# return empty string if no package match
def cran_version(package):
   global r_dict
   cran_url="http://crandb.r-pkg.org/"

   if package in r_dict:
      return r_dict[package]

   resp=requests.get(url=cran_url+package)
   data=json.loads(resp.text)
   try:
      r_dict[package]=data['Version']
   except KeyError:
      print("Warning: could not find R package:",package)
      r_dict[package]=""
 
   return r_dict[package]

py_dict={}

def pypi_version(package):
   global py_dict
   pypi_url="http://pypi.python.org/pypi/"

   if package in py_dict:
      return py_dict[package]

   resp=requests.get(url=pypi_url+package+"/json")
   try:
      data=json.loads(resp.text)
      py_dict[package]=data['info']['version']
   except:
      print("Warning: could not find Python package:",package)
      py_dict[package]=""

   return py_dict[package]
  
def q(s):
   return("'"+s+"'")

# fp, 3 params from original, new version
def write3(f,indent,params,current):
   f.write(' '*indent)
   f.write("("+q(params[0])+", "+q(current)+", "+params[2]+"),\n")

def get_temp():
   return "/tmp/temp."+str(os.getpid())

def update_updated(f):
   f.write('# package versions updated '+time.strftime("%b %d %Y")+'\n')

def parse_ez(ez_file,parse_func):
   not_exts_list=True
   changes=0

   temp=get_temp()
   with open(temp,"w") as f_out:
      with open(ez_file,"r") as f_in:
         for line in f_in:
            if not_exts_list:
               if line.startswith("# package versions updated"):
                  update_updated(f_out)
                  continue
               elif line.startswith("exts_list"):
                  not_exts_list=False
            else:
               if not line.startswith("]"):
                  cleaned=line.lstrip()
                  if not cleaned.startswith("#"):
                     indent=len(line)-len(cleaned)
                     cleaned=cleaned.rstrip()

                     changes,ret=parse_func(cleaned,indent,changes,f_out)
                     if ret:
                        continue
               else:
                  not_exts_list=True

            f_out.write(line)

   if changes>0:
      shutil.move(temp,ez_file)
   else:
      os.remove(temp)

   print("%s: updated %d package%s" % (ez_file,changes,"" if changes==1 else "s"))

def parse_r(cleaned,indent,changes,f_out):
   params_re="([^', \(\)]+)"
   cont=0

   params=re.findall(params_re,cleaned)
   if len(params)==3:
      current=cran_version(params[0])
      if current!="" and params[1]!=current:
         write3(f_out,indent,params,current)
         changes=changes+1
         cont=1

   return changes,cont

# stupidly write group to temp file
def dump_py_group(f,group):
   for item in group:
      f.write(' '*item[0]+item[1]+'\n')

# determine if package from pypi
# if not dump to file else
# get package version, etc
def parse_py_group(f,group):
   params_re="([^', \(\)]+)"

   if len(group)!=2 or "pypi.python.org" not in group[1][1]:
      dump_py_group(f,group)
   else:
      params=re.findall(params_re,group[0][1])
      current=pypi_version(params[0])
      if current=="" or current==params[1]:
         dump_py_group(f,group)
      else:
         f.write(' '*group[0][0]+'('+q(params[0])+", "+q(current)+", {\n")
         dump_py_group(f,group[1:])
         return 1

   return 0

py_group=[]

def parse_py(cleaned,indent,changes,f_out):
   global py_group
   cont=0

   if cleaned=="}),":
      changes=changes+parse_py_group(f_out,py_group)
      py_group=[]
   else:
      py_group.append([indent,cleaned])
      cont=1

   return changes,cont

def main(args):
   if len(args)==0:
      print("Usage: ezupdate <R- or Python- .eb file(s)>")
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
