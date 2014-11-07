
import logging
import random
import re
import sys

from pywineds.resultswriting import ExcelWriter, TSVWriter
from pywineds import utils
from pywineds.utils import time_it, REPORTING_INDICES


FILE_ENCODING = "utf-8"

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


log = logging.getLogger("wineds")


def configure_log():
    level = logging.DEBUG
    fmt = "%(name)s: [%(levelname)s] %(message)s"
    logging.basicConfig(format=fmt, level=level)
    log.info("logging configured: level=%s" % logging.getLevelName(level))


def make_nbhd_names():
    """
    Return a dict mapping neighborhood labels to human-friendly names.

    """
    data = {}
    for s in NEIGHBORHOODS.strip().splitlines():
        label, name = s.split(":")
        data[label] = name
    return data


def exit_with_error(msg):
    log.info(msg)
    exit(1)


def parse_data_chunk(chunk):
    """Parse the 16+ character string beginning each line."""
    # 0AAACCCPPPPTTTTT[PTY]
    #
    # AAA   = contest_id
    # CCC   = choice_id
    # PPPP  = precinct_id
    # TTTTT = choice_total
    contest_id = int(chunk[1:4])
    choice_id = int(chunk[4:7])
    precinct_id = int(chunk[7:11])
    vote_total = -1 if chunk[11:16] == "000-1" else int(chunk[11:16])
    party = chunk[16:]
    return choice_id, contest_id, precinct_id, vote_total, party


# We do not currently need this function for anything.
def split_line(line):
    """Return a list of field values in the line."""
    return SPLITTER.split(line.strip())


def split_line_fixed(line):
    """
    Split a line from a WinEDS Reporting Tool output file into parts.

    The Reporting Tool outputs lines with fixed-width columns.  This function
    is necessary because not all columns have space between them.
    For example, "13TH CONGRESSIONAL DISTRITC-Election Day Reporting"
    divides before "TC-Election".

    A sample line:

        0010073990000000PF        US Representative, District 13                          \
        LAWERENCE N. ALLEN                    Pct 9900 MB                   \
        13TH CONGRESSIONAL DISTRITC-Election Day Reporting

    """
    # data_field, contest_name, choice_name, precinct_name, district_name, [reporting_type]
    data_field = line[:26].strip()
    contest_name = line[26:82].strip()
    choice_name = line[82:120].strip()
    precinct_name = line[120:150].strip()
    district_name = line[150:175].strip()
    reporting_type = line[175:].strip()
    return data_field, contest_name, choice_name, precinct_name, district_name, reporting_type


class ContestInfo(object):

    """
    Encapsulates metadata about a contest (but not results).

    """

    def __init__(self, id_, name, district_name):
        self.choice_ids = set()
        self.id = id_
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
        # A dict of integer precinct ID to precinct name.
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


class ElectionMeta(object):

    """
    Encapsulates election metadata (but not results).

    Attributes:

      choices: a dict of integer choice ID to a 2-tuple of
        (contest_id, choice_name).
      contests: a dict of integer contest_id to ContestInfo object.
      precincts: a dict of integer precinct ID to precinct name.

    """

    def __init__(self):
        # The following get set to integers if the WinEDS file contains
        # undervotes and overvotes.
        self.overvote_id = None
        self.undervote_id = None

        self.has_reporting_type = None

        self.choices = {}
        self.contests = {}
        self.precincts = {}

    def __repr__(self):
        return ("<ElectionMeta object: %d contests, %d choices, %d precincts>" %
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
        # When set, this should be an iterable of keys that will be used
        # within the "contests" and "voted" dicts to subdivide the vote totals.
        self.reporting_indices = None

        self.contests = {}
        self.registered = {}
        self.voted = {}


class ElectionInfo(object):

    def __init__(self, areas_info, meta, name, results):
        self.areas_info = areas_info
        self.meta = meta
        self.results = results
        self.name = name


def init_results(info, results):
    """
    Initialize the results object by modifying it in place.

    Arguments:
      info: an ElectionMeta object.
      results: an ElectionResults object.

    """
    contests = results.contests
    registered = results.registered
    voted = results.voted

    reporting_indices = (utils.REPORTING_INDICES_COMPLETE if info.has_reporting_type else
                         utils.REPORTING_INDICES_SIMPLE)
    results.reporting_indices = reporting_indices

    for contest_id, contest_info in info.contests.items():
        contest_results = {}
        contests[contest_id] = contest_results
        for precinct_id in contest_info.precinct_ids:
            # cp_results stands for contest_precinct_results
            # It is a dict of reporting-type index to: dict of
            # choice_id to vote total.
            cp_results = {k: dict() for k in reporting_indices}
            contest_results[precinct_id] = cp_results

    # Initialize the election-wide result attributes.
    for precinct_id in info.precincts.keys():
        # This is a dict of reporting-type index to ballots cast.
        voted[precinct_id] = {}

    return results


class Parser(object):

    line_no = 0
    line = None

    def log_line(self, msg):
        return '%s:\n>>> [L%d]:"%s"' % (msg, self.line_no, self.line.strip())

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
        log.info("parsed: %d lines" % line_no)

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
            log.info("parsing: %r" % self.name)
            try:
                with f:
                    lines = self.iter_lines(f)
                    self.parse_lines(lines)
            except:
                raise Exception("error while parsing line %d: %r" %
                                (self.line_no, self.line))
        return self.get_parse_return_value()

    def parse_path(self, path):
        log.info("opening: %s" % path)
        return self.parse_file(open(path, "r", encoding=FILE_ENCODING))


def parse_precinct_file(path):
    parser = PrecinctIndexParser()
    areas_info = parser.parse_path(path)
    log.info("parsed: %d precincts" % len(areas_info.city))
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
            text = self.log_line("precinct_id %d occurred again in line" % precinct_id)
            log.warning(text)
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


class ElectionMetaParser(Parser):

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
          info: an ElectionMeta object.

        """
        self.election_info = info
        # The following values are for convenience.
        self.contests = info.contests
        self.choices = info.choices
        self.precincts = info.precincts

    def make_choice(self, contest_id, choice_name):
        """Create the "choice" object for a given choice name, etc."""
        if choice_name in ('Under Vote', 'Over Vote'):
            contest_id = None
        return contest_id, choice_name

    def save_choice(self, choice_id, contest_id, choice_name):
        choice = self.make_choice(contest_id, choice_name)
        if choice[0] is None:
            if choice_name == "Under Vote":
                self.election_info.undervote_id = choice_id
            elif choice_name == "Over Vote":
                self.election_info.overvote_id = choice_id
            else:
                raise AssertionError("unexpected choice name for contest id None: %r" % choice_name)
            log.info("setting id=%r for: %r" % (choice_id, choice_name))
        self.choices[choice_id] = choice

    def parse_first_line(self, line):
        char_count = len(line.rstrip('\r\n'))
        try:
            assert char_count in (175, 205)
        except AssertionError:
            raise Exception("unexpected number of characters in first line: %d" % char_count)
        has_reporting_type = (char_count == 205)
        log.info("detected file format: has_reporting_type=%r" % has_reporting_type)
        self.election_info.has_reporting_type = has_reporting_type
        super().parse_first_line(line)

    def parse_line(self, line):
        """
        This function parses a single line, validates our assumptions
        about the file format, and then stores any new election metadata
        in the ElectionMeta object associated with the current
        parser instance.

        This function populates election_info.choices but does not
        populate contest.choice_ids for the objects in election_info.contests.
        We populate contest.choice_ids from election_info.choices
        afterwards.

        """
        fields = split_line_fixed(line)
        data, contest_name, choice_name, precinct_name, district_name, reporting_type = fields

        # Validate our assumptions about the initial data chunk.
        #
        # If the party is present in the "data" string, then the length
        # will be longer than 16.
        assert len(data) >= 16
        assert data[0] == '0'
        choice_id, contest_id, precinct_id, vote_total, party = parse_data_chunk(data)
        # We don't need to know the vote_total here.
        del vote_total, party

        # Store the precinct_id if it is new, otherwise check that it
        # matches the precinct name stored before.
        precincts = self.precincts
        try:
            old_precinct_name = precincts[precinct_id]
            assert precinct_name == old_precinct_name
        except KeyError:
            precincts[precinct_id] = precinct_name

        if not district_name:
            # Then this line must be one of the summary lines that lack a
            # final district_name column (since these rows have no contest
            # associated with them):
            #   0001001110100484  REGISTERED VOTERS - TOTAL  VOTERS  Pct 1101
            #   0002001110100141  BALLOTS CAST - TOTAL  BALLOTS CAST  Pct 1101
            #
            # In this case, we validate our assumptions about the summary
            # line and skip storing any contest or choices.
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
        except KeyError:
            logging.debug("adding contest_id %r: %s" % (contest_id, contest_name))
            contest = ContestInfo(id_=contest_id, name=contest_name,
                                  district_name=district_name)
            contests[contest_id] = contest
        else:
            try:
                assert contest_name == contest.name
            except AssertionError:
                raise Exception("contest_id=%r, contest_name=%r, contest.name=%s" %
                                (contest_id, contest_name, contest.name))
            try:
                assert district_name == contest.district_name
            except AssertionError:
                raise Exception("district_name=%r, contest.district_name=%s" %
                                (district_name, contest.district_name))

        # The following line is a no-op for contest choices after the
        # first in a precinct.
        contest.precinct_ids.add(precinct_id)

        try:
            prior_choice = self.choices[choice_id]
        except KeyError:
            logging.debug("adding choice_id %r: %s" % (choice_id, choice_name))
            self.save_choice(choice_id, contest_id, choice_name)
        else:
            new_choice = self.make_choice(contest_id, choice_name)
            try:
                assert new_choice == prior_choice
            except AssertionError:
                raise Exception("choice id %d (name=%r) for contest id %d already assigned to: "
                                "contest_id=%r, choice_name=%r" %
                                (choice_id, choice_name, contest_id, prior_choice[0], prior_choice[1]))


class ResultsParser(Parser):

    """
    When parsing, this class does not validate the file in the same way
    that the ElectionMetaParser does.

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

    def add_vote_total(self, totals, key, vote_total):
        """
        Arguments:
          totals: a dict mapping keys to integer vote totals.

        """
        try:
            assert isinstance(totals, dict)
        except AssertionError:
            raise Exception("totals has unexpected type: %r" % totals)
        try:
            totals[key]
        except KeyError:
            totals[key] = vote_total
        else:
            raise Exception("total for key=%d was already stored" % (key, ))

    def parse_line(self, line):
        fields = split_line_fixed(line)
        reporting_type = fields[-1]
        r_index = REPORTING_INDICES[reporting_type]

        choice_id, contest_id, precinct_id, vote_total, party = parse_data_chunk(fields[0])
        # We do not use party yet.
        del party
        if vote_total < 0:
            text = self.log_line("negative ballot total %d: choice_id=%d, "
                                 "contest_id=%d, precinct_id=%d" %
                                 (vote_total, choice_id, contest_id, precinct_id))
            log.warning(text)
        if contest_id == 1:
            totals = self.registered
            totals_key = precinct_id
        elif contest_id == 2:
            totals = self.voted[precinct_id]
            totals_key = r_index
        else:
            # Otherwise, we have a normal contest with candidates.
            totals = self.contests[contest_id][precinct_id][r_index]
            totals_key = choice_id

        self.add_vote_total(totals, totals_key, vote_total)


def parse_export_file(path):
    """
    Parse a WinEDS export file, and return an ElectionMeta object.

    """
    election_info = ElectionMeta()
    parser = ElectionMetaParser(election_info)
    parser.parse_path(path)

    choices = election_info.choices
    contest_map = election_info.contests

    # Add the available choices to each contest.
    for choice_id, (contest_id, choice_name) in choices.items():
        if contest_id is None:
            # Then the choice is an undervote or overvote and applies
            # to all contests.
            contests = contest_map.values()
        else:
            contests = (contest_map[contest_id], )

        for contest in contests:
            contest.choice_ids.add(choice_id)

    return election_info


def parse_export_file_with_check(areas_info, wineds_path):
    election_info = parse_export_file(wineds_path)

    # Check that the precincts in the precinct index file match the
    # precincts in the results file.
    for i, (precinct_id, wineds_precinct_id) in enumerate(zip(sorted(areas_info.city),
                                     sorted(election_info.precincts.keys())), start=1):
        try:
            assert precinct_id == wineds_precinct_id
        except AssertionError:
            if precinct_id < wineds_precinct_id:
                msg = "WinEDS file does not contain precinct id %d" % precinct_id
            else:
                msg = "WinEDS file contains unknown precinct id %d" % precinct_id
            msg += ": %s" % wineds_path
            raise Exception(msg)

    return election_info


def digest_input_files(precinct_index_path, wineds_path):
    """
    Read the input files and return a 3-tuple of objects of the following
    classes: ElectionMeta, AreasInfo, ElectionResults.

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
    election_info = parse_export_file_with_check(areas_info, wineds_path)

    # Log the contests parsed.
    contests = election_info.contests
    log.info("parsed %d contests:" % len(contests))
    for contest_id in sorted(contests.keys()):
        contest = contests[contest_id]
        log.info(" %3d: %s - %s (%d choices)" %
                 (contest_id, contest.name, contest.district_name, len(contest.choice_ids)))

    # Construct the results object.
    results = ElectionResults()
    init_results(election_info, results)

    # Pass #2
    parser = ResultsParser(results)
    parser.parse_path(wineds_path)

    return election_info, areas_info, results


def convert(election_name, precincts_path, export_path, output_base, now=None):
    election_meta, areas_info, results = digest_input_files(precincts_path, export_path)
    election_info = ElectionInfo(areas_info, election_meta, election_name, results)

    tsv_path = "%s.tsv" % output_base
    writer = TSVWriter(path=tsv_path, now=now)
    writer.write(election_info)

    excel_path = "%s.xlsx" % output_base
    writer = ExcelWriter(path=excel_path, now=now)
    writer.write(election_info)

    return tsv_path, excel_path

def inner_main(docstr, argv):
    try:
        # TODO: use argparse.
        election_name, precincts_path, export_path, output_path = argv[1:]
    except ValueError:
        err = "ERROR: incorrect number of arguments"
        exit_with_error("\n".join([err, docstr, err]))

    convert(election_name, precincts_path, export_path, output_path)


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
        log.info("wrote: %d lines" % self.write_line_count)


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
        data = split_line_fixed(line)[0]
        choice_id, contest_id, precinct_id, vote_total, party = parse_data_chunk(data)
        if vote_total < 0:
            log.warning("negative vote total %r: contest=%r, precinct=%r" %
                        (vote_total, contest_id, precinct_id))
        return ((precinct_id in self.precinct_ids) and
                (contest_id in self.contest_ids))


def make_test_precincts(args):
    """
    Create a small precinct file for end-to-end testing purposes.

    """
    log.info("making test precinct file")
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

    log.info("randomly chose: %d precincts" % len(precincts))

    parser = PrecinctFilterParser(precincts, output_file=sys.stdout)
    parser.parse_path(precincts_path)


def make_test_export(args):
    """
    Create a small WinEDS output file for end-to-end testing purposes.

    The test output file is written to stdout.

    """
    log.info("making test export file")
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


def main(docstr, argv):
    configure_log()
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

    with time_it("full program"):
        inner_main(docstr, argv)
