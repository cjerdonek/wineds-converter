
from datetime import datetime
from pathlib import Path
import unittest

from pywineds.parser import convert, parse_data_chunk, split_line_fixed


class ModuleTest(unittest.TestCase):

    def test_split_line_fixed__simple(self):
        """Check parsing a "simple" line (i.e. 175 characters long)."""
        line = ("0001001110800827          REGISTERED VOTERS - TOTAL"
                "                               VOTERS"
                "                                Pct 1108"
                "                                               \n")
        actual = split_line_fixed(line)
        expected = ('0001001110800827', 'REGISTERED VOTERS - TOTAL',
                    'VOTERS', 'Pct 1108', '', '')
        self.assertEqual(actual, expected)

    def test_split_line_fixed__complete(self):
        """Check parsing a "complete" line (i.e. 205 characters long)."""
        line = ("0010073990000000PF        US Representative, District 13                          "
                "LAWERENCE N. ALLEN                    Pct 9900 MB                   "
                "13TH CONGRESSIONAL DISTRITC-Election Day Reporting     \n")
        actual = split_line_fixed(line)
        expected = ('0010073990000000PF', 'US Representative, District 13',
                    'LAWERENCE N. ALLEN', 'Pct 9900 MB', '13TH CONGRESSIONAL DISTRI',
                    'TC-Election Day Reporting')
        self.assertEqual(actual, expected)

    def test_parse_data_chunk(self):
        self.assertEqual(parse_data_chunk("0001001110100484"), (1, 1, 1101, 484, ''))
        self.assertEqual(parse_data_chunk("0100016113100001NON"), (16, 100, 1131, 1, 'NON'))
        self.assertEqual(parse_data_chunk("01000167208000-1NON"), (16, 100, 7208, -1, 'NON'))


def parse_test_file(label, name, now=None):
    test_dir = Path(__file__).parents[1] / 'test_data'

    precincts_path = str(test_dir / "precincts.csv")
    test_dir /= label
    input_name = "wineds_%s.txt" % label
    exports_path, expected_path = (str(test_dir / name) for name in (input_name, "output.tsv"))

    output_path = "temp.txt"

    convert(election_name=name, precincts_path=precincts_path,
            export_path=exports_path, output_path=output_path, now=now)

    return output_path, expected_path


class EndToEndTest(unittest.TestCase):

    def assert_files_equal(self, actual_file, expected_file):
        for line_no, (line1, line2) in enumerate(zip(actual_file, expected_file), start=1):
            self.assertEqual(line1, line2, msg=("at line %d in actual and expected files, respectively" % line_no))
        # Check that neither file has lines remaining.
        for f, name in ((actual_file, "actual"), (expected_file, "expected")):
            msg = "%r file has more lines than the other starting at line %d" % (name, line_no + 1)
            with self.assertRaises(StopIteration, msg=msg):
                next(f)

    def check_end_to_end(self, label, name):
        now = datetime(2014, 9, 22, 22, 30, 13)
        actual_path, expected_path = parse_test_file(label, name, now)
        def read(path):
            return open(path, "r", encoding="utf-8")

        with read(actual_path) as actual_file, \
              read(expected_path) as expected_file:
            self.assert_files_equal(actual_file, expected_file)

    def test_end_to_end__simple(self):
        self.check_end_to_end("simple", "Test Election")

    def test_end_to_end__complete(self):
        self.check_end_to_end("complete", "Test Election (Complete Data)")


if __name__ == "__main__":
    unittest.main()
