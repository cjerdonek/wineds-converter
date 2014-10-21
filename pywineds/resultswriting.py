
"""
Supports writing results files.

"""

import logging

from pywineds.utils import time_it


GRAND_TOTALS_HEADER = "Grand Totals"
WRITER_DELIMITER = "\t"

log = logging.getLogger("wineds")


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
                log.info("   no precincts: %s" % (area_name, ))
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
        log.info("writing contest: %s (%d precincts)" %
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


class SimpleContestWriter(ContestWriter):
    pass


class CompleteContestWriter(ContestWriter):
    pass


class ResultsWriter(Writer):

    def __init__(self, file, election_name, now=None):
        if now is None:
            now = datetime.now()
        self.election_name = election_name
        self.file = file
        self.now = now

    def write_inner(self, election_info, areas_info, results):
        info_contests = election_info.contests
        results_contests = results.contests

        self.write_ln(self.election_name)
        self.write_ln()
        # This looks like the following, for example:
        #   Report generated on: Friday, September 12, 2014 at 09:06:26 PM
        now = self.now
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
