import unittest

from app.ui.live_insights import append_or_merge_live_row, tentative_insights_from_live_rows


class LiveInsightsTests(unittest.TestCase):
    def test_merges_short_final_segments_for_stable_live_rows(self):
        rows = []
        append_or_merge_live_row(rows, "00:01", "Meeting Audio", "Maya will review the switch logs", False)
        append_or_merge_live_row(rows, "00:03", "Meeting Audio", "by tomorrow.", False)

        self.assertEqual(len(rows), 1)
        self.assertIn("Maya will review", rows[0][2])
        self.assertIn("by tomorrow", rows[0][2])

    def test_tentative_live_insights_extract_action_and_date(self):
        rows = [
            (
                "00:10",
                "Meeting Audio",
                "Maya will review the switch logs by tomorrow. The team decided the backup schedule will remain unchanged.",
                False,
            )
        ]

        insights = tentative_insights_from_live_rows(rows)

        self.assertEqual(len(insights.actions), 1)
        self.assertEqual(insights.actions[0].owner, "Maya")
        self.assertEqual(insights.actions[0].due_date, "Tomorrow")
        self.assertEqual(insights.actions[0].confidence, "Tentative")
        self.assertEqual(len(insights.dates), 1)
        self.assertEqual(len(insights.decisions), 1)


if __name__ == "__main__":
    unittest.main()
