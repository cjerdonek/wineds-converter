"""
Usage: wineds-convert ELECTION_NAME PRECINCTS.csv WINEDS.txt OUTPUT_BASE

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

  OUTPUT_BASE: desired output path base.  The file extension will be
    appended to the argument provided, so the output paths will have the
    form "OUTPUT_BASE.tsv" and "OUTPUT_BASE.xlsx".

In the above, relative paths will be interpreted as relative to the
current working directory.
"""

import sys

import pywineds.main


def main():
    """
    The main console_script setup.py entry point.
    """
    pywineds.main.main(__doc__, sys.argv)
