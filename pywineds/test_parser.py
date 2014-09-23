
from pathlib import Path
import unittest

from parser import convert

def parse_test_file():
    p = Path(__file__).parents[1] / 'data/test'

    precincts_path = str(p / "precincts.csv")
    exports_path = str(p / "export.txt")
    output_path = "temp.txt"

    convert(election_name="Test Election", precincts_path=precincts_path,
            export_path=exports_path,
            output_path=output_path)

class EndToEndTest(unittest.TestCase):

    def test(self):
        parse_test_file()
        self.assertEqual(1, 1)

if __name__ == "__main__":
    unittest.main()
