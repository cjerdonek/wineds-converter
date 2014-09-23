WinEDS Converter
================

This repository contains an open-source Python 3 script to convert
WinEDS 4.0 output into a simpler format.  WinEDS is an election
management system owned by [Dominion Voting Systems][dominion].

The script is tailored for use in elections held in San Francisco by the
[San Francisco Department of Elections][sf-elections].  However,
it wouldn't be too hard to modify the code for other jurisdictions.

The new (target) output format is a single tab-delimited file that
resembles the format of the PDF Statements of Vote released by the
SF Department of Elections.  In particular, it includes a
"District Grand Totals" section for each contest, which reports totals
broken down by various districts and neighborhoods.

The new file format is also smaller in size.  For example, for the
June 3, 2014 election, an 8.5 MB WinEDS file converted to a file with
size 487 KB.


Setting up
----------

The script is written for Python 3 and was developed using Python 3.4.

You can download Python [from here][python-download].

Then just clone this repo or download the individual file `parse.py`.


Usage
-----

For usage notes, see the docstring of the main [`parse.py`](parse.py#L6)
file.


Testing
-------

To test the script--

    $ python3 pywineds/test_parser.py


New Format
----------

This section documents the new format (i.e. the destination or target
format of the conversion).

Here is a snippet of what a file in the new format looks like.  The
data rows in the file are tab-delimited.  The string `***` can be used
to detect the first line of the section starting a new contest.

    San Francisco Election - June 3, 2014

    Report generated on: Tuesday, June 17, 2014 at 04:30:15 PM


    *** Governor - CALIFORNIA
    VotingPrecinctName  VotingPrecinctID  Precincts  Registration  Ballots Cast  Turnout (%)  [...CANDIDATE NAMES...]
    Pct 1101      1101      1     484     141  29.13     3     0  ...
    Pct 1102      1102      1     873     286  32.76    13     1  ...
    [...OTHER PRECINCTS...]
    Pct 9902 MB   9902      1       0       0   0.00     0     0  ...
    Grand Totals  City:0  597  435757  129399  29.70  4683  1223  ...

    District Grand Totals
    DistrictName  DistrictLabel  Precincts  Registration >>
     >> Ballots Cast  Turnout (%)  [...CANDIDATE NAMES...]
    12TH CONGRESSIONAL DISTRICT  Congressional:12  522  385648  114107 >>
     >> 29.59  4286  1135  ...
    [...OTHER DISTRICTS...]
    [...CITY/COUNTY...]
    [...NEIGHBORHOODS...]
    Grand Totals                 City:0            597  435757  129399 >>
     >> 29.70  4683  1223  ...

    [...ADDITIONAL CONTESTS IN SAME FORMAT AS ABOVE...]


Source Format (WinEDS)
----------------------

This section contains information about the output format of a TXT
export from the WinEDS Reporting Tool.

The file seems to be UTF-8 encoded.

Here are a few sample lines from an actual output file (the strings of
several spaces between columns were replaced by strings of two spaces):

    0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
    ...
    0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
    ...
    0175098110100082  State Proposition 42  Yes  Pct 1101  CALIFORNIA

For description purposes, we rewrite the last line as follows:

    0CCCHHHPPPPTTTTT  CONTEST_NAME  CHOICE_NAME  PRECINCT_NAME  DISTRICT_NAME

The `DISTRICT_NAME` column is a description of the area associated
with the contest.  This column is absent for the "REGISTERED VOTERS"
and "BALLOTS CAST" rows.

Here is a key for the meaning of the first block (with values for the
example above in parentheses).  The ID's can all be interpreted as
integers rather than strings.

* `CCC` = Contest ID (`175` or 175 for "State Proposition 42")
* `HHH` = Choice ID (`098` or 98 for "Yes" [on 42])
* `PPPP` = Precinct ID (`1101` for "Pct 1101")
* `TTTTT` = Vote total (`00082` for 82)


License
-------

This project is licensed under the permissive BSD 3-clause license.
See the [`LICENSE`](LICENSE) file for details.


Author
------

Chris Jerdonek (<chris.jerdonek@gmail.com>)


[dominion]: http://www.dominionvoting.com/
[python-download]: https://www.python.org/downloads/
[sf-elections]: http://sfelections.org
