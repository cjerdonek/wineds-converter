WinEDS Converter
================

This repository contains an open-source Python 3 script to convert
WinEDS 4.0 output into a simpler format.  WinEDS is an election
management system owned by [Dominion Voting Systems][dominion].


New Format
----------

This section documents the new format (i.e. the destination or target
format of the conversion).

Here is a snippet of what a file in the new format looks like.  The
column data is comma-delimited, and an empty line separates each contest.

    State Proposition 41 - CALIFORNIA
    Precinct,Precinct ID,Registration,Ballots Cast,Yes,No
    Pct 1101,1101,484,141,79,51
    Pct 1102,1102,873,286,180,83
    ...
    Pct 9901 MB,9901,0,0,0,0
    Pct 9902 MB,9902,0,0,0,0

    Local Measure B - CITY/COUNTY OF SAN FRANCI
    Precinct,Precinct ID,Registration,Ballots Cast,Yes,No
    Pct 1101,1101,484,141,85,49
    Pct 1102,1102,873,286,163,107
    ...


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

    0CCCHHHPPPPTTTTT  CONTEST  CHOICE  PRECINCT_NAME  CONTEST_AREA

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
