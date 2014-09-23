
from datetime import datetime
from pathlib import Path
import unittest

from parser import convert

def parse_test_file(now=None):
    p = Path(__file__).parents[1] / 'data/test'

    precincts_path, exports_path, expected_path = (str(p / name) for name in
        ("precincts.csv", "export.txt", "out.tsv"))

    output_path = "temp.txt"

    convert(election_name="Test Election", precincts_path=precincts_path,
            export_path=exports_path, output_path=output_path, now=now)

    return output_path, expected_path


class EndToEndTest(unittest.TestCase):

    def assert_files_equal(self, actual_file, expected_file):
        for line_no, (line1, line2) in enumerate(zip(actual_file, expected_file), start=1):
            self.assertEqual(line1, line2, msg=("at line %d in actual and expected files, respectively" % line_no))

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
