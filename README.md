WinEDS Converter
================

This repository contains a script to convert WinEDS 4.0 output into a
simpler format.  WinEDS is an election management system owned by
[Dominion Voting Systems][dominion].


WinEDS Reporting Tool
---------------------

This section contains a description of the output format of a TXT export
from the WinEDS Reporting Tool.

Here is a sample line of a sample output file (the strings of several
spaces between columns were replaced by strings of two spaces):

    0175098110100082  State Proposition 42  Yes  Pct 1101  CALIFORNIA

For description purposes, we rewrite this as follows:

    0AAACCCPPPPTTTTT  CONTEST  CHOICE  PRECINCT_NAME  CONTEST_AREA

Here is a key (with values for the example above in parentheses):

* AAA = Contest ID? (175, representing "State Proposition 42")
* CCC = Choice ID? (098, representing "Yes" [on 42, specifically])
* PPPP = Precinct ID (1101, representing "Pct 1101")
* TTTTT = Choice total (00082)


[dominion]: http://www.dominionvoting.com/
