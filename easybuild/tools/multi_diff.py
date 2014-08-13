import difflib
import os
import sys
from collections import defaultdict
from pprint import pprint
import collections

import easybuild.tools.terminal as terminal

class bcolors:
        GREEN = "\033[92m"
        PURPLE = "\033[0;35m"
        GRAY = "\033[1;37m"
        RED = "\033[91m"
        ENDC = "\033[0m"

class Diff:
    def __init__(self, base, files):
        self.base = base
        self.base_lines = open(base).readlines()
        self.diff_info = defaultdict(dict)
        self.files = files
        self.num_files = len(files)

    def add_line(self,line_no, diff_line, meta, squigly_line=None):
        if diff_line.startswith('+'):
            self._add_diff(line_no, diff_line.rstrip(), meta, squigly_line)
        elif diff_line.startswith('-'):
            self._remove_diff(line_no, diff_line.rstrip(), meta, squigly_line)

    def write_out(self):
        def limit(text, length):
            if len(text) > length:
                return text[0:length-3] + '...'
            else:
                return text

        w,h = terminal.get_terminal_size()
        print " ".join(["Comparing", bcolors.PURPLE, os.path.basename(self.base), bcolors.ENDC, "with", bcolors.GRAY, ", ".join(map(os.path.basename,self.files)), bcolors.ENDC])

        for i in range(len(self.base_lines)):
            lines = self.get_line(i)
            if filter(None,lines):
                print "\n".join(map(lambda line: limit(line,w),lines))

    def get_line(self, line_no):
        removal_dict = dict()
        addition_dict = dict()
        squigly_dict = dict()
        order = set()
        output = []
        if 'removal' in self.diff_info[line_no]:
            for (diff_line, meta, squigly_line) in self.diff_info[line_no]['removal']:
                if squigly_line:
                    squigly_dict[diff_line] = squigly_line
                order.add(diff_line)
                if diff_line not in removal_dict:
                    removal_dict[diff_line] = set([meta])
                else:
                    removal_dict[diff_line].add(meta)

        for diff_line in order:
            line = [str(line_no), self._colorize(diff_line, squigly_dict.get(diff_line))]
            files = removal_dict[diff_line]
            if len(files) != self.num_files:
                line.extend([bcolors.GRAY, "(%d/%d)" % (len(files), self.num_files), ', '.join(files), bcolors.ENDC])
            else:
                line.extend([bcolors.GRAY, "(%d/%d)" % (len(files), self.num_files), bcolors.ENDC])
            output.append(" ".join(line))

        squigly_dict = dict()
        order = set()

        if 'addition' in self.diff_info[line_no]:
            for (diff_line, meta, squigly_line) in self.diff_info[line_no]['addition']:
                if squigly_line:
                    squigly_dict[diff_line] = self._merge_squigly(squigly_dict.get(diff_line, squigly_line), squigly_line)
                order.add(diff_line)
                if diff_line not in addition_dict:
                    addition_dict[diff_line] = set([meta])
                else:
                    addition_dict[diff_line].add(meta)

        for diff_line in order:
            line = [str(line_no), self._colorize(diff_line, squigly_dict.get(diff_line))]
            files = addition_dict[diff_line]
            if len(files) != self.num_files:
                line.extend([bcolors.GRAY, "(%d/%d)" % (len(files), self.num_files), ', '.join(files), bcolors.ENDC])
            else:
                line.extend([bcolors.GRAY, "(%d/%d)" % (len(files), self.num_files), bcolors.ENDC])
            output.append(" ".join(line))

        # print seperator
        if self.diff_info[line_no] and 'addition' not in self.diff_info[line_no+1] and 'removal' not in self.diff_info[line_no + 1]:
            output.append('')
            output.append('-----')
            output.append('')

        return output


    def _remove_diff(self,line_no, diff_line, meta, squigly_line=None):
        if 'removal' not in self.diff_info[line_no]:
            self.diff_info[line_no]['removal'] = []

        self.diff_info[line_no]['removal'].append((diff_line, meta, squigly_line))

    def _add_diff(self,line_no, diff_line, meta, squigly_line=None):
        if 'addition' not in self.diff_info[line_no]:
            self.diff_info[line_no]['addition'] = []

        self.diff_info[line_no]['addition'].append((diff_line, meta, squigly_line))

    def _colorize(self, line, squigly):
        chars = list(line)
        flag = ' '
        compensator = 0
        if not squigly:
            if line.startswith('+'):
                chars.insert(0, bcolors.GREEN)
            elif line.startswith('-'):
                chars.insert(0, bcolors.RED)
        else:
            for i in range(len(squigly)):
                if squigly[i] == '+' and flag != '+':
                    chars.insert(i+compensator, bcolors.GREEN)
                    compensator += 1
                    flag = '+'
                if squigly[i] == '^' and flag != '^':
                    color = bcolors.GREEN if line.startswith('+') else bcolors.RED
                    chars.insert(i+compensator, color)
                    compensator += 1
                    flag = '^'
                if squigly[i] == '-' and flag != '-':
                    chars.insert(i+compensator, bcolors.RED)
                    compensator += 1
                    flag = '-'
                if squigly[i] != flag:
                    chars.insert(i+compensator, bcolors.ENDC)
                    compensator += 1
                    flag = squigly[i]

        chars.append(bcolors.ENDC)
        return ''.join(chars)

    def _merge_squigly(self, squigly1, squigly2):
        """Combine 2 diff lines into 1 """
        sq1 = list(squigly1)
        sq2 = list(squigly2)
        base,other = (sq1, sq2) if len(sq1) > len(sq2) else (sq2,sq1)

        for i in range(len(other)):
            if base[i] != other[i] and base[i] == ' ':
                base[i] = other[i]
            if base[i] != other[i] and base[i] == '^':
                base[i] = other[i]


        return ''.join(base)

def merge_diff_info(diffs):
    ### Combine multiple diff squigly lines into a single one.
    base = list(max(diffs,key=len))
    for line in diffs:
        for i in range(len(line)):
            if base[i] != line[i]:
                if base[i] == ' ' and line[i] != "\n":
                    base[i] = line[i]
    return ''.join(base).rstrip()

def multi_diff(base,files):
    d = difflib.Differ()
    base_lines = open(base).readlines()

    diff_information = dict()
    enters = []

    differ = Diff(base, files)

    # store diff information in dict
    for file_name in files:
        diff = list(d.compare(open(file_name).readlines(), base_lines))
        file_name = os.path.basename(file_name)

        local_diff = defaultdict(list)
        squigly_dict = dict()
        last_added = None
        compensator = 1
        for (i, line) in enumerate(diff):
            if line.startswith('?'):
                squigly_dict[last_added] = (line)
                compensator -= 1
            elif line.startswith('+'):
                local_diff[i+compensator].append((line, file_name))
                last_added = line
            elif line.startswith('-'):
                local_diff[i+compensator].append((line, file_name))
                last_added = line
                compensator -= 1


        for line_no in local_diff:
            for (line, file_name) in local_diff[line_no]:
                differ.add_line(line_no, line, file_name, squigly_dict.get(line, None))

    return differ
