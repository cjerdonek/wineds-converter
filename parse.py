#!/usr/bin/env python
#
# **THIS SCRIPT IS WRITTEN FOR PYTHON 3.**
#

"""
Usage: python3 parse.py ELECTION_NAME PCT_INDEX_PATH RESULTS_PATH > out.tsv

Parses the given files and writes a new output file to stdout.

The new output file is tab-delimited (.tsv).  Tabs are used since some
fields contain commas (e.g. "US Representative, District 12").

Arguments:

  ELECTION_NAME: the name of the election for display purposes.
    This appears in the first line of the output file.
    An example value is "San Francisco June 3, 2014 Election".

  PCT_INDEX_PATH: path to a CSV file mapping precincts to their
    different districts and neighborhoods.

  RESULTS_PATH: path to a WinEDS Reporting Tool output file that contains
    vote totals for each precinct in each contest.

In the above, relative paths will be interpreted as relative to the
current working directory.
"""

import sys

from pywineds.parser import main

if __name__ == "__main__":
    main(sys.argv)
