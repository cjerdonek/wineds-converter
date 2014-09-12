#!/usr/bin/env python
#
# **THIS SCRIPT IS WRITTEN FOR PYTHON 3.**
#

"""\
Usage: python3 parse.py NAME DISTRICTS_PATH RESULTS_PATH

Arguments:

  NAME: the name of the election.

  DISTRICTS_PATH: path to a CSV file mapping precincts to their
    different districts.

  RESULTS_PATH: path to a WinEDS Reporting Tool output file that contains
    vote totals for each precinct in each contest.

In the above, relative paths will be interpreted as relative to the
current working directory.
"""

import codecs
from contextlib import contextmanager
import re
import sys
import timeit


DISTRICT_TYPES = {
    'Assembly': ('assembly', '%sTH ASSEMBLY DISTRICT'),
    'BART': ('bart', 'BART DISTRICT %s'),
    'Congressional': ('congress', '%sTH CONGRESSIONAL DISTRICT'),
    'Neighborhood': ('neighborhood', None),
    'Senatorial': ('senate', '%sTH SENATORIAL DISTRICT'),
    'Supervisorial': ('supervisor', 'SUPERVISORIAL DISTRICT %s')
}

# This constant is a convenience to let us write code that is more DRY.
# This does not include the "city" and "neighborhoods" attributes.
DISTRICT_INFO_ATTRS = ('assembly', 'bart', 'congress', 'senate', 'supervisor')

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


class DistrictInfo(object):

    """
    Encapsulates what precincts are in what districts.

    """

    def __init__(self):
        # These are all dicts mapping district number to set of precinct_ids.
        # The neighborhood dict is slightly different in that the keys
        # are strings instead of integers.
        self.assembly = {}
        self.bart = {}
        self.city = set()  # all precinct IDs.
        self.congress = {}
        self.neighborhoods = {}
        self.senate = {}
        self.supervisor = {}


class ElectionInfo(object):

    """
    Encapsulates election metadata (but not results).

    Attributes:

      choices: a dict of integer choice ID to a 2-tuple of
        (contest_id, choice_name).
      contests: a dict of integer contest_id to ContestInfo object.
      neighborhoods: a dict mapping neighborhood string label to string name.
        For example, "BAYVW/HTRSPT" maps to "BAYVIEW/HUNTERS POINT".
      precincts: a dict of integer precinct ID to precinct name.

    """

    def __init__(self, name, district_info):
        """
        Arguments:
          district_info: a DistrictInfo object.

        """
        self.choices = {}
        self.contests = {}
        self.districts = district_info
        self.neighborhoods = {}
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

    # TODO: validate that each precinct appears only once.
    contest.precinct_ids.add(precinct_id)


class Parser(object):

    line_no = 0
    line = None

    def iter_lines(self, path):
        """
        Return an iterator over the lines of an input file.

        Each iteration yields a 2-tuple: (line_no, line).

        """
        log("parsing: %s" % path)
        with codecs.open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(iter(f), start=1):
                self.line = line
                self.line_no = line_no
                # This yields no values because we set the information
                # we need as instance attributes instead.  This is more
                # convenient for things like our Parser exception handler.
                yield
        log("parsed: %d lines" % line_no)

    def parse_line(self, line):
        raise NotImplementedError()

    def parse_body(self, path):
        for x in self.iter_lines(path):
            self.parse_line(self.line)

    def parse(self, path):
        try:
            self.parse_body(path)
        except:
            raise Exception("error while parsing line %d: %r" %
                            (self.line_no, self.line))


class DistrictInfoParser(Parser):

    """
    Parses a CSV file with information about precincts and districts.

    """

    def __init__(self, district_info):
        """
        Arguments:
          info: a DistrictInfo object.

        """
        self.district_info = district_info

    def add_precinct(self, attr, precinct_id, value):
        districts = getattr(self.district_info, attr)
        try:
            precinct_ids = districts[value]
        except KeyError:
            precinct_ids = set()
            districts[value] = precinct_ids
        precinct_ids.add(precinct_id)

    def parse_line(self, line):
        # Here are the column headers of the file:
        #   VotingPrecinctID,VotingPrecinctName,MailBallotPrecinct,BalType,
        #   Assembly,BART,Congressional,Neighborhood,Senatorial,Supervisorial
        values = line.strip().split(",")
        precinct_id = int(values[0])
        # Includes: Assembly,BART,Congressional,Neighborhood,Senatorial,Supervisorial
        values = values[4:]
        nbhd_label = values.pop(3)
        for attr, value in zip(DISTRICT_INFO_ATTRS, values):
            self.add_precinct(attr, precinct_id, int(value))

        self.add_precinct('neighborhoods', precinct_id, nbhd_label)
        self.district_info.city.add(precinct_id)

    def parse_body(self, path):
        lines = self.iter_lines(path)
        next(lines)  # Skip the header line.
        for x in lines:
            self.parse_line(self.line)

class ElectionInfoParser(Parser):

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


def make_election_info(path, name, district_info):
    """
    Parse the file, and create an ElectionInfo object.

    """
    info = ElectionInfo(name, district_info)
    parser = ElectionInfoParser(info)
    parser.parse(path)

    choices = info.choices
    contests = info.contests

    for choice_id, (contest_id, choice_name) in choices.items():
        contest = contests[contest_id]
        contest.choice_ids.add(choice_id)

    return info


def digest_input_files(name, districts_path, wineds_path):
    """
    Read the input files and return a 2-tuple of an ElectionInfo
    object and an ElectionResults object.

    """
    district_info = DistrictInfo()
    parser = DistrictInfoParser(district_info)
    parser.parse(districts_path)

    # TODO: remove this debug code.
    for attr in DISTRICT_INFO_ATTRS:
        data = getattr(district_info, attr)
        log(attr)
        for num, precinct_ids in data.items():
            log("%d: %d" % (num, len(precinct_ids)))

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
    election_info = make_election_info(wineds_path, name, district_info)

    # Check that the precincts in the district file match the precincts
    # in the results file.
    for i, (p1, p2) in enumerate(zip(sorted(district_info.city),
                                     sorted(election_info.precincts.keys())), start=1):
        try:
            assert p1 == p2
        except AssertionError:
            exit_with_error("precinct %d differs: %r != %r" % (i, p1, p2))

    results = ElectionResults()
    init_results(election_info, results)

    # Pass #2
    parser = ResultsParser(results)
    parser.parse(wineds_path)

    return election_info, results


class ResultsWriter(object):

    """
    Responsible for writing output to a file.

    """

    district_keys = (
        'Congressional',
        'Senatorial',
        'Assembly',
        'BART',
        'Supervisorial'
    )

    def __init__(self, file, info, results):
        self.file = file
        self.election_info = info
        self.results = results

    def write_ln(self, s=""):
        print(s, file=self.file)

    # TODO: remove this.
    def write_values(values):
        self.write_ln(",".join(values))

    def write_row(self, *values):
        self.write_ln(",".join([str(v) for v in values]))

    def write_district_type_summary(self, choice_ids, type_label):
        attr, format_name = DISTRICT_TYPES[type_label]
        numbers = getattr(self.election_info.districts, attr)
        for number in sorted(numbers):
            name = format_name % number
            label = "%s_%s" % (type_label, number)
            self.write_row(name, label, *choice_ids)

    def write_contest_summary(self, choice_ids):
        """
        Arguments:
          choice_ids: an iterable of choice IDs.

        """
        self.write_ln("District Grand Totals")
        for district_key in self.district_keys:
            self.write_district_type_summary(choice_ids, district_key)

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
        # TODO: remove the next line.
        precinct_ids = []
        for pid in precinct_ids:
            precinct_results = contest_results[pid]
            values = [precincts[pid], str(pid), str(registered[pid]), str(voted[pid])]
            values += [str(precinct_results[cid]) for cid in contest_choice_ids]
            self.write_ln(",".join(values))
        self.write_ln()
        self.write_contest_summary(contest_choice_ids)

    def write(self):
        """Write the election results to the given file."""
        info = self.election_info
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
            self.write_ln()


def inner_main(argv):
    try:
        # TODO: use argparse.
        name, districts_path, results_path = argv[1:]
    except ValueError:
        exit_with_error("%s\nERROR: incorrect number of arguments" % __doc__)

    info, results = digest_input_files(name, districts_path, results_path)

    writer = ResultsWriter(file=sys.stdout, info=info, results=results)
    writer.write()


def main(argv):
    with time_it():
        inner_main(argv)


if __name__ == "__main__":
    main(sys.argv)
