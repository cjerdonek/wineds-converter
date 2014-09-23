#!/usr/bin/env python
#
# **THIS SCRIPT IS WRITTEN FOR PYTHON 3.**
#

"""
Usage: python3 parse.py ELECTION_NAME PCT_INDEX_PATH RESULTS_PATH > out.tsv

Parses the given files and writes a new output file to stdout.

The new output file is tab-delimited (.tsv).  Tabs are used since some
fields contain commas (e.g. "US Representative, District 12").

Arguments:

  ELECTION_NAME: the name of the election for display purposes.
    This appears in the first line of the output file.
    An example value is "San Francisco June 3, 2014 Election".

  PCT_INDEX_PATH: path to a CSV file mapping precincts to their
    different districts and neighborhoods.

  RESULTS_PATH: path to a WinEDS Reporting Tool output file that contains
    vote totals for each precinct in each contest.

In the above, relative paths will be interpreted as relative to the
current working directory.
"""

from contextlib import contextmanager
from datetime import datetime
import random
import re
import sys
import timeit

WRITER_DELIMITER = "\t"
GRAND_TOTALS_HEADER = "Grand Totals"

# We split on strings of whitespace having 2 or more characters.  This is
# necessary since field values can contain spaces (e.g. candidate names).
SPLITTER = re.compile(r'\s{2,}')

# This string contains a mapping from neighborhood labels in the
# precinct-to-neighborhood file to the more human-friendly names that
# appear in the Statement of Vote.
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


# TODO: use Python's logging module.
def log(s=None):
    """Write to stderr."""
    if s is None:
        s = ""
    print(s, file=sys.stderr)


@contextmanager
def time_it(task_desc):
    """
    A context manager for timing chunks of code and logging it.

    Arguments:
      task_desc: task description for logging purposes

    """
    start_time = timeit.default_timer()
    yield
    elapsed = timeit.default_timer() - start_time
    log("elapsed (%s): %.4f seconds" % (task_desc, elapsed))


def exit_with_error(msg):
    log(msg)
    exit(1)


class ContestInfo(object):

    """
    Encapsulates metadata about a contest (but not results).

    """

    # TODO: include ID?
    def __init__(self, name, district_name):
        self.choice_ids = set()
        self.precinct_ids = set()
        self.name = name
        self.district_name = district_name

    def __repr__(self):
        return ("<ContestInfo object: name=%r, district_name=%r, %d precincts, %d choices)" %
                (self.name, self.district_name, len(self.precinct_ids), len(self.choice_ids)))


class AreasInfo(object):

    """
    Encapsulates information about each area and district.

    Each attribute corresponds to an "area type".  With the exception
    of the city attribute, each attribute is a dict that maps an integer
    area ID (or string in the case of neighborhoods) to a set of integer
    precinct IDs.  Each key in the dict represents an "area" or district.

    The city attribute is a simple set of integer precinct IDs (because
    there is only one area corresponding to the "city" area type).

    Other Attributes:

      nbhd_names: a dict mapping neighborhood string label to string name.
        For example, "BAYVW/HTRSPT" maps to "BAYVIEW/HUNTERS POINT".

    """

    # A dictionary containing information about the types of areas whose
    # name can be generated from a format string and a district number.
    # This dictionary does not include the "city" and "neighborhood"
    # area types.
    DISTRICT_TYPE_INFO = {
        'Assembly': ('assembly', '%sTH ASSEMBLY DISTRICT'),
        'BART': ('bart', 'BART DISTRICT %s'),
        'Congressional': ('congress', '%sTH CONGRESSIONAL DISTRICT'),
        'Senatorial': ('senate', '%sTH SENATORIAL DISTRICT'),
        'Supervisorial': ('supervisor', 'SUPERVISORIAL DISTRICT %s')
    }

    nbhd_names = make_nbhd_names()

    def __init__(self):
        # A dictionary of precinct_id to precinct_name.
        self.precincts = {}

        self.assembly = {}
        self.bart = {}
        # TODO: rename to all_precincts or precinct_ids?
        # TODO: or better yet, remove this since we have self.precincts?
        self.city = set()  # all precinct IDs.
        self.congress = {}
        self.neighborhoods = {}
        self.senate = {}
        self.supervisor = {}

    def get_area_type(self, district_type_name):
        area_attr = self.DISTRICT_TYPE_INFO[district_type_name][0]
        return getattr(self, area_attr)

    def get_area_name_function(self, district_type_name):
        format_str = self.DISTRICT_TYPE_INFO[district_type_name][1]
        return lambda area_id: format_str % area_id


# TODO: rename to ReportInfo?
class ElectionInfo(object):

    """
    Encapsulates election metadata (but not results).

    Attributes:

      choices: a dict of integer choice ID to a 2-tuple of
        (contest_id, choice_name).
      contests: a dict of integer contest_id to ContestInfo object.
      precincts: a dict of integer precinct ID to precinct name.

    """

    def __init__(self):
        self.choices = {}
        self.contests = {}
        self.precincts = {}

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


class Parser(object):

    line_no = 0
    line = None

    def iter_lines(self, f):
        """
        Return an iterator over the lines of an input file.

        Each iteration sets self.line and self.line_no but yields nothing.

        """
        for line_no, line in enumerate(iter(f), start=1):
            self.line = line
            self.line_no = line_no
            # This yields no values because we set the information
            # we need as instance attributes instead.  This is more
            # convenient for things like our Parser exception handler.
            yield
        log("parsed: %d lines" % line_no)

    def get_parse_return_value(self):
        return None

    def parse_first_line(self, line):
        self.parse_line(line)

    def parse_line(self, line):
        raise NotImplementedError()

    def parse_lines(self, lines):
        next(lines)
        self.parse_first_line(self.line)
        for x in lines:
            self.parse_line(self.line)

    def parse_file(self, f):
        with time_it("parsing %r" % self.name):
            log("parsing...\n  %r" % self.name)
            try:
                with f:
                    lines = self.iter_lines(f)
                    self.parse_lines(lines)
            except:
                raise Exception("error while parsing line %d: %r" %
                                (self.line_no, self.line))
        return self.get_parse_return_value()

    def parse_path(self, path):
        log("opening...\n  %s" % path)
        return self.parse_file(open(path, "r", encoding="utf-8"))


def parse_precinct_file(path):
    parser = PrecinctIndexParser()
    areas_info = parser.parse_path(path)
    log("parsed: %d precincts" % len(areas_info.city))
    return areas_info


def parse_precinct_index_line(line):
    values = line.strip().split(",")
    precinct_id = int(values[0])
    return precinct_id, values


class PrecinctIndexParser(Parser):

    """
    Parses a CSV precinct-index file.

    """

    DISTRICT_HEADERS = ("Assembly", "BART", "Congressional", "Senatorial", "Supervisorial")

    name = "Precinct Index File"

    def __init__(self):
        self.areas_info = AreasInfo()

    def get_parse_return_value(self):
        return self.areas_info

    def parse_first_line(self, line):
        # Skip the header line.
        pass

    def add_precinct_to_area(self, area_type, area_id, precinct_id):
        try:
            precinct_ids = area_type[area_id]
        except KeyError:
            precinct_ids = set()
            area_type[area_id] = precinct_ids
        precinct_ids.add(precinct_id)

    def parse_line(self, line):
        # Here are the column headers of the file:
        #   VotingPrecinctID,VotingPrecinctName,MailBallotPrecinct,BalType,
        #   Assembly,BART,Congressional,Neighborhood,Senatorial,Supervisorial
        precinct_id, values = parse_precinct_index_line(line)
        precinct_name = values[1]
        if precinct_id in self.areas_info.precincts:
            log(("WARN: precinct_id %d occurred again in line:\n"
                 " [#%d]: %s") % (precinct_id, self.line_no, line.strip()))
            return

        self.areas_info.precincts[precinct_id] = precinct_name

        # Includes: Assembly,BART,Congressional,Neighborhood,Senatorial,Supervisorial
        values = values[4:]
        nbhd_label = values.pop(3)
        for district_type_name, area_id in zip(self.DISTRICT_HEADERS, values):
            area_type = self.areas_info.get_area_type(district_type_name)
            self.add_precinct_to_area(area_type, int(area_id), precinct_id)

        area_type = self.areas_info.neighborhoods
        self.add_precinct_to_area(area_type, nbhd_label, precinct_id)
        self.areas_info.city.add(precinct_id)


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


class ElectionInfoParser(Parser):

    """
    Parser for a TEXT report from the WinEDS Reporting Tool.

    This class is responsible for reading and building election metadata
    from the file but not election vote totals.

    When parsing, the parser also performs validation on the file to ensure
    that our assumptions about the file format and data are correct.

    """

    name = "Results File (pass #1, for election metadata)"

    def __init__(self, info):
        """
        Arguments:
          info: an ElectionInfo object.

        """
        self.contests = info.contests
        self.choices = info.choices
        self.precincts = info.precincts

    def parse_line(self, line):
        """
        This function parses a single line, validates our assumptions
        about the file format, and then stores any new election metadata
        in the ElectionInfo object associated with the current
        parser instance.

        This function populates election_info.choices but does not
        populate contest.choice_ids for the objects in election_info.contests.
        We populate contest.choice_ids from election_info.choices
        afterwards.

        """
        fields = split_line(line)
        try:
            data, contest_name, choice_name, precinct_name, district_name = fields
        except ValueError:
            # Then this line must be one of the summary lines that lack a
            # final district_name column (since these rows have no contest
            # associated with them):
            #   0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
            #   0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
            try:
                data, contest_name, choice_name, precinct_name = fields
            except ValueError:
                raise Exception("error unpacking fields: %r" % fields)
            district_name = None

        # Validate our assumptions about the initial data chunk.
        assert len(data) == 16
        assert data[0] == '0'
        choice_id, contest_id, precinct_id, vote_total = parse_data_chunk(data)

        # Store the precinct_id if it is new, otherwise check that it
        # matches the precinct name stored before.
        precincts = self.precincts
        try:
            old_precinct_name = precincts[precinct_id]
            assert precinct_name == old_precinct_name
        except KeyError:
            precincts[precinct_id] = precinct_name

        if district_name is None:
            # Then validate our assumptions about the summary line and
            # skip storing any contest or choices.
            assert choice_id == 1
            assert contest_id in (1, 2)
            if contest_id == 1:
                expected_contest_name = "REGISTERED VOTERS - TOTAL"
                expected_choice_name = "VOTERS"
            else:
                # Then contest_id is 2.
                expected_contest_name = "BALLOTS CAST - TOTAL"
                expected_choice_name = "BALLOTS CAST"
            assert contest_name == expected_contest_name
            assert choice_name == expected_choice_name
            return
        # Otherwise, the line corresponds to a real contest.

        contests = self.contests
        try:
            contest = contests[contest_id]
            assert contest_name == contest.name
            assert district_name == contest.district_name
        except KeyError:
            contest = ContestInfo(name=contest_name, district_name=district_name)
            contests[contest_id] = contest

        choices = self.choices
        try:
            choice = choices[choice_id]
            try:
                assert choice == (contest_id, choice_name)
            except AssertionError:
                raise Exception("choice mismatch for choice ID %d: %r != %r" %
                                (choice_id, choice, (contest_id, choice_name)))
        except KeyError:
            choice = (contest_id, choice_name)
            choices[choice_id] = choice

        # The following line is a no-op for contest choices after the
        # first in a precinct.
        contest.precinct_ids.add(precinct_id)


class ResultsParser(Parser):

    """
    In addition to parsing the file, this class's parse() method also
    performs validation on the file to ensure that all of our assumptions
    about the file format and data are correct.
    """

    name = "Results File (pass #2, for vote totals)"

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
                # Then contest_id equals 2.
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


def parse_export_file(path):
    """
    Parse a WinEDS export file, and return an ElectionInfo object.

    """
    election_info = ElectionInfo()
    parser = ElectionInfoParser(election_info)
    parser.parse_path(path)

    choices = election_info.choices
    contests = election_info.contests

    # Set the choice_ids attribute on each contest.
    for choice_id, (contest_id, choice_name) in choices.items():
        contest = contests[contest_id]
        contest.choice_ids.add(choice_id)

    return election_info


def digest_input_files(precinct_index_path, wineds_path):
    """
    Read the input files and return a 3-tuple of objects of the following
    classes: ElectionInfo, AreasInfo, ElectionResults.

    """
    areas_info = parse_precinct_file(precinct_index_path)

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
    election_info = parse_export_file(wineds_path)

    # TODO: move the following assertions into a parse_export_file_with_check()
    # funcation (with a better function name).
    # Check that the precincts in the precinct index file match the
    # precincts in the results file.
    for i, (p1, p2) in enumerate(zip(sorted(areas_info.city),
                                     sorted(election_info.precincts.keys())), start=1):
        try:
            assert p1 == p2
        except AssertionError:
            exit_with_error("precinct %d differs: %r != %r" % (i, p1, p2))

    # Log the contests parsed.
    contests = election_info.contests
    log("parsed %d contests:" % len(contests))
    for contest_id in sorted(contests.keys()):
        contest = contests[contest_id]
        log(" %3d: %s - %s (%d choices)" %
            (contest_id, contest.name, contest.district_name, len(contest.choice_ids)))

    # Construct the results object.
    results = ElectionResults()
    init_results(election_info, results)

    # Pass #2
    parser = ResultsParser(results)
    parser.parse_path(wineds_path)

    return election_info, areas_info, results


class Writer(object):

    def write_ln(self, s=""):
        print(s, file=self.file)


class ContestWriter(Writer):

    district_type_names = (
        'Congressional',
        'Senatorial',
        'Assembly',
        'BART',
        'Supervisorial'
    )

    def __init__(self, file, election_info, areas_info, results, contest_info, contest_results):
        """
        Arguments:

          contest_results: a value in the results.contests dictionary,
            where results is an ElectionResults object.  See the
            ElectionResults docstring for information on the structure
            of these values.

        """
        self.file = file
        self.areas_info = areas_info
        self.contest_info = contest_info
        self.contest_results = contest_results
        self.election_info = election_info
        self.results = results
        self.sorted_choice_ids = sorted(contest_info.choice_ids)

    @property
    def precinct_ids(self):
        """
        Return a set of IDs for the precincts participating in the contest.

        """
        return self.contest_info.precinct_ids

    def write_row(self, *values):
        self.write_ln(WRITER_DELIMITER.join([str(v) for v in values]))

    def write_totals_row_header(self, name_header, id_header):
        """
        Write the column header row for the totals rows.

        """
        choices = self.election_info.choices
        # Each choices value is a 2-tuple of (contest_id, choice_name).
        choice_names = (choices[choice_id][1] for choice_id in self.sorted_choice_ids)
        self.write_row(name_header, id_header, "Precincts", "Registration",
                       "Ballots Cast", "Turnout (%)", *choice_names)

    def write_totals_row(self, area_name, area_id, area_precinct_ids):
        """
        Write a row for a contest, for a participating district or area.

        For example, the area can be a precinct or district, like
        "Pct 9503/9504" or "12TH CONGRESSIONAL DISTRICT".

        The columns in the row are--

        * Row headers
           1) Area name
           2) Area identifier
        * Totals
           3) Number of precincts represented by row
           4) Registration
           5) Ballots cast
           6) Percent turnout
           7) choice #1 vote total
           8) choice #2 vote total
           9) etc.

        Arguments:
          area_precinct_ids: an iterable of precinct IDs in the given area.

        """
        # Add four extra columns for:
        # precinct count, registration, ballots cast, and percent turnout.
        extra_columns = 4
        choice_ids = self.sorted_choice_ids
        totals = (extra_columns + len(choice_ids)) * [0]
        registered = self.results.registered
        voted = self.results.voted

        contest_results = self.contest_results
        for precinct_id in area_precinct_ids:
            try:
                precinct_results = contest_results[precinct_id]
            except KeyError:
                # Then this precinct in the district did not
                # participate in the contest.
                continue

            totals[0] += 1
            totals[1] += registered[precinct_id]
            totals[2] += voted[precinct_id]

            for i, choice_id in enumerate(choice_ids, start=extra_columns):
                totals[i] += precinct_results[choice_id]

        assert totals[0] > 0
        # Prevent division by zero.
        totals[3] = "0.00" if totals[1] == 0 else "{:.2%}".format(totals[2] / totals[1])[:-1]
        self.write_row(area_name, area_id, *totals)

    def write_grand_totals_row(self, header):
        """
        Write a row for the city-wide totals.

        """
        all_precinct_ids = self.areas_info.city
        # The area ID "City:0" is just a placeholder value so the column
        # value can have the same format as other rows in the summary.
        self.write_totals_row(header, "City:0", all_precinct_ids)

    def write_precinct_rows(self):
        precincts = self.election_info.precincts
        for precinct_id in sorted(self.precinct_ids):
            # Convert precinct_id into an iterable with one element in order
            # to use write_totals_row().
            self.write_totals_row(precincts[precinct_id], precinct_id, (precinct_id, ))
        self.write_grand_totals_row(GRAND_TOTALS_HEADER)

    def write_area_rows(self, area_type, area_type_name, make_area_name, area_ids):
        contest_precinct_ids = self.precinct_ids
        for area_id in area_ids:
            area_name = make_area_name(area_id)
            area_label = "%s:%s" % (area_type_name, area_id)
            area_precinct_ids = area_type[area_id]
            assert type(area_precinct_ids) is set
            if area_precinct_ids.isdisjoint(contest_precinct_ids):
                # Then no precincts in the district overlapped the contest, so skip it.
                log("   no precincts: %s" % (area_name, ))
                continue
            try:
                self.write_totals_row(area_name, area_label, area_precinct_ids)
            except:
                raise Exception("while processing area: %s" % area_name)

    def write_district_type_rows(self, district_type_name):
        """
        Write the rows for a contest for a particular area type.

        For example: the "Congressional" areas.

        """
        areas_info = self.areas_info
        area_type = areas_info.get_area_type(district_type_name)
        make_area_name = areas_info.get_area_name_function(district_type_name)
        area_ids = sorted(area_type.keys())
        self.write_area_rows(area_type, district_type_name, make_area_name, area_ids)

    def write_contest_summary(self):
        self.write_ln("District Grand Totals")
        self.write_totals_row_header("DistrictName", "DistrictLabel")
        for district_type_name in self.district_type_names:
            self.write_district_type_rows(district_type_name)

        # This precedes the neighborhood totals in the PDF Statement of Vote.
        self.write_grand_totals_row("CITY/COUNTY OF SAN FRANCISCO")

        # Also write the neighborhood rows.
        nbhd_names = self.areas_info.nbhd_names
        nbhd_pairs = nbhd_names.items()  # (nbhd_id, nbhd_name)
        # Alphabetize the pairs by the full name and not the label.
        nbhd_pairs = sorted(nbhd_pairs, key=lambda pair: pair[1])

        neighborhoods_area = self.areas_info.neighborhoods
        make_nbhd_name = lambda nbhd_id: nbhd_names[nbhd_id]
        nbhd_ids = [pair[0] for pair in nbhd_pairs]

        self.write_area_rows(neighborhoods_area, "Neighborhood", make_nbhd_name, nbhd_ids)
        self.write_grand_totals_row(GRAND_TOTALS_HEADER)

    def write(self):
        contest_name = self.contest_info.name
        log("writing contest: %s (%d precincts)" %
            (contest_name, len(self.precinct_ids)))
        # TODO: move this assertion earlier in the script?
        assert type(self.precinct_ids) is set
        # Begin each contest with a distinctive string.  We use 3 stars.
        # Doing this makes it easier for people to both (1) search through
        # the CSV (e.g. by using COMMAND+F or CTRL+F), and (2) parse the
        # file with a script (since it gives people an easy way to find
        # where the lines for each contest start).
        self.write_ln("*** %s - %s" % (contest_name, self.contest_info.district_name))
        self.write_totals_row_header("VotingPrecinctName", "VotingPrecinctID")
        self.write_precinct_rows()
        self.write_ln()
        self.write_contest_summary()


class ResultsWriter(Writer):

    def __init__(self, file, election_name):
        self.election_name = election_name
        self.file = file

    def write_inner(self, election_info, areas_info, results):
        info_contests = election_info.contests
        results_contests = results.contests

        now = datetime.now()
        self.write_ln(self.election_name)
        self.write_ln()
        # This looks like the following, for example:
        #   Report generated on: Friday, September 12, 2014 at 09:06:26 PM
        self.write_ln("Report generated on: %s %d, %s" %
                      (now.strftime("%A, %B"),
                       now.day,  # strftime lacks an option not to zero-pad the month.
                       now.strftime("%Y at %I:%M:%S %p")))

        for contest_id in sorted(info_contests.keys()):
            self.write_ln()
            self.write_ln()
            contest_info = info_contests[contest_id]
            contest_results = results_contests[contest_id]
            try:
                contest_writer = ContestWriter(self.file, election_info, areas_info,
                                               results, contest_info, contest_results)
                contest_writer.write()
            except:
                raise Exception("while processing contest: %s" % contest_info.name)

    def write(self, election_info, areas_info, results):
        """Write the election results to the given file."""
        with time_it("writing output file"):
            self.write_inner(election_info, areas_info, results)

def inner_main(argv):
    try:
        # TODO: use argparse.
        election_name, precinct_index_path, results_path = argv[1:]
    except ValueError:
        err = "ERROR: incorrect number of arguments"
        exit_with_error("\n".join([err, __doc__, err]))

    # TODO: consider combining these three things into a master object.
    election_info, areas_info, results = digest_input_files(precinct_index_path, results_path)

    # TODO: look into how to control the encoding when writing to stdout.
    writer = ResultsWriter(file=sys.stdout, election_name=election_name)
    writer.write(election_info, areas_info, results)


class FilterParser(Parser):

    """
    A class for copying a file while filtering out lines.

    The should_write() method determines the filtering condition.

    """

    def __init__(self, output_file):
        self.output_file = output_file
        self.write_line_count = 0

    def should_write(self, line):
        raise NotImplementedError()

    def write(self, line):
        self.output_file.write(line)
        self.write_line_count += 1

    def parse_line(self, line):
        if self.should_write(line):
            self.write(line)

    def parse_lines(self, lines):
        # TODO: use the Hollywood principle instead of calling the base class method.
        super().parse_lines(lines)
        log("wrote: %d lines" % self.write_line_count)


class PrecinctFilterParser(FilterParser):

    name = "Precinct Index File (filtering)"

    def __init__(self, precinct_ids, output_file):
        super().__init__(output_file)
        self.precinct_ids = precinct_ids

    def parse_first_line(self, line):
        # Copy the header line.
        self.write(line)

    def should_write(self, line):
        precinct_id, values = parse_precinct_index_line(line)
        return precinct_id in self.precinct_ids


class ExportFilterParser(FilterParser):

    name = "Results Export File (filtering)"

    def __init__(self, precinct_ids, contest_ids, output_file):
        super().__init__(output_file)
        self.contest_ids = contest_ids
        self.precinct_ids = precinct_ids

    def should_write(self, line):
        data = split_line(line)[0]
        choice_id, contest_id, precinct_id, vote_total = parse_data_chunk(data)
        return ((precinct_id in self.precinct_ids) and
                (contest_id in self.contest_ids))


def make_test_precincts(args):
    """
    Create a small precinct file for end-to-end testing purposes.

    """
    log("making test precinct file")
    assert not args
    precincts_path = "data/election-2014-06-03/precincts_20140321.csv"

    areas_info = parse_precinct_file(precincts_path)
    all_precincts = areas_info.city

    # Include the two "duplicated" precincts so that we can test
    # this edge case.
    precincts = set((7509, 7527))
    def choose_from_area_type(area_type, precincts):
        for area_precincts in area_type.values():
            precinct, = random.sample(area_precincts, 1)
            precincts.add(precinct)

    # Choose at least one precinct from each district and neighborhood.
    for type_name in areas_info.DISTRICT_TYPE_INFO:
        area_type = areas_info.get_area_type(type_name)
        choose_from_area_type(area_type, precincts)
    choose_from_area_type(areas_info.neighborhoods, precincts)

    log("randomly chose: %d precincts" % len(precincts))

    parser = PrecinctFilterParser(precincts, output_file=sys.stdout)
    parser.parse_path(precincts_path)


def make_test_export(args):
    """
    Create a small data export file for end-to-end testing purposes.

    """
    log("making test export file")
    precincts_path, export_path = args
    areas_info = parse_precinct_file(precincts_path)

    precinct_ids = set(areas_info.precincts.keys())
    # We include the following contests because they provide a mixture
    # of full-city and partial-city contests:
    #
    #   1: Registered voters
    #   2: Ballots cast
    # 120: State Treasurer - CALIFORNIA (3 choices)
    # 145: US Representative, District 14 - 14TH CONGRESSIONAL DISTRI (2 choices)
    # 150: State Assembly, District 17 - 17TH ASSEMBLY DISTRICT (3 choices)
    # 180: Local Measure A - CITY/COUNTY OF SAN FRANCI (2 choices)
    #
    contest_ids = set((1, 2, 120, 145, 150, 180))

    parser = ExportFilterParser(precinct_ids=precinct_ids, contest_ids=contest_ids,
                                output_file=sys.stdout)
    parser.parse_path(export_path)


def main(argv):
    # Check length of argv to avoid the following when accessing argv[1]:
    # IndexError: list index out of range
    # TODO: use argparse.
    if len(argv) > 1:
        arg = argv[1]
        if arg == "make_test_precincts":
            make_test_precincts(argv[2:])
            return
        elif arg == "make_test_export":
            make_test_export(argv[2:])
            return

    # Skip a line for readability.
    log()
    with time_it("full program"):
        inner_main(argv)

if __name__ == "__main__":
    main(sys.argv)
