The test files in this directory cover the case of duplicate contest IDs.

It turns out that WinEDS can assign the same integer contest ID to
multiple contests when the ID reaches 255.  This happened in the
November 2014 election in San Francisco.

The solution we chose is to use the contest name as the ID.
