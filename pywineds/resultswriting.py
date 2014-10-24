
"""
Supports writing results files.

"""

from contextlib import contextmanager
from datetime import datetime
import logging

try:
    import xlsxwriter
except ImportError:
    raise Exception("XlsxWriter does not seem to be installed. "
                    "Please follow the setup instructions.")

from pywineds import utils
from pywineds.utils import (time_it, REPORTING_INDICES, REPORTING_INDICES_SIMPLE,
                            REPORTING_INDICES_COMPLETE)


GRAND_TOTALS_HEADER = "Grand Totals"
WRITER_DELIMITER = "\t"

log = logging.getLogger(__name__)


class ContestWriter(object):

    district_type_names = (
        'Congressional',
        'Senatorial',
        'Assembly',
        'BART',
        'Supervisorial'
    )

    def __init__(self, info, contest_info, contest_results):
        """
        Arguments:

          contest_results: a value in the results.contests dictionary,
            where results is an ElectionResults object.  See the
            ElectionResults docstring for information on the structure
            of these values.

        """
        self.areas_info = info.areas_info
        self.contest_info = contest_info
        self.contest_results = contest_results
        self.election_info = info.meta
        self.results = info.results
        self.sorted_choice_ids = sorted(contest_info.choice_ids)

    @property
    def precinct_ids(self):
        """
        Return a set of IDs for the precincts participating in the contest.

        """
        return self.contest_info.precinct_ids

    @property
    def reporting_indices(self):
        return self.results.reporting_indices

    def extra_header_names(self):
        return ()

    def make_first_fields(self, area_name, area_label, reporting_indices):
        return (area_name, area_label)

    def write_totals_row_header(self, name_header, id_header):
        """
        Write the column header row for the totals rows.

        """
        choices = self.election_info.choices
        # Each choices value is a 2-tuple of (contest_id, choice_name).
        choice_names = (choices[choice_id][1] for choice_id in self.sorted_choice_ids)
        values = [name_header]
        values.extend(self.extra_header_names())
        values.extend([id_header, "Precincts", "Registration", "Ballots Cast", "Turnout (%)"])
        values.extend(choice_names)
        self.write_row(values)

    def write_totals_row(self, area_precinct_ids, area_name, area_label, reporting_indices):
        """
        Write a row for a contest, for a participating district or area.

        The area can be a precinct or district, for example, like
        "Pct 9503/9504" or "12TH CONGRESSIONAL DISTRICT".  It can also
        be a single precinct.

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
            precinct_voted = voted[precinct_id]
            for r_index in reporting_indices:
                totals[2] += precinct_voted[r_index]

                for i, choice_id in enumerate(choice_ids, start=extra_columns):
                    totals[i] += precinct_results[r_index][choice_id]

        assert totals[0] > 0
        # Prevent division by zero.
        totals[3] = "0.00" if totals[1] == 0 else "{:.2%}".format(totals[2] / totals[1])[:-1]
        values = list(self.make_first_fields(area_name, area_label, reporting_indices))
        values.extend(totals)
        self.write_row(values)

    def write_grand_totals_row(self, header, reporting_indices=None):
        """
        Write a row for the city-wide totals.

        """
        if reporting_indices is None:
            reporting_indices = self.reporting_indices
        all_precinct_ids = self.areas_info.city
        # The area ID "City:0" is just a placeholder value so the column
        # value can have the same format as other rows in the summary.
        self.write_totals_row(all_precinct_ids, header, "City:0", reporting_indices)

    def write_precincts(self):
        """Write the rows for all precincts."""
        precincts = self.election_info.precincts
        for precinct_id in sorted(self.precinct_ids):
            precinct_name = precincts[precinct_id]
            self.write_precinct(precinct_id, precinct_name)

    def write_post_precincts(self, header):
        pass

    def write_area_rows(self, area_type, area_type_name, make_area_name, area_ids):
        contest_precinct_ids = self.precinct_ids
        for area_id in area_ids:
            area_name = make_area_name(area_id)
            area_label = "%s:%s" % (area_type_name, area_id)
            area_precinct_ids = area_type[area_id]
            assert type(area_precinct_ids) is set
            if area_precinct_ids.isdisjoint(contest_precinct_ids):
                # Then no precincts in the district overlapped the contest, so skip it.
                log.info("  skipping area: contest has no precincts in: %s" % (area_name, ))
                continue
            try:
                self.write_totals_row(area_precinct_ids, area_name, area_label, self.reporting_indices)
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

    def write_precinct_report(self):
        self.write_ln("Precinct Totals")
        self.write_totals_row_header("PrecinctName", "PrecinctID")
        self.write_precincts()
        self.write_post_precincts(GRAND_TOTALS_HEADER)
        self.write_grand_totals_row(GRAND_TOTALS_HEADER)

    def write_district_report(self):
        self.write_ln("District and Neighborhood Totals")
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
        contest_info = self.contest_info
        contest_name = contest_info.name
        log.info("writing contest: %s (%d precincts)" %
                 (contest_name, len(self.precinct_ids)))
        # TODO: move this assertion earlier in the script?
        assert type(self.precinct_ids) is set
        contest_title = "%s - %s (%d)" % (contest_name, contest_info.district_name, contest_info.id)
        self.write_contest_start(contest_title)
        self.write_precinct_report()
        self.write_ln()
        # Repeat the contest title for the convenience of people looking
        # at the district summary.
        self.write_ln(contest_title)
        self.write_district_report()


class SimpleContestWriter(ContestWriter):

    def write_precinct(self, precinct_id, precinct_name):
        """Write the row or rows for a single precinct."""
        # Convert precinct_id into an iterable with one element in order
        # to use write_totals_row().
        self.write_totals_row((precinct_id, ), precinct_name, precinct_id, REPORTING_INDICES_SIMPLE)


class CompleteContestWriter(ContestWriter):

    headers = {
        REPORTING_INDICES[utils.REPORTING_TYPE_ELD]: "Election Day",
        REPORTING_INDICES[utils.REPORTING_TYPE_VBM]: "VBM",
    }

    def extra_header_names(self):
        return ("ReportingType", )

    def make_first_fields(self, area_name, area_label, reporting_indices):
        if len(reporting_indices) > 1:
            r_header = ""
        else:
            r_header = self.headers[reporting_indices[0]]
        return (area_name, r_header, area_label)

    def write_precinct(self, precinct_id, precinct_name):
        """Write the row or rows for a single precinct."""
        for r_index in REPORTING_INDICES_COMPLETE:
            self.write_totals_row((precinct_id, ), precinct_name, precinct_id, (r_index, ))

    def write_post_precincts(self, header):
        for r_index in REPORTING_INDICES_COMPLETE:
            self.write_grand_totals_row(GRAND_TOTALS_HEADER, (r_index, ))


class ResultsWriter(object):

    def __init__(self, path, now=None):
        if now is None:
            now = datetime.now()
        self.path = path
        self.now = now

    def write(self, info):
        with time_it("writing output file: %s" % self.name):
            with self.writer():
                self.write_start(info)
                self.write_contests(info)

    def write_contests(self, info):
        contests_info = info.meta.contests
        contests_results = info.results.contests

        for contest_id in sorted(contests_info.keys()):
            contest_info = contests_info[contest_id]
            contest_results = contests_results[contest_id]

            writer_cls = self.get_writer_class(info)
            try:
                contest_writer = writer_cls(info, contest_info, contest_results)
                self.write_contest(contest_writer)
            except:
                raise Exception("while processing contest: %s" % contest_info.name)


class TSVMixin(object):

    def write_ln(self, s=""):
        print(s, file=self.file)

    def write_row(self, values):
        self.write_ln(WRITER_DELIMITER.join([str(v) for v in values]))

    def write_contest_start(self, contest_title):
        # Begin each contest with a distinctive string.  We use 3 stars.
        # Doing this makes it easier for people to both (1) search through
        # the CSV (e.g. by using COMMAND+F or CTRL+F), and (2) parse the
        # file with a script (since it gives people an easy way to find
        # where the lines for each contest start).
        self.write_ln("*** %s" % contest_title)


class TSVSimpleContestWriter(SimpleContestWriter, TSVMixin):
    pass


class TSVCompleteContestWriter(CompleteContestWriter, TSVMixin):
    pass


class TSVWriter(ResultsWriter, TSVMixin):

    name = "TSV"

    def get_writer_class(self, info):
        return TSVCompleteContestWriter if info.meta.has_reporting_type else TSVSimpleContestWriter

    @contextmanager
    def writer(self):
        with open(self.path, "w", encoding='utf-8') as f:
            self.file = f
            yield

    def write_start(self, info):
        self.write_ln(info.name)
        self.write_ln()
        now = self.now
        # This looks like the following, for example:
        #   Report generated on: Friday, September 12, 2014 at 09:06:26 PM
        self.write_ln("Report generated on: %s %d, %s" %
                      (now.strftime("%A, %B"),
                       now.day,  # strftime lacks an option not to zero-pad the month.
                       now.strftime("%Y at %I:%M:%S %p")))

    def write_contest(self, contest_writer):
        self.write_ln()
        self.write_ln()
        contest_writer.file = self.file
        contest_writer.write()


class ExcelMixin(object):

    row_index = 0

    def write_row(self, values):
        self.worksheet.write_row(self.row_index, 0, values)
        self.row_index += 1

    def write_ln(self, s=""):
        self.write_row((s, ))

    def write_contest_start(self, contest_title):
        self.write_ln(contest_title)
        self.write_ln()


class ExcelSimpleContestWriter(SimpleContestWriter, ExcelMixin):
    pass


class ExcelCompleteContestWriter(CompleteContestWriter, ExcelMixin):
    pass


class ExcelWriter(ResultsWriter, ExcelMixin):

    name = "Excel"

    def get_writer_class(self, info):
        return ExcelCompleteContestWriter if info.meta.has_reporting_type else ExcelSimpleContestWriter

    @contextmanager
    def writer(self):
        workbook = xlsxwriter.Workbook(self.path)
        self.workbook = workbook
        yield
        workbook.close()

    def write_start(self, info):
        pass

    def write_contest(self, contest_writer):
        workbook = self.workbook
        contest_info = contest_writer.contest_info

        name = "%d - %s" % (contest_info.id, contest_info.name)
        # Worksheet names must be 31 characters or less.
        name = name[:31]
        worksheet = workbook.add_worksheet(name)

        contest_writer.worksheet = worksheet
        contest_writer.write()
