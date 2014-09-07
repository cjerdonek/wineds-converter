WinEDS Converter
================

This repository contains a script to convert WinEDS 4.0 output into a
simpler format.  WinEDS is an election management system owned by
[Dominion Voting Systems][dominion].


New Format
----------

This section documents the new format.

Here is an example of what the file looks like (tab-delimited):

    SAN FRANCISCO PRIMARY ELECTION JUNE 3, 2014

    State Treasurer - CALIFORNIA
    PRECINCT	ELLEN H. BROWN	GREG CONLON	JOHN CHIANG


WinEDS Reporting Tool
---------------------

This section contains a description of the output format of a TXT export
from the WinEDS Reporting Tool.

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

[dominion]: http://www.dominionvoting.com/
