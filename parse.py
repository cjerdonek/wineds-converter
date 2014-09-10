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
    log("elapsed: %.4f seconds" % elapsed)


# TODO: use Python's logging module.
def log(s=None):
    """Write to stderr."""
    if s is None:
        s = ""
    print(s, file=sys.stderr)


def exit_with_error(msg):
    log(msg)
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


class ElectionResults(object):

    """
    Encapsulates election results (i.e. vote totals).

    Attributes:

      contests: a results dictionary, as described below.
      registered: a dict mapping precinct_id to a registration count.
      voted: a dict mapping precinct_id to a voter count.

    The results dictionary is a tree-like structure as follows:

      results[contest_id] -> contest_results
      contest_results[precinct_id] -> contest_precinct_results
      contest_precinct_results[choice_id] -> vote_total

    In particular, to get a vote total for a contest in a precinct:

      results[contest_id][precinct_id][choice_id]

    """

    def __init__(self):
        self.contests = {}
        self.registered = {}
        self.voted = {}


def init_results(info, results):
    """
    Initialize the results object by modifying it in place.

    Arguments:
      info: an ElectionInfo object.
      results: an ElectionResults object.

    """
    contests = results.contests
    registered = results.registered
    voted = results.voted

    for contest_id, contest_info in info.contests.items():
        contest_results = {}
        contests[contest_id] = contest_results
        for precinct_id in contest_info.precinct_ids:
            cp_results = {}  # stands for contest_precinct_results
            contest_results[precinct_id] = cp_results
            for choice_id in contest_info.choice_ids:
                cp_results[choice_id] = 0

    # Initialize the election-wide result attributes.
    for precinct_id in info.precincts.keys():
        registered[precinct_id] = 0
        voted[precinct_id] = 0

    return results


def split_line(line):
    """Return a list of field values in the line."""
    return SPLITTER.split(line.strip())


def parse_data_chunk(chunk):
    """Parse the 16-character string beginning each line."""
    # 0AAACCCPPPPTTTTT
    #
    # AAA   = contest_id
    # CCC   = choice_id
    # PPPP  = precinct_id
    # TTTTT = choice_total
    contest_id = int(chunk[1:4])
    choice_id = int(chunk[4:7])
    precinct_id = int(chunk[7:11])
    vote_total = int(chunk[11:16])
    return choice_id, contest_id, precinct_id, vote_total


def parse_line_info(contests, choices, precincts, line):
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
            raise Exception("error unpacking fields: %r" % fields)

    assert len(data) == 16
    assert data[0] == '0'
    choice_id, contest_id, precinct_id, vote_total = parse_data_chunk(data)

    try:
        old_precinct = precincts[precinct_id]
        assert old_precinct == precinct
    except KeyError:
        precincts[precinct_id] = precinct

    # The contests with the following names are special cases that need
    # to be treated differently:
    #   "REGISTERED VOTERS - TOTAL"
    #   "BALLOTS CAST - TOTAL"
    if area is None:
        assert contest_id in (1, 2)
        # TODO: both have choice ID 1, so skip them and don't store them as choices.
        return

    try:
        contest = contests[contest_id]
        assert new_contest == contest.name
        assert area == contest.area
    except KeyError:
        contest = ContestInfo(name=new_contest, area=area)
        contests[contest_id] = contest

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


def iter_lines(path):
    """
    Return an iterator over the lines of an input file.

    Each iteration yields a 2-tuple: (line_no, line).

    """
    with codecs.open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(iter(f), start=1):
            yield line_no, line
    log("parsed: %d lines" % line_no)


class Parser(object):

    def parse_line(self, line):
        raise NotImplementedError()

    def parse(self, path):
        for line_no, line in iter_lines(path):
            try:
                self.parse_line(line)
            except:
                raise Exception("error while parsing line %d: %r" % (line_no, line))


class InfoParser(Parser):

    """
    In addition to parsing the file, this class's parse() method also
    performs validation on the file to ensure that all of our assumptions
    about the file format and data are correct.
    """

    def __init__(self, info):
        """
        Arguments:
          info: an ElectionInfo object.

        """
        self.contests = info.contests
        self.choices = info.choices
        self.precincts = info.precincts

    def parse_line(self, line):
        parse_line_info(self.contests, self.choices, self.precincts, line)


class ResultsParser(Parser):

    """
    In addition to parsing the file, this class's parse() method also
    performs validation on the file to ensure that all of our assumptions
    about the file format and data are correct.
    """

    def __init__(self, results):
        """
        Arguments:
          results: an ElectionResults object.

        """
        self.contests = results.contests
        self.registered = results.registered
        self.voted = results.voted

    def parse_line(self, line):
        data = split_line(line)[0]
        choice_id, contest_id, precinct_id, vote_total = parse_data_chunk(data)
        if contest_id < 3:
            if contest_id == 1:
                precinct_totals = self.registered
            else:
                precinct_totals = self.voted
            precinct_totals[precinct_id] = vote_total
            return
        # Otherwise, we have a normal contest.

        # TODO: simplify and complete the error handling below.
        try:
            self.contests[contest_id][precinct_id][choice_id] += vote_total
        except KeyError:
            err = ("error adding vote total for chunk with: "
                   "contest_id=%d, precinct_id=%d, choice_id=%d, vote_total=%d" %
                   (contest_id, precinct_id, choice_id, vote_total))
            try:
                contest_results = self.contests[contest_id]
            except KeyError:
                err = "contest_id not found in results: " + err
            raise Exception(err)


def make_election_info(path, name):
    """
    Parse the file, and create an ElectionInfo object.

    """
    info = ElectionInfo(name)
    parser = InfoParser(info)
    parser.parse(path)

    choices = info.choices
    contests = info.contests

    for choice_id, (contest_id, choice_name) in choices.items():
        contest = contests[contest_id]
        contest.choice_ids.add(choice_id)

    return info


def process_input(path, name):
    """
    Modify the ElectionInfo object in place and return a results dict.

    """
    # We parse the file in two passes to simplify the logic and make the
    # code easier to understand.
    #
    # In the first pass, we read all the election "metadata" (contests,
    # choices, precincts, etc) and validate the integer ID's, etc, to
    # make sure that all of our assumptions about the file format are
    # correct.
    #
    # After the first pass, we construct a results object in which to
    # store values.  Essentially, this is a large tree-like dictionary
    # of contests, precincts, vote totals, etc.
    #
    # Then we parse the file a second time, but without doing any
    # validation.  We simply read the vote totals and insert them into
    # the object structure.

    # Pass #1
    info = make_election_info(path, name)

    results = ElectionResults()
    init_results(info, results)

    # Pass #2
    parser = ResultsParser(results)
    parser.parse(path)

    return info, results


class ResultsWriter(object):

    """
    Responsible for writing output to a file.

    """

    def __init__(self, file, info, results):
        self.file = file
        self.info = info
        self.results = results

    def write_ln(self, s=""):
        print(s, file=self.file)

    def write_values(values):
        self.write_ln(",".join(values))

    def write_contest(self, precincts, choices, contest_info, contest_results):
        """
        Arguments:
          precincts: the ElectionInfo.precincts dict.
          choices: the ElectionInfo.choices dict.
          contest_info: a ContestInfo object.

        """
        self.write_ln("%s - %s" % (contest_info.name, contest_info.area))
        contest_choice_ids = sorted(contest_info.choice_ids)
        columns = ["VotingPrecinctName", "VotingPrecinctID", "Registration", "Ballots Cast"]
        # Collect the choice names.
        columns += [choices[choice_id][1] for choice_id in contest_choice_ids]
        self.write_ln(",".join(columns))

        results = self.results
        registered = results.registered
        voted = results.voted
        precinct_ids = sorted(contest_info.precinct_ids)
        for pid in precinct_ids:
            precinct_results = contest_results[pid]
            values = [precincts[pid], str(pid), str(registered[pid]), str(voted[pid])]
            values += [str(precinct_results[cid]) for cid in contest_choice_ids]
            self.write_ln(",".join(values))

    def write(self):
        """Write the election results to the given file."""
        info = self.info
        results = self.results

        choices = info.choices
        info_contests = info.contests
        precincts = info.precincts
        results_contests = results.contests

        self.write_ln(info.name)
        self.write_ln()
        for contest_id in sorted(info_contests.keys()):
            contest_info = info_contests[contest_id]
            contest_results = results_contests[contest_id]
            self.write_contest(precincts, choices, contest_info, contest_results)
            self.write_ln()


def inner_main(argv):
    try:
        # TODO: use argparse.
        name, input_path = argv[1:]
    except ValueError:
        exit_with_error("You must provide two values: NAME and PATH.")

    info, results = process_input(input_path, name)

    log("parsed election: %r" % info)

    choices = info.choices
    contests = info.contests
    precincts = info.precincts

    log("Contests:")
    for cid in sorted(contests):
        contest = contests[cid]
        log("%s %s" % (cid, contests[cid]))
    log()

    log("Choices:")
    for cid in sorted(choices):
        choice = choices[cid]
        log("%r: %s, %s" % (cid, choice[0], choice[1]))
    log()

    # TODO: use logging.
    log("parsed: %d contests" % len(contests))
    log("parsed: %d choices" % len(choices))
    log("parsed: %d precincts" % len(precincts))

    writer = ResultsWriter(file=sys.stdout, info=info, results=results)
    writer.write()


def main(argv):
    with time_it():
        inner_main(argv)


if __name__ == "__main__":
    main(sys.argv)
