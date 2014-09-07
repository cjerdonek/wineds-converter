#!/usr/bin/env python

"""
Usage: python parse.py PATH

PATH is a path to a WinEDS Reporting Tool output file.

"""

import re
import sys
import timeit

splitter = re.compile(r'\s{2,}')

def parse_line(line):
    # Split on strings of whitespace with 2 or more characters.
    # This is necessary since field values can contain spaces.
    return splitter.split(line.strip())

def main(argv):
    try:
        input_path = argv[1]
    except IndexError:
        raise Exception("PATH not provided on command-line")

    with open(input_path, 'rb') as f:
        start_time = timeit.default_timer()
        for i, line in enumerate(iter(f), start=1):
            data = parse_line(line)
        elapsed = timeit.default_timer() - start_time

    print "parsed: %d lines" % i
    print "elapsed: %.4f seconds" % elapsed

if __name__ == "__main__":
    main(sys.argv)
