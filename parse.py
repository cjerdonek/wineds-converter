#!/usr/bin/env python
#
# **THIS SCRIPT IS WRITTEN FOR PYTHON 3.**
#

"""\
Usage: python3 parse.py ELECTION_NAME DISTRICTS_PATH RESULTS_PATH

Arguments:

  ELECTION_NAME: the name of the election, for display purposes.
    This appears in the first line of the output file.

  DISTRICTS_PATH: path to a CSV file mapping precincts to their
    different districts.

  RESULTS_PATH: path to a WinEDS Reporting Tool output file that contains
    vote totals for each precinct in each contest.

In the above, relative paths will be interpreted as relative to the
current working directory.
"""

import codecs
from contextlib import contextmanager
from datetime import datetime
import re
import sys
import timeit


# We split on strings of whitespace having 2 or more characters.  This is
# necessary since field values can contain spaces (e.g. candidate names).
SPLITTER = re.compile(r'\s{2,}')

# Information about the area types whose name can be generated from a
# format string and an area or district number.  This does not include
# the "city" and "neighborhood" types.
AREA_INFO = {
    'Assembly': ('assembly', '%sTH ASSEMBLY DISTRICT'),
    'BART': ('bart', 'BART DISTRICT %s'),
    'Congressional': ('congress', '%sTH CONGRESSIONAL DISTRICT'),
    'Senatorial': ('senate', '%sTH SENATORIAL DISTRICT'),
    'Supervisorial': ('supervisor', 'SUPERVISORIAL DISTRICT %s')
}

# TODO: remove this constant.
# This constant is a convenience to let us write code that is more DRY.
# This does not include the "city" and "neighborhoods" attributes.
DISTRICT_INFO_ATTRS = ('assembly', 'bart', 'congress', 'senate', 'supervisor')

# This string contains a mapping from neighborhood labels in the
# precinct-to-neighborhood file to the more human-friendly names that
# appear in the Statements of Vote.
NEIGHBORHOODS = """
BAYVW/HTRSPT:BAYVIEW/HUNTERS POINT
CHINA:CHINATOWN
CVC CTR/DWTN:CIVIC CENTER/DOWNTOWN
DIAMD HTS:DIAMOND HEIGHTS
EXCELSIOR:EXCELSIOR (OUTER MISSION)
HAIGHT ASH:HAIGHT ASHBURY
INGLESIDE:INGLESIDE
INNER SUNSET:INNER SUNSET
LAKE MERCED:LAKE MERCED
LRL HTS/ANZA:LAUREL HEIGHTS/ANZA VISTA
MAR/PAC HTS:MARINA/PACIFIC HEIGHTS
MISSION:MISSION
N BERNAL HTS:NORTH BERNAL HTS
N EMBRCDRO:NORTH EMBARCADERO
NOE VALLEY:NOE VALLEY
PORTOLA:PORTOLA
POTRERO HILL:POTRERO HILL
RICHMOND:RICHMOND
S BERNAL HTS:SOUTH BERNAL HEIGHT
SECLF/PREHTS:SEA CLIFF/PRESIDIO HEIGHTS
SOMA:SOUTH OF MARKET
SUNSET:SUNSET
UPRMKT/EURKA:UPPER MARKET/EUREKA VALLEY
VISITA VLY:VISITATION VALLEY
W TWIN PKS:WEST OF TWIN PEAKS
WST ADDITION:WESTERN ADDITION
"""

def make_nbhd_names():
    """
    Return a dict mapping neighborhood labels to human-friendly names.

    """
    data = {}
    for s in NEIGHBORHOODS.strip().splitlines():
        label, name = s.split(":")
        data[label] = name
    return data


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


class AreaPrecincts(object):

    """
    Encapsulates what precincts are in what districts and areas.

    Each attribute corresponds to an "area type".  With the exception
    of the city attribute, each attribute is a dict that maps an integer
    area ID (or string in the case of neighborhoods) to a set of integer
    precinct IDs.  Each key in the dict represents an "area" or district.

    The city attribute is a simple set of integer precinct IDs (because
    there is only one area corresponding to the "city" area type).

    """

    def __init__(self):
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

    nbhd_names = make_nbhd_names()

    def __init__(self, name, district_index):
        """
        Arguments:
          district_index: a AreaPrecincts object.

        """
        self.choices = {}
        self.contests = {}
        self.area_index = district_index
        self.precincts = {}

        self.name = name

    def __repr__(self):
        return ("<ElectionInfo object: %d contests, %d choices, %d precincts>" %
                (len(self.contests), len(self.choices), len(self.precincts)))


class ElectionResults(object):

    """
    Encapsulates election results (i.e. vote totals).

    Attributes:

      contests: a dictionary, as described below.
      registered: a dict mapping precinct_id to a registration count.
      voted: a dict mapping precinct_id to a voter count.

    The contests dictionary is a tree-like structure as follows:

      contests[contest_id] -> contest_results
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


class PrecinctIndexParser(Parser):

    """
    Parses a CSV file with information about precincts and districts.

    """

    def __init__(self, district_index):
        """
        Arguments:
          district_index: a AreaPrecincts object.

        """
        self.district_info = district_index

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
    area_precincts = AreaPrecincts()
    parser = PrecinctIndexParser(area_precincts)
    parser.parse(districts_path)

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
    # of contests, precincts, vote totals (that start zeroed out), etc.
    #
    # Then we parse the file a second time, but without doing any
    # validation.  We simply read the vote totals and insert them into
    # the object structure.

    # Pass #1
    election_info = make_election_info(wineds_path, name, area_precincts)

    # Check that the precincts in the district file match the precincts
    # in the results file.
    for i, (p1, p2) in enumerate(zip(sorted(area_precincts.city),
                                     sorted(election_info.precincts.keys())), start=1):
        try:
            assert p1 == p2
        except AssertionError:
            exit_with_error("precinct %d differs: %r != %r" % (i, p1, p2))

    # Construct the results object.
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

    district_type_names = (
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

    def write_row(self, *values):
        self.write_ln(",".join([str(v) for v in values]))

    def write_totals_row_header(self, name_header, id_header, contest_choice_ids):
        choices = self.election_info.choices
        # Each choices value is a 2-tuple of (contest_id, choice_name).
        choice_names = (choices[choice_id][1] for choice_id in contest_choice_ids)
        self.write_row(name_header, id_header, "Registration", "Ballots Cast",
                       *choice_names)

    def write_totals_row(self, area_name, area_id, contest_results,
                         choice_ids, area_precinct_ids):
        """
        Write a row for an area participating in a contest.

        The area can be a precinct or district, for example "Pct 9503/9504"
        or"12TH CONGRESSIONAL DISTRICT".

        The columns in the row are--

        * Row headers
           1) area name
           2) area identifier
        * Totals
           3) registration
           4) ballots cast
           5) choice #1 vote total
           6) choice #2 vote total
           7) etc.

        Arguments:

          contest_results: a dict described by the following:
            contest_results[precinct_id] -> contest_precinct_results
            contest_precinct_results[choice_id] -> vote_total

        """
        # Add two for the "registration" and "ballots cast" columns.
        totals = (len(choice_ids) + 2) * [0]
        registered = self.results.registered
        voted = self.results.voted

        precinct_count = 0
        for precinct_id in area_precinct_ids:
            try:
                precinct_results = contest_results[precinct_id]
                precinct_count += 1
            except KeyError:
                # Then this precinct in the district did not
                # participate in the contest.
                continue

            totals[0] += registered[precinct_id]
            totals[1] += voted[precinct_id]

            for i, choice_id in enumerate(choice_ids, start=2):
                totals[i] += precinct_results[choice_id]

        assert precinct_count > 0
        self.write_row(area_name, area_id, *totals)

    def write_precinct_rows(self, contest_results, contest_choice_ids, precinct_ids):
        precincts = self.election_info.precincts
        for precinct_id in sorted(precinct_ids):
            # Convert precinct_id into an iterable with one element in order
            # to use write_totals_row().
            self.write_totals_row(precincts[precinct_id], precinct_id, contest_results,
                                  contest_choice_ids, (precinct_id, ))

    def write_area_rows(self, contest_results, choice_ids, contest_precinct_ids,
                        area_precincts, area_type_name, make_area_name, area_ids):
        for area_id in area_ids:
            area_name = make_area_name(area_id)
            area_label = "%s:%s" % (area_type_name, area_id)
            area_precinct_ids = area_precincts[area_id]
            assert type(area_precinct_ids) is set
            if area_precinct_ids.isdisjoint(contest_precinct_ids):
                # Then no precincts in the district overlapped the contest, so skip it.
                log("skipping area: %s" % area_name)
                continue
            try:
                self.write_totals_row(area_name, area_label, contest_results,
                                      choice_ids, area_precinct_ids)
            except:
                raise Exception("while processing area: %s" % area_name)

    def write_area_type_rows(self, contest_results, contest_precinct_ids,
                             choice_ids, area_type_name):
        """
        Write the rows for a contest for a particular area type.

        For example: the "Congressional" areas.

        """
        attr, format_name = AREA_INFO[area_type_name]
        area_type = getattr(self.election_info.area_index, attr)
        area_ids = sorted(area_type.keys())
        make_area_name = lambda area_id: format_name % area_id
        self.write_area_rows(contest_results, choice_ids, contest_precinct_ids,
                             area_type, area_type_name, make_area_name, area_ids)

    def write_contest_summary(self, contest_results, choice_ids, contest_precinct_ids):
        """
        Arguments:
          choice_ids: an iterable of choice IDs in the contest, in
            column display order.
          contest_precinct_ids: a set of precinct IDs corresponding to the
            precincts participating in the contest.

        """
        assert type(contest_precinct_ids) is set
        self.write_ln("District Grand Totals")
        self.write_totals_row_header("DistrictName", "DistrictLabel", choice_ids)
        for type_name in self.district_type_names:
            self.write_area_type_rows(contest_results, contest_precinct_ids, choice_ids, type_name)

        # Also write the neighborhood rows.
        nbhd_names = self.election_info.nbhd_names
        nbhd_pairs = nbhd_names.items()  # (nbhd_id, nbhd_name)
        # Alphabetize the pairs by the full name and not the label.
        nbhd_pairs = sorted(nbhd_pairs, key=lambda pair: pair[1])

        nbhd_precincts = self.election_info.area_index.neighborhoods
        make_nbhd_name = lambda nbhd_id: nbhd_names[nbhd_id]
        nbhd_ids = [pair[0] for pair in nbhd_pairs]

        self.write_area_rows(contest_results, choice_ids, contest_precinct_ids,
                             nbhd_precincts, "Neighborhood", make_nbhd_name, nbhd_ids)

    def write_contest(self, precincts, contest_info, contest_results):
        """
        Arguments:
          precincts: the ElectionInfo.precincts dict.
          contest_info: a ContestInfo object.

        """
        contest_name = contest_info.name
        precinct_ids = contest_info.precinct_ids
        contest_choice_ids = sorted(contest_info.choice_ids)

        log("writing contest: %s (%d precincts)" % (contest_name, len(precinct_ids)))

        self.write_ln("%s - %s" % (contest_name, contest_info.area))

        self.write_totals_row_header("VotingPrecinctName", "VotingPrecinctID", contest_choice_ids)
        self.write_precinct_rows(contest_results, contest_choice_ids, precinct_ids)
        self.write_ln()

        self.write_contest_summary(contest_results, contest_choice_ids, precinct_ids)

    def write(self):
        """Write the election results to the given file."""
        info = self.election_info
        results = self.results

        info_contests = info.contests
        precincts = info.precincts
        results_contests = results.contests

        now = datetime.now()
        self.write_ln(info.name)
        self.write_ln()
        # This looks like the following, for example:
        #   Report generated on: Friday, September 12, 2014 at 09:06:26 PM
        self.write_ln("Report generated on: %s %d, %s" %
                      (now.strftime("%A, %B"),
                       now.day,  # strftime lacks an option not to zero-pad the month.
                       now.strftime("%Y at %I:%M:%S %p")))
        self.write_ln()
        self.write_ln()
        for contest_id in sorted(info_contests.keys()):
            contest_info = info_contests[contest_id]
            contest_results = results_contests[contest_id]
            try:
                self.write_contest(precincts, contest_info, contest_results)
            except:
                raise Exception("while processing contest: %s" % contest_info.name)
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
