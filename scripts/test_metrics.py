"""Checks for contribution parsing, ranking, and truthful language proportions."""

import unittest
import xml.etree.ElementTree as ET
from update_metrics import ContributionCalendar, activity, rank, stats


class MetricsTests(unittest.TestCase):
    def test_calendar_parses_zero_and_thousands_without_filling_missing_days(self):
        parser = ContributionCalendar()
        parser.feed('''<td id="a" data-date="2026-11-01"></td>
          <tool-tip for="a">No contributions on November 1st.</tool-tip>
          <td id="b" data-date="2026-11-02"></td>
          <tool-tip for="b">1,234 contributions on November 2nd.</tool-tip>
          <td id="c" data-date="2026-11-03"></td>''')
        self.assertEqual(parser.days(), {"2026-11-01": 0, "2026-11-02": 1234})

    def test_rank_handles_zero_and_high_counts(self):
        empty = dict.fromkeys(("commits", "prs", "issues", "reviews", "stars", "followers"), 0)
        self.assertEqual(rank(empty), ("C", 0))
        self.assertEqual(rank(dict.fromkeys(empty, 100000))[0], "S")
        self.assertEqual(rank(dict(commits=250, prs=50, issues=25, reviews=2, stars=50, followers=10)), ("B+", .5))

    def test_languages_keep_omitted_bytes_in_denominator(self):
        data = dict(year=2026, commits=0, prs=0, issues=0, reviews=0, stars=0, followers=0,
                    languages=[{"name": chr(65+i), "bytes": 10, "color": "#ffffff"} for i in range(8)])
        for mobile in (False, True):
            output = stats(data, mobile)
            ET.fromstring(output)
            self.assertIn("A · 12.5%", output)
            self.assertIn("Other · 37.5%", output)

    def test_empty_calendar_renders_finite_coordinates(self):
        data = {"days": [{"date": f"2026-10-{i+1:02}", "count": 0} for i in range(31)]}
        for mobile in (False, True):
            output = activity(data, mobile)
            ET.fromstring(output)
            self.assertNotIn("nan", output.lower())
            self.assertNotIn("infinity", output.lower())


if __name__ == "__main__":
    unittest.main()
