#!/usr/bin/env python

"""
Usage: python parse.py PATH

PATH is a path to a WinEDS Reporting Tool output file.

"""

import codecs
import re
import sys
import timeit

# We split on strings of whitespace having 2 or more characters.  This is
# necessary since field values can contain spaces (e.g. candidate names).
SPLITTER = re.compile(r'\s{2,}')

class Contest(object):

    def __init__(self, name, area):
        # Change these to choice_ids and precinct_ids.
        self.choices = {}
        self.precincts = {}
        self.name = name
        self.area = area

    def __repr__(self):
        return ("Contest(name=%r, area=%r, precincts=%d, choices=%d)" %
                (self.name, self.area, len(self.precincts), len(self.choices)))

def split_line(line):
    """Return a list of field values in the line."""
    return SPLITTER.split(line.strip())

def parse_line(contests, choices, precincts, line_no, line):
    fields = split_line(line)
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


def parse_election_metadata(path):
    pass

def parse(path):
    """
    We parse and process the file in two passes to simplify the logic
    and make the code easier to understand.

    In the first pass, we read all the election "metadata" (contests,
    choices, precincts, etc) and validate the integer ID's, etc, to
    make sure that all of our assumptions about the file format are
    correct.

    After the first pass, we build an object structure in which to
    store values.  Essentially, this is a large tree-like dictionary
    of contests and vote totals per precinct for each contest.

    Then we parse the file a second time, but without doing any validation.
    We simply read the vote totals and insert them into the object
    structure.

    """
    with codecs.open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(iter(f), start=1):
            data = split_line(line)[0]

def init_results(contests):
    """
    Returns a tree-like results dictionary:

    totals:
        contest_id:
            precinct_id:
                choice_id:
                    vote_total

    """
    totals = {}
    for contest_id, contest in contests.iteritems():
        contest_totals = {}
        totals[contest_id] = contest_totals
        for precinct_id in contest.precincts:
            precinct_totals = {}
            contest_totals[precinct_id] = precinct_totals
            for choice_id in contest.choices:
                precinct_totals[choice_id] = 0

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

    with codecs.open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(iter(f), start=1):
            parse_line(contests, choices, precincts, line_no, line)

    elapsed = timeit.default_timer() - start_time

    contest_ids = contests.keys()
    contest_ids.sort()
    print "Contests:"
    for cid in contest_ids:
        print cid, contests[cid]
    print

    print "Choices:"
    for cid in sorted(choices):
        choice = choices[cid]
        print "%r: %s, %s" % (cid, choice[0], choice[1])
    print

    print "parsed: %d contests" % len(contests)
    print "parsed: %d choices" % len(choices)
    print "parsed: %d precincts" % len(precincts)
    print "parsed: %d lines" % line_no
    print "elapsed: %.4f seconds" % elapsed

if __name__ == "__main__":
    main(sys.argv)
