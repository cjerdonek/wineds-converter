WinEDS Converter
================

[![Build Status](https://travis-ci.org/cjerdonek/wineds-converter.svg?branch=master)][travis-ci-project-page]

This repository contains an open-source Python 3 script to generate
Statement of Votes for elections run using WinEDS 4.0.  It creates both
a machine-readable file using an open format (specifically tab-separated
value, aka TSV), as well as Excel with the `.xlsx` extension.

WinEDS is an election management system owned by [Dominion Voting Systems][dominion].
Out of the box, the system only makes it easy to generate a PDF.

See the [License](#license) section for open-source license information.


Features
--------

The script in this repository is tailored for use in San Francisco elections
held by the [San Francisco Department of Elections][sf-elections].
However, it wouldn't be too hard to modify the code for other jurisdictions.

The input is the raw TEXT output from the WinEDS Reporting Tool.
Preferably, the input file should include undervotes, overvotes, and
the Election Day & VBM breakdown.

The TSV and Excel output files both have formats resembling the PDF
Statements of Vote released by the SF Department of Elections.
In particular, the output includes the following for each contest:

* a Precinct Report with Election Day & VBM subtotals,
* overvote and undervote totals,
* percent turnout, and
* district and neighborhood subtotals.

In addition, the Excel file has a table of contents, and each contest
is in its own Excel worksheet.

Here is information on the running time of the script and the sizes of
the output files.  For the June 3, 2014 election in San Francisco, the
WinEDS input TEXT file was 30.7 MB.  On this file using an old Macbook Pro,
the script took about 15 seconds to generate both files.  The TSV and
Excel output files were both 1.2 MB.  In contrast, the PDF Statement of
Vote was 8.1 MB.


Setting up
----------

The script was written for Python 3.4.  You can download and install
Python 3.4 [from here][python-download].

Then clone this repo.

And install third-party requirements:

    $ pip install XlsxWriter

And follow the usage instructions below.


Usage
-----

To run the script, run the following from the repo root--

    $ python3.4 convert.py ELECTION_NAME PRECINCTS.csv WINEDS.txt OUTPUT_BASE

This creates two files by adding the `.tsv` and `.xlsx` extensions:
`OUTPUT_BASE.tsv` and `OUTPUT_BASE.xlsx`.

For convenience, the precinct file for the June 2014 and November 2014
elections is contained in this repository inside the folder
`data/election-2014-06-03`.  So you can type the following, for example:

    $ python3.4 convert.py "November 4, 2014 Election" \
       data/election-2014-06-03/precincts_20140321.csv WINEDS.txt OUTPUT.tsv

For additional usage notes, see the docstring of the main
[`convert.py`](convert.py#L7) file.


Testing
-------

To test the script, run the following from the repo root--

    $ python3.4 -m pywineds.test

This runs some unit tests, as well as some end-to-end tests whose input and
expected output files are located in the [`test_data/`](test_data) directory.

These tests are also run automatically on [Travis CI][travis-ci].


New Format
----------

To see an example of what the new output format looks like, see the
"expected" output file of the end-to-end test located at
[`test_data/complete/output.tsv`](test_data/complete/output.tsv).

The format is largely self-explanatory.


Source Format (WinEDS)
----------------------

This section contains information about the output format of a TXT
export from the WinEDS Reporting Tool.

The lines seem to have fixed-width columns.  In particular, not all
columns are separated by white space.  For example, one actual file
had this substring: "13TH CONGRESSIONAL DISTRITC-Election Day Reporting".
In this case, the column division is between "DISTRI" and "TC-Election".

We assume the file is UTF-8 encoded, though we have not confirmed this yet.

Here are a few sample lines from an actual output file (the strings of
several spaces between columns were replaced by strings of two spaces):

    0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
    ...
    0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
    ...
    0175098110100082  State Proposition 42  Yes  Pct 1101  CALIFORNIA

And from a "complete" file (i.e. with VBM breakdown):

    0100001110100000GRN  Governor  LUIS J. RODRIGUEZ  Pct 1101  CALIFORNIA \
      TC-Election Day Reporting

For description purposes, we rewrite the last line as follows:

    0CCCHHHPPPPTTTTT[PTY]  CONTEST_NAME  CHOICE_NAME  PRECINCT_NAME \
      DISTRICT_NAME  [REPORTING_TYPE]

The `DISTRICT_NAME` column is a description of the area associated
with the contest.  This column is absent for the "REGISTERED VOTERS"
and "BALLOTS CAST" rows.  The `REPORTING_TYPE` column is not present for all
export files.  Its value can be either `TC-Election Day Reporting`,
`TC-VBM Reporting`, or the empty string.

Here is a key for the meaning of the first block (with values for the
example above in parentheses).  The ID's can all be interpreted as
integers rather than strings.

* `CCC` = Contest ID (`175` or 175 for "State Proposition 42")
* `HHH` = Choice ID (`098` or 98 for "Yes" [on 42])
* `PPPP` = Precinct ID (`1101` for "Pct 1101")
* `TTTTT` = Vote total (`00082` for 82)
* `[PTY]` = Party abbreviation of the candidate (optional and variable-length,
  e.g. "DEM", "REP", "NON, "PF", etc.)

There are also some lines with initial fields of the form--

    01000167208000-1NON       Governor


Developing
----------

There are some commands to assist with developing, for example to create
smaller output files for testing purposes.  For a list of these, see the
code and comments near the `main()` function, where `sys.argv` is parsed.


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
[travis-ci]: https://travis-ci.org/
[travis-ci-project-page]: https://travis-ci.org/cjerdonek/wineds-converter
