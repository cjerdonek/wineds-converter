#!/usr/bin/env python

"""
Usage: python3 parse.py NAME PATH

NAME: the election name.

PATH: path to a WinEDS Reporting Tool output file.  A relative path
  will be interpreted as relative to the current working directory.

**Note: this script is written for Python 3.**

"""

import codecs
from contextlib import contextmanager
import re
import sys
import timeit


# We split on strings of whitespace having 2 or more characters.  This is
# necessary since field values can contain spaces (e.g. candidate names).
SPLITTER = re.compile(r'\s{2,}')


@contextmanager
def time_it():
    start_time = timeit.default_timer()
    yield
    elapsed = timeit.default_timer() - start_time
    print("elapsed: %.4f seconds" % elapsed)


# TODO: use Python's logging module.
def log(s):
    """Write to stderr."""
    print(s, file=sys.stderr)


def exit_with_error(msg):
    print(msg)
    exit(1)


class ContestInfo(object):

    """
    Encapsulates metadata about a contest (but not results).

    """

    def __init__(self, name, area):
        self.choice_ids = set()
        self.precinct_ids = set()
        self.name = name
        self.area = area

    def __repr__(self):
        return ("<ContestInfo object: name=%r, area=%r, %d precincts, %d choices)" %
                (self.name, self.area, len(self.precinct_ids), len(self.choice_ids)))

class ElectionInfo(object):

    """
    Encapsulates election metadata (but not results).

    Attributes:

      choices: a dict of integer choice ID to a 2-tuple of
        (contest_id, choice_name).
      contests: a dict of integer contest_id to ContestInfo object.
      precincts: a dict of integer precinct ID to precinct name.

    """

    def __init__(self, name):
        self.choices = {}
        self.contests = {}
        self.precincts = {}

        self.name = name

    def __repr__(self):
        return ("<ElectionInfo object: %d contests, %d choices, %d precincts>" %
                (len(self.contests), len(self.choices), len(self.precincts)))


def split_line(line):
    """Return a list of field values in the line."""
    return SPLITTER.split(line.strip())


def iter_lines(path):
    """
    Return an iterator over the lines of an input file.

    Each iteration yields a 2-tuple: (line_no, line).

    """
    with codecs.open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(iter(f), start=1):
            yield line_no, line
    print("parsed: %d lines" % line_no)


def parse_line_info(contests, choices, precincts, line_no, line):
    """
    This function does not populate contest.choice_ids for the objects
    in contests.

    """
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
        contest = ContestInfo(name=new_contest, area=area)
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

    # TODO: change precincts to a set and validate that each precinct
    # appears only once.
    contest.precinct_ids.add(precinct_id)


def parse_election_info(path, info):
    """
    Parse the given file, and return an ElectionInfo object.

    In addition to parsing the file, this function also performs
    validation on the file to ensure that all of our assumptions about
    the file format and data are correct.
    """
    contests = info.contests
    choices = info.choices
    precincts = info.precincts

    for line_no, line in iter_lines(path):
        parse_line_info(contests, choices, precincts, line_no, line)

    for choice_id, (contest_id, choice_name) in choices.items():
        contest = contests[contest_id]
        contest.choice_ids.add(choice_id)

    return info


def init_results(info):
    """
    Return a tree-like results dictionary.

    Returns:
      results: a dict mapping contest_id to contest_results.

    contest_results: a dict mapping precinct_id to contest_precinct_results.

    contest_precinct_results: a dict mapping choice_id to an integer vote
        total for the choice in that precinct for that contest.

    """
    results = {}
    for contest_id, contest_info in info.contests.items():
        contest_results = {}
        results[contest_id] = contest_results
        for precinct_id in contest.precinct_ids:
            precinct_totals = {}
            contest_totals[precinct_id] = precinct_totals
            for choice_id in contest.choice_ids:
                precinct_totals[choice_id] = 0


def parse_results(path):

    with codecs.open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(iter(f), start=1):
            data = split_line(line)[0]


def parse(path, info):
    """
    Return an ElectionInfo object.

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
    parse_election_info(path, info)

    # TODO: also return a results object.
    return info


def write_results(f, info):
    print(info.name, file=f)


def inner_main(argv):
    try:
        # TODO: use argparse.
        name, input_path = argv[1:]
    except ValueError:
        exit_with_error("You must provide two values: NAME and PATH.")

    info = ElectionInfo(name)
    parse(input_path, info)

    print("parsed election: %r" % info)

    choices = info.choices
    contests = info.contests
    precincts = info.precincts

    print("Contests:")
    for cid in sorted(contests):
        contest = contests[cid]
        print(cid, contests[cid])
    print

    print("Choices:")
    for cid in sorted(choices):
        choice = choices[cid]
        print("%r: %s, %s" % (cid, choice[0], choice[1]))
    print()

    # TODO: use logging.
    print("parsed: %d contests" % len(contests))
    print("parsed: %d choices" % len(choices))
    print("parsed: %d precincts" % len(precincts))

    output_file = sys.stdout
    write_results(output_file, info)


def main(argv):
    with time_it():
        inner_main(argv)


if __name__ == "__main__":
    main(sys.argv)
