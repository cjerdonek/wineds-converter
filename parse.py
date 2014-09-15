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

import codecs
from contextlib import contextmanager
from datetime import datetime
import re
import sys
import timeit

WRITER_DELIMITER = "\t"
GRAND_TOTALS_HEADER = "Grand Totals"

# We split on strings of whitespace having 2 or more characters.  This is
# necessary since field values can contain spaces (e.g. candidate names).
SPLITTER = re.compile(r'\s{2,}')

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
def time_it():
    start_time = timeit.default_timer()
    yield
    elapsed = timeit.default_timer() - start_time
    log("elapsed: %.4f seconds" % elapsed)


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


class AreasInfo(object):

    """
    Encapsulates information about each area and district.

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

    def __init__(self, name, areas_info):
        """
        Arguments:
          areas_info: an AreasInfo object.

        """
        self.choices = {}
        self.contests = {}
        self.areas_info = areas_info
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


class Parser(object):

    line_no = 0
    line = None

    def iter_lines(self, f):
        """
        Return an iterator over the lines of an input file.

        Each iteration yields a 2-tuple: (line_no, line).

        """
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

    def parse_body(self, f):
        for x in self.iter_lines(f):
            self.parse_line(self.line)

    def parse_file(self, f):
        try:
            with f:
                self.parse_body(f)
        except:
            raise Exception("error while parsing line %d: %r" %
                            (self.line_no, self.line))

    def parse_path(self, path):
        log("parsing: %s" % path)
        self.parse_file(codecs.open(path, "r", encoding="utf-8"))


class PrecinctIndexParser(Parser):

    """
    Parses a CSV precinct-index file.

    """

    DISTRICT_HEADERS = ("Assembly", "BART", "Congressional", "Senatorial", "Supervisorial")

    def __init__(self, areas_info):
        """
        Arguments:
          areas_info: an AreasInfo object.

        """
        self.areas_info = areas_info

    def add_precinct_to_area(self, area_attr, precinct_id, area_id):
        area_type = getattr(self.areas_info, area_attr)
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
        values = line.strip().split(",")
        precinct_id = int(values[0])
        # Includes: Assembly,BART,Congressional,Neighborhood,Senatorial,Supervisorial
        values = values[4:]
        nbhd_label = values.pop(3)
        for district_type_name, area_id in zip(self.DISTRICT_HEADERS, values):
            area_attr = DISTRICT_TYPE_INFO[district_type_name][0]
            self.add_precinct_to_area(area_attr, precinct_id, int(area_id))

        self.add_precinct_to_area('neighborhoods', precinct_id, nbhd_label)
        self.areas_info.city.add(precinct_id)

    def parse_body(self, f):
        lines = self.iter_lines(f)
        next(lines)  # Skip the header line.
        for x in lines:
            self.parse_line(self.line)


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
        """
        This function does not populate contest.choice_ids for the objects
        in contests.

        """
        fields = split_line(line)
        try:
            data, new_contest, new_choice, precinct, contest_area = fields
        except ValueError:
            # This exception can occur for summary lines like the following
            # that lack a final "contest_area" column (since there is
            # no contest for these rows):
            #   0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
            #   0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
            fields.append(None)
            try:
                data, new_contest, new_choice, precinct, contest_area = fields
            except ValueError:
                raise Exception("error unpacking fields: %r" % fields)

        assert len(data) == 16
        assert data[0] == '0'
        choice_id, contest_id, precinct_id, vote_total = parse_data_chunk(data)

        contests, choices, precincts = self.contests, self.choices, self.precincts

        try:
            old_precinct = precincts[precinct_id]
            assert old_precinct == precinct
        except KeyError:
            precincts[precinct_id] = precinct

        # The contests with the following names are special cases that need
        # to be treated differently:
        #   "REGISTERED VOTERS - TOTAL"
        #   "BALLOTS CAST - TOTAL"
        if contest_area is None:
            assert contest_id in (1, 2)
            # TODO: both have choice ID 1, so skip them and don't store them as choices.
            return

        try:
            contest = contests[contest_id]
            assert new_contest == contest.name
            assert contest_area == contest.area
        except KeyError:
            contest = ContestInfo(name=new_contest, area=contest_area)
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


def make_election_info(path, name, areas_info):
    """
    Parse the file, and create an ElectionInfo object.

    """
    election_info = ElectionInfo(name, areas_info)
    parser = ElectionInfoParser(election_info)
    parser.parse_path(path)

    choices = election_info.choices
    contests = election_info.contests

    for choice_id, (contest_id, choice_name) in choices.items():
        contest = contests[contest_id]
        contest.choice_ids.add(choice_id)

    return election_info


def digest_input_files(name, precinct_index_path, wineds_path):
    """
    Read the input files and return a 2-tuple of an ElectionInfo
    object and an ElectionResults object.

    """
    areas_info = AreasInfo()
    parser = PrecinctIndexParser(areas_info)
    parser.parse_path(precinct_index_path)

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
    election_info = make_election_info(wineds_path, name, areas_info)

    # Check that the precincts in the precinct index file match the
    # precincts in the results file.
    for i, (p1, p2) in enumerate(zip(sorted(areas_info.city),
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
    parser.parse_path(wineds_path)

    return election_info, results


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

    def __init__(self, file, election_info, results, contest_info, contest_results):
        self.file = file
        self.contest_info = contest_info
        self.contest_results = contest_results
        self.election_info = election_info
        self.results = results
        self.sorted_choice_ids = sorted(contest_info.choice_ids)

    @property
    def contest_name(self):
        """
        Return a set of IDs for the precincts participating in the contest.

        """
        return self.contest_info.name

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

    def write_totals_row(self, contest_results, choice_ids,
                         area_name, area_id, area_precinct_ids):
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

          contest_results: a value in the results.contests dictionary,
            where results is an ElectionResults object.  See the
            ElectionResults docstring for information on the structure
            of these values.
          area_precinct_ids: an iterable of precinct IDs in the given area.

        """
        # Add four extra columns for:
        # precinct count, registration, ballots cast, and percent turnout.
        extra_columns = 4
        totals = (extra_columns + len(choice_ids)) * [0]
        registered = self.results.registered
        voted = self.results.voted

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
        totals[3] = "0.00" if totals[1] == 0 else "{:.2%}".format(totals[2] / totals[1])[:-1]
        self.write_row(area_name, area_id, *totals)

    def write_grand_totals_row(self, header):
        """
        Write a row for the city-wide totals.

        """
        all_precinct_ids = self.election_info.areas_info.city
        # The area ID "City:0" is just a placeholder value so the column
        # value can have the same format as other rows in the summary.
        self.write_totals_row(self.contest_results, self.sorted_choice_ids,
                              header, "City:0", all_precinct_ids)

    def write_precinct_rows(self):
        contest_results = self.contest_results
        contest_choice_ids = self.sorted_choice_ids
        precincts = self.election_info.precincts
        for precinct_id in sorted(self.precinct_ids):
            # Convert precinct_id into an iterable with one element in order
            # to use write_totals_row().
            self.write_totals_row(contest_results, contest_choice_ids,
                                  precincts[precinct_id], precinct_id, (precinct_id, ))
        self.write_grand_totals_row(GRAND_TOTALS_HEADER)

    def write_area_rows(self, contest_name, contest_results, choice_ids,
                        contest_precinct_ids, area_type, area_type_name,
                        make_area_name, area_ids):
        for area_id in area_ids:
            area_name = make_area_name(area_id)
            area_label = "%s:%s" % (area_type_name, area_id)
            area_precinct_ids = area_type[area_id]
            assert type(area_precinct_ids) is set
            if area_precinct_ids.isdisjoint(contest_precinct_ids):
                # Then no precincts in the district overlapped the contest, so skip it.
                log("skipping area in %s: %s" % (contest_name, area_name))
                continue
            try:
                self.write_totals_row(contest_results, choice_ids,
                                      area_name, area_label, area_precinct_ids)
            except:
                raise Exception("while processing area: %s" % area_name)

    def write_district_type_rows(self, contest_name, contest_results, contest_precinct_ids,
                                 choice_ids, district_type_name):
        """
        Write the rows for a contest for a particular area type.

        For example: the "Congressional" areas.

        """
        area_attr, format_name = DISTRICT_TYPE_INFO[district_type_name]
        area_type = getattr(self.election_info.areas_info, area_attr)
        area_ids = sorted(area_type.keys())
        make_area_name = lambda area_id: format_name % area_id
        self.write_area_rows(contest_name, contest_results, choice_ids,
                             contest_precinct_ids, area_type, district_type_name,
                             make_area_name, area_ids)

    def write_contest_summary(self):
        contest_name = self.contest_name
        contest_precinct_ids = self.precinct_ids
        contest_results = self.contest_results
        choice_ids = self.sorted_choice_ids
        assert type(contest_precinct_ids) is set
        self.write_ln("District Grand Totals")
        self.write_totals_row_header("DistrictName", "DistrictLabel")
        for district_type_name in self.district_type_names:
            self.write_district_type_rows(contest_name, contest_results,
                                          contest_precinct_ids, choice_ids, district_type_name)

        # This precedes the neighborhood totals in the PDF Statement of Vote.
        self.write_grand_totals_row("CITY/COUNTY OF SAN FRANCISCO")

        # Also write the neighborhood rows.
        nbhd_names = self.election_info.nbhd_names
        nbhd_pairs = nbhd_names.items()  # (nbhd_id, nbhd_name)
        # Alphabetize the pairs by the full name and not the label.
        nbhd_pairs = sorted(nbhd_pairs, key=lambda pair: pair[1])

        neighborhoods_area = self.election_info.areas_info.neighborhoods
        make_nbhd_name = lambda nbhd_id: nbhd_names[nbhd_id]
        nbhd_ids = [pair[0] for pair in nbhd_pairs]

        # TODO: cut down on the number of arguments passed by storing things
        # like the following as attributes: contest_name, contest_results,
        # choice_ids, and contest_precinct_ids.
        self.write_area_rows(contest_name, contest_results, choice_ids,
                             contest_precinct_ids, neighborhoods_area,
                             "Neighborhood", make_nbhd_name, nbhd_ids)
        self.write_grand_totals_row(GRAND_TOTALS_HEADER)

    def write(self):
        log("writing contest: %s (%d precincts)" % (self.contest_name, len(self.precinct_ids)))
        self.write_ln("%s - %s" % (self.contest_name, self.contest_info.area))
        self.write_totals_row_header("VotingPrecinctName", "VotingPrecinctID")
        self.write_precinct_rows()
        self.write_ln()
        self.write_contest_summary()


class ResultsWriter(Writer):

    def __init__(self, file):
        self.file = file

    def write(self, election_info, results):
        """Write the election results to the given file."""
        info_contests = election_info.contests
        results_contests = results.contests

        now = datetime.now()
        self.write_ln(election_info.name)
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
                contest_writer = ContestWriter(self.file, election_info, results, contest_info, contest_results)
                contest_writer.write()
            except:
                raise Exception("while processing contest: %s" % contest_info.name)
            self.write_ln()
            self.write_ln()


def inner_main(argv):
    try:
        # TODO: use argparse.
        name, precinct_index_path, results_path = argv[1:]
    except ValueError:
        err = "ERROR: incorrect number of arguments"
        exit_with_error("\n".join([err, __doc__, err]))

    election_info, results = digest_input_files(name, precinct_index_path, results_path)

    writer = ResultsWriter(file=sys.stdout)
    writer.write(election_info, results)


def main(argv):
    with time_it():
        inner_main(argv)


if __name__ == "__main__":
    main(sys.argv)
