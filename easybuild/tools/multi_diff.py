import difflib
import os
import sys
from collections import defaultdict
from pprint import pprint

import collections

class bcolors:
        HEADER = '\033[95m'
        OKBLUE = '\033[94m'
        OKGREEN = '\033[92m'
        WARNING = '\033[93m'
        FAIL = '\033[91m'
        ENDC = '\033[0m'

class OrderedSet(collections.MutableSet):
    '''Set that remembers original insertion order.'''

    KEY, PREV, NEXT = range(3)

    def __init__(self, iterable=None):
        self.end = end = []
        end += [None, end, end]         # sentinel node for doubly linked list
        self.map = {}                   # key --> [key, prev, next]
        if iterable is not None:
            self |= iterable

    ### Collection Methods
    def __contains__(self, key):
        return key in self.map

    def __eq__(self, other):
        if isinstance(other, OrderedSet):
            return len(self) == len(other) and list(self) == list(other)
        return set(self) == set(other)

    def __iter__(self):
        end = self.end
        curr = end[self.NEXT]
        while curr is not end:
            yield curr[self.KEY]
            curr = curr[self.NEXT]

    def __len__(self):
        return len(self.map)

    def __reversed__(self):
        end = self.end
        curr = end[self.PREV]
        while curr is not end:
            yield curr[self.KEY]
            curr = curr[self.PREV]

    def add(self, key):
        if key not in self.map:
            end = self.end
            curr = end[self.PREV]
            curr[self.NEXT] = end[self.PREV] = self.map[key] = [key, curr, end]

    def discard(self, key):
        if key in self.map:
            key, prev, next = self.map.pop(key)
            prev[self.NEXT] = next
            next[self.PREV] = prev

    def pop(self, last=True):
        if not self:
            raise KeyError('set is empty')
        key = next(reversed(self)) if last else next(iter(self))
        self.discard(key)
        return key

    ### General Methods
    def __del__(self):
        self.clear()                    # remove circular references

    def __repr__(self):
        class_name = self.__class__.__name__
        if not self:
            return '{0!s}()'.format(class_name)
        return '{0!s}({1!r})'.format(class_name, list(self))

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
        print "Comparing %s with %s" % (os.path.basename(self.base), ", ".join(map(os.path.basename,self.files)))
        for i in range(len(self.base_lines)):
            self.get_line(i)

    def get_line(self, line_no):
        removal_dict = dict()
        addition_dict = dict()
        squigly_dict = dict()
        order = OrderedSet([])
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
            print line_no, self._colorize(diff_line, squigly_dict.get(diff_line)),
            if len(removal_dict[diff_line]) != self.num_files:
                print bcolors.OKBLUE, ', '.join(removal_dict[diff_line]), bcolors.ENDC
            else:
                print

        squigly_dict = dict()
        order = OrderedSet([])

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
            print line_no, self._colorize(diff_line, squigly_dict.get(diff_line)),
            if len(addition_dict[diff_line]) != self.num_files:
                print bcolors.OKBLUE, ', '.join(addition_dict[diff_line]), bcolors.ENDC
            else:
                print

        # print seperator
        if self.diff_info[line_no] and 'addition' not in self.diff_info[line_no+1] and 'removal' not in self.diff_info[line_no + 1]:
            print '-----'


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
                chars.insert(0, bcolors.OKGREEN)
            elif line.startswith('-'):
                chars.insert(0, bcolors.FAIL)
        else:
            for i in range(len(squigly)):
                if squigly[i] == '+' and flag != '+':
                    chars.insert(i+compensator, bcolors.OKGREEN)
                    compensator += 1
                    flag = '+'
                if squigly[i] == '^' and flag != '^':
                    chars.insert(i+compensator, bcolors.WARNING)
                    compensator += 1
                    flag = '^'
                if squigly[i] == '-' and flag != '-':
                    chars.insert(i+compensator, bcolors.FAIL)
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
