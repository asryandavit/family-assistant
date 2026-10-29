"""Watch list Sheet: rows out, phone edits merged back in (market/sheet.py)."""
import unittest

from market import sheet, state

UK = "https://www.amazon.co.uk/dp/B0B7RZBWLR"
DE = "https://www.amazon.de/dp/B0B7RZBWLR"


def items():
    out = []
    out.append(state.new_item(out, "Airfryer", [UK], weight_kg=5.2, size_cm=[45, 35, 25], added_by="Davit"))
    return out


class Rows(unittest.TestCase):
    def test_item_rows(self):
        rows = sheet.item_rows(items())
        self.assertEqual(rows[0], sheet.ITEMS)
        self.assertEqual(rows[1][:9], ["1", "Airfryer", "exact", UK, "", "amazon_uk", 1, 5.2, "45x35x25"])

    def test_formula_injection_guarded(self):
        self.assertEqual(sheet.cell("=IMPORTXML(1)"), "'=IMPORTXML(1)")
        self.assertEqual(sheet.cell("-5"), "'-5")
        self.assertEqual(sheet.cell("Airfryer"), "Airfryer")


class Merge(unittest.TestCase):
    def test_phone_edit_applies(self):
        rows = sheet.item_rows(items())
        rows[1][7] = "4,8"                 # decimal comma typed on a phone
        rows[1][3] = UK + "\n" + DE
        rows[1][11] = "bought"
        merged, problems = sheet.merge(items(), rows)
        self.assertEqual(problems, [])
        self.assertEqual(merged[0]["weight_kg"], 4.8)
        self.assertEqual(merged[0]["links"], [UK, DE])
        self.assertEqual(merged[0]["status"], "bought")

    def test_bad_value_keeps_old_and_says_so(self):
        rows = sheet.item_rows(items())
        rows[1][7] = "heavy"
        merged, problems = sheet.merge(items(), rows)
        self.assertEqual(merged[0]["weight_kg"], 5.2)
        self.assertEqual(len(problems), 1)
        self.assertIn("row 2 weight_kg", problems[0])

    def test_new_row_without_id(self):
        rows = sheet.item_rows(items())
        rows.append(["", "Kettle", "", DE] + [""] * 9)
        merged, problems = sheet.merge(items(), rows)
        self.assertEqual([m["name"] for m in merged], ["Airfryer", "Kettle"])
        self.assertEqual(merged[1]["id"], "2")
        self.assertEqual(merged[1]["added_by"], "Sheet")

    def test_row_missing_link_rejected(self):
        rows = sheet.item_rows(items()) + [["", "Kettle"] + [""] * 11]
        merged, problems = sheet.merge(items(), rows)
        self.assertEqual(len(merged), 1)
        self.assertIn("needs a name and a link", problems[0])

    def test_deleted_row_keeps_item(self):
        merged, problems = sheet.merge(items(), [sheet.ITEMS])
        self.assertEqual(len(merged), 1)

    def test_empty_read_changes_nothing(self):
        its = items()
        self.assertEqual(sheet.merge(its, []), (its, []))


class TypedInput(unittest.TestCase):
    def test_weight(self):
        self.assertEqual(state.parse_weight("2,4 kg"), 2.4)
        self.assertEqual(state.parse_weight("800 g"), 0.8)
        self.assertEqual(state.parse_weight("5 lb"), 2.268)
        for bad in ("", "abc", "0", "500 kg"):
            with self.assertRaises(ValueError):
                state.parse_weight(bad)

    def test_size(self):
        self.assertEqual(state.parse_size("40x30x20"), [40.0, 30.0, 20.0])
        self.assertEqual(state.parse_size("16 × 12 × 8 in"), [40.6, 30.5, 20.3])
        with self.assertRaises(ValueError):
            state.parse_size("40x30")

    def test_weight_and_size(self):
        self.assertEqual(state.parse_weight_and_size("2.4 kg 40x30x20"), (2.4, [40.0, 30.0, 20.0]))
        self.assertEqual(state.parse_weight_and_size("40x30x20"), (None, [40.0, 30.0, 20.0]))
        with self.assertRaises(ValueError):
            state.parse_weight_and_size("dunno")

    def test_qty_and_amount(self):
        self.assertEqual(state.parse_qty("3"), 3)
        with self.assertRaises(ValueError):
            state.parse_qty("0")
        self.assertEqual(state.parse_amount("79,99"), (79.99, None))
        self.assertEqual(state.parse_amount("9890₽"), (9890.0, "RUB"))
        with self.assertRaises(ValueError):
            state.parse_amount("free")

    def test_list_limit(self):
        its = []
        for i in range(state.MAX_ITEMS):
            its.append(state.new_item(its, "x%d" % i, [UK]))
        with self.assertRaises(ValueError):
            state.new_item(its, "one more", [UK])


if __name__ == "__main__":
    unittest.main()
