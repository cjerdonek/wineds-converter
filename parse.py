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
        self.choices = {}
        self.precincts = {}
        self.name = name
        self.area = area

    def __repr__(self):
        return ("Contest(name=%r, area=%r, precincts=%d, choices=%d)" %
                (self.name, self.area, len(self.precincts), len(self.choices)))

def parse_line(contests, choices, precincts, line_no, line):
    # Split on strings of whitespace with 2 or more characters.
    # This is necessary since field values can contain spaces.
    fields = splitter.split(line.strip())
    try:
        data, new_contest, new_choice, precinct, area = fields
    except ValueError:
        # This can occur for summary lines like the following that lack an area:
        # 0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
        # 0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
        fields.append(None)
        try:
            data, new_contest, new_choice, precinct, area = fields
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
        old_precinct = precincts[precinct_id]
        assert old_precinct == precinct
    except KeyError:
        precincts[precinct_id] = precinct

    try:
        contest = contests[contest_id]
        assert new_contest == contest.name
        assert area == contest.area
    except KeyError:
        contest = Contest(name=new_contest, area=area)
        contests[contest_id] = contest

    # The "REGISTERED VOTERS - TOTAL" and "BALLOTS CAST - TOTAL" contests
    # both have choice ID 1, so skip them and don't store them as choices.
    if area is not None:
        try:
            choice = choices[choice_id]
            try:
                assert choice == (contest_id, new_choice)
            except AssertionError:
                raise Exception("choice mismatch for choice ID %d: %r != %r" %
                                (choice_id, choice, (contest_id, new_choice)))
        except KeyError:
            choice = (contest_id, new_choice)
            choices[choice_id] = choice
        contest.choices[choice_id] = True

    contest.precincts[precinct_id] = True


def main(argv):
    try:
        input_path = argv[1]
    except IndexError:
        raise Exception("PATH not provided on command-line")

    start_time = timeit.default_timer()

    # A dict of contest ID to Contest object.
    contests = {}
    # A dict of precinct ID to precinct name.
    precincts = {}
    # A dict of choice ID to (contest_id, choice name).
    choices = {}

    with open(input_path, 'rb') as f:
        for line_no, line in enumerate(iter(f), start=1):
            parse_line(contests, choices, precincts, line_no, line)

    elapsed = timeit.default_timer() - start_time

    contest_ids = contests.keys()
    contest_ids.sort()
    print "Contests:"
    for cid in contest_ids:
        print cid, contests[cid]
    print

    choice_ids = choices.keys()
    choice_ids.sort()
    print "Choices:"
    for cid in choice_ids:
        print "%r: %r" % (cid, choices[cid])
    print

    print "parsed: %d contests" % len(contests)
    print "parsed: %d choices" % len(choices)
    print "parsed: %d precincts" % len(precincts)
    print "parsed: %d lines" % line_no
    print "elapsed: %.4f seconds" % elapsed

if __name__ == "__main__":
    main(sys.argv)
