
from datetime import datetime
from pathlib import Path
import unittest

from parser import convert, split_line_fixed


class ModuleTest(unittest.TestCase):

    def test_split_line_fixed(self):
        line = ("0010073990000000PF        US Representative, District 13                          "
                "LAWERENCE N. ALLEN                    Pct 9900 MB                   "
                "13TH CONGRESSIONAL DISTRITC-Election Day Reporting     \n")
        actual = split_line_fixed(line)
        expected = ('0010073990000000PF', 'US Representative, District 13',
                    'LAWERENCE N. ALLEN', 'Pct 9900 MB', '13TH CONGRESSIONAL DISTRI',
                    'TC-Election Day Reporting')
        self.assertEqual(actual, expected)


def parse_test_file(now=None):
    p = Path(__file__).parents[1] / 'data/test'

    precincts_path, exports_path, expected_path = (str(p / name) for name in
        ("precincts.csv", "wineds.txt", "output.tsv"))

    output_path = "temp.txt"

    convert(election_name="Test Election", precincts_path=precincts_path,
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

    def test_end_to_end(self):
        now = datetime(2014, 9, 22, 22, 30, 13)
        actual_path, expected_path = parse_test_file(now)
        def read(path):
            return open(path, "r", encoding="utf-8")

        with read(actual_path) as actual_file, \
              read(expected_path) as expected_file:
            self.assert_files_equal(actual_file, expected_file)


if __name__ == "__main__":
    unittest.main()
