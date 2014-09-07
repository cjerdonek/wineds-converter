#!/usr/bin/env python

"""
Usage: python parse.py PATH

PATH is a path to a WinEDS Reporting Tool output file.

"""

import re
import sys
import timeit

splitter = re.compile(r'\s{2,}')

class Contest(object):

    def __init__(self, name, area):
        self.name = name
        self.area = area

    def __repr__(self):
        return "Contest(name=%r, area=%r)" % (self.name, self.area)

def parse_line(line_no, election, line):
    # Split on strings of whitespace with 2 or more characters.
    # This is necessary since field values can contain spaces.
    fields = splitter.split(line.strip())
    try:
        data, contest, choice, precinct, area = fields
    except ValueError:
        # This can occur for summary lines like the following that lack an area:
        # 0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
        # 0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
        fields.append(None)
        try:
            data, contest, choice, precinct, area = fields
        except ValueError:
            raise Exception("error unpacking line %d: %r" % (line_no, fields))

    # 0AAACCCPPPPTTTTT
    #
    # AAA   = contest_id
    # CCC   = choice_id
    # PPPP  = precinct_id
    # TTTTT = choice_total
    assert len(data) == 16
    assert data[0] == '0'
    contest_id = int(data[1:4])
    choice_id = int(data[4:7])
    precinct_id = int(data[7:11])
    choice_total = int(data[11:16])

    try:
        old_contest = election[contest_id]
        assert old_contest.name == contest
        assert old_contest.area == area
    except KeyError:
        election[contest_id] = Contest(name=contest, area=area)

    return fields

def main(argv):
    try:
        input_path = argv[1]
    except IndexError:
        raise Exception("PATH not provided on command-line")

    start_time = timeit.default_timer()

    # A dict of contest ID to contest data.
    election = {}

    with open(input_path, 'rb') as f:
        for line_no, line in enumerate(iter(f), start=1):
            data = parse_line(line_no, election, line)

    elapsed = timeit.default_timer() - start_time

    contest_ids = election.keys()
    contest_ids.sort()
    for cid in contest_ids:
        print cid, election[cid]

    print "parsed: %d lines" % line_no
    print "elapsed: %.4f seconds" % elapsed

if __name__ == "__main__":
    main(sys.argv)
