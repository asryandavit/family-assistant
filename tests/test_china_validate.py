"""china/validate.py: the contract accepts a real answer and rejects every defect whole."""
import copy
import json
import os
import unittest

from china import validate

F = os.path.join(os.path.dirname(__file__), "fixtures", "china")


def good():
    with open(os.path.join(F, "answer_pinduoduo_contract.json"), encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_source")
    return d


class Accepts(unittest.TestCase):
    def test_real_answer(self):
        a = validate.answer(good(), "pinduoduo")
        self.assertEqual(a["status"], "ok")
        self.assertEqual(len(a["results"]), 3)
        self.assertEqual(a["results"][1]["price_text"], "¥159")
        self.assertTrue(all(r["site"] == "pinduoduo" for r in a["results"]))

    def test_check_page_without_results(self):
        a = validate.answer({"site": "taobao", "status": "check", "notice": "访问异常",
                             "search_ids": [], "results": []}, "taobao")
        self.assertEqual((a["status"], a["results"]), ("check", []))

    def test_json_in_fences(self):
        txt = "Here it is:\n```json\n" + json.dumps(good(), ensure_ascii=False) + "\n```\nDone {x}"
        self.assertEqual(validate.extract_json(txt)["site"], "pinduoduo")


class Rejects(unittest.TestCase):
    def bad(self, mutate, site="pinduoduo"):
        d = good()
        mutate(d)
        with self.assertRaises(ValueError):
            validate.answer(d, site)

    def test_wrong_site(self):
        self.bad(lambda d: None, site="1688")

    def test_status_and_category(self):
        self.bad(lambda d: d.update(status="fine"))
        self.bad(lambda d: d.update(category="gadgets"))

    def test_id_not_on_search_page(self):
        self.bad(lambda d: d["results"][0].update(id="123456789"))

    def test_id_not_numeric(self):
        self.bad(lambda d: d["results"][0].update(id="abc"))
        self.bad(lambda d: d["search_ids"].append("12ab"))

    def test_duplicate_result(self):
        self.bad(lambda d: d["results"].append(copy.deepcopy(d["results"][0])))

    def test_url_in_text(self):
        self.bad(lambda d: d["results"][0].update(why="see https://evil.example"))

    def test_too_many_points(self):
        self.bad(lambda d: d["results"][0].update(liked=["a", "b", "c", "d"]))

    def test_restrict_allow_list(self):
        self.bad(lambda d: d["results"][0].update(restrict=["explosive"]))

    def test_types(self):
        self.bad(lambda d: d["results"][0].update(price_text=159))
        self.bad(lambda d: d["results"][0].update(likely_over_1kg="yes"))
        self.bad(lambda d: d["results"][0].update(price_kind="cheap"))
        self.bad(lambda d: d["results"][0].update(title_en=""))
        self.bad(lambda d: d["results"][0].update(specs=["65W"]))

    def test_ok_without_results(self):
        self.bad(lambda d: d.update(results=[]))

    def test_one_bad_result_rejects_all(self):
        d = good()
        d["results"][2]["complaints"] = "not a list"
        with self.assertRaises(ValueError):
            validate.answer(d, "pinduoduo")

    def test_no_json(self):
        with self.assertRaises(ValueError):
            validate.extract_json("I could not open the page.")
        with self.assertRaises(ValueError):
            validate.extract_json('{"site": "pinduoduo"')


if __name__ == "__main__":
    unittest.main()
