#!/usr/bin/env python
#
# **THIS SCRIPT IS WRITTEN FOR PYTHON 3.**
#

"""
Usage: python3 parse.py ELECTION_NAME PRECINCTS.csv WINEDS.txt OUTPUT.tsv

Parses the given files and writes a new output file to stdout.

The new output file is tab-delimited (.tsv).  Tabs are used since some
fields contain commas (e.g. "US Representative, District 12").

Arguments:

  ELECTION_NAME: the name of the election for display purposes.
    This appears in the first line of the output file.
    An example value is "San Francisco June 3, 2014 Election".

  PRECINCTS.csv: path to a CSV file mapping precincts to their
    different districts and neighborhoods.

  WINEDS.txt: path to a TXT export file from the WinEDS Reporting Tool.
    The report contains vote totals for each precinct in each contest,
    along with "registered voters" and "ballots cast" totals.

  OUTPUT.tsv: desired output path.

In the above, relative paths will be interpreted as relative to the
current working directory.
"""

import sys

from pywineds.parser import main

if __name__ == "__main__":
    main(__doc__, sys.argv)
