"""china/search.py end to end, offline: fake plan, fake site readers (the P0-derived answer),
fake Telegram. Checks the order: questions when vague; progress per site; one answer to the
asking chat; a failing site named while the others still answer; /china last saved after."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import date

from china import runner, search, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "tests", "fixtures", "china")
RATES = {"date": "2026-10-30", "amd_per": {"USD": 360.14, "EUR": 403.36, "CNY": 54.132}}


def pdd_answer():
    with open(os.path.join(F, "answer_pinduoduo_contract.json"), encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_source")
    return validate.answer(d, "pinduoduo")


class TG:
    def __init__(self, rich_ok=True):
        self.sent, self.rich_ok = [], rich_ok

    def send_html(self, cfg, text, silent=False, buttons=None, chat_id=None, **kw):
        self.sent.append(("html", chat_id, text, buttons))

    def send_rich(self, cfg, rich, plain, silent=True, buttons=None, chat_id=None):
        self.sent.append(("rich", chat_id, rich, buttons))
        return ("rich", 1) if self.rich_ok else ("plain", None)

    @staticmethod
    def esc(s):
        return s


class Search(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "market"))
        shutil.copy(os.path.join(ROOT, "config_china.json"), self.root)
        shutil.copy(os.path.join(ROOT, "market", "tariffs.json"), os.path.join(self.root, "market"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def plan(self, vague=False):
        p = {"query_cn": "氮化镓充电器 65W", "query_en": "GaN charger 65W", "category": "electronics",
             "vague": vague, "questions": [{"q": "Budget?", "options": ["< ¥100", "¥100–200"]}] if vague else []}
        return lambda cfg, ccfg, desc: (p, {})

    def reader(self, cfg, ccfg, site, desc, q, log=print):
        if site == "pinduoduo":
            return pdd_answer(), {"ms": 1}
        if site == "taobao":
            return {"site": "taobao", "status": "login", "notice": "亲，请登录", "category": "other",
                    "brand_guidance": None, "search_ids": [], "results": []}, {}
        raise RuntimeError("boom")

    def run_job(self, tg, vague=False, **job):
        j = {"job": "ab12cd34", "kind": "search", "chat_id": "222", "description": "GaN charger 65W"}
        j.update(job)
        return search.run_search(j, {}, self.root, tg, date(2026, 11, 9), log=lambda m: None,
                                 read=self.reader, plan_fn=self.plan(vague),
                                 rates_get=lambda root, d: RATES)

    def test_full_answer(self):
        tg = TG()
        self.assertEqual(self.run_job(tg), "rich")
        progress = [t for k, c, t, b in tg.sent if k == "html"]
        self.assertEqual(len(progress), 3)
        self.assertIn("Pinduoduo done (1/3)", progress[0])
        self.assertIn("Taobao logged out (2/3)", progress[1])
        self.assertIn("1688 not read (3/3)", progress[2])
        kind, chat, rich, _ = tg.sent[-1]
        self.assertEqual((kind, chat), ("rich", "222"))       # to the asking chat only
        self.assertIn("Taobao logged out — open Chrome on the PC and sign in", rich)
        self.assertIn("1688 could not be read this time", rich)
        self.assertIn("🏆", rich)
        last = search.load_last(self.root, "222")
        self.assertEqual(last["job"], "ab12cd34")
        self.assertEqual(len(last["sites"][0]["ranked"]), 3)

    def test_vague_asks_first(self):
        tg = TG()
        self.assertEqual(self.run_job(tg, vague=True), "asked")
        self.assertEqual(len(tg.sent), 1)
        _, chat, text, btns = tg.sent[0]
        self.assertIn("Budget?", text)
        self.assertEqual(btns[0][0][1], "cn:q:ab12cd34:0:0")
        self.assertIsNotNone(search.read_json(self.root, "pending_ab12cd34.json"))
        self.assertIsNone(search.load_last(self.root, "222"))

    def test_answers_skip_questions(self):
        tg = TG()
        self.assertEqual(self.run_job(tg, vague=True, answers=["< ¥100"],
                                      plan={"query_cn": "氮化镓充电器 65W", "vague": False,
                                            "questions": [], "category": "electronics"}), "rich")

    def test_taobao_link_mode(self):
        cfg = json.load(open(os.path.join(self.root, "config_china.json"), encoding="utf-8"))
        cfg["taobao_mode"] = "link"
        json.dump(cfg, open(os.path.join(self.root, "config_china.json"), "w", encoding="utf-8"))
        called = []

        def reader(c, cc, site, d, q, log=print):
            called.append(site)
            return search.read_site(c, cc, site, d, q, log) if site == "taobao" else self.reader(c, cc, site, d, q)
        tg = TG()
        search.run_search({"job": "j1", "chat_id": "222", "description": "GaN 65W",
                           "sites": ["pinduoduo", "taobao"]}, {}, self.root, tg, date(2026, 11, 9),
                          log=lambda m: None, read=reader, plan_fn=self.plan(),
                          rates_get=lambda r, d: RATES)
        rich = tg.sent[-1][2]
        self.assertIn("Taobao is not read automatically", rich)
        self.assertIn("open this search on Taobao", rich)
        self.assertIn("https://s.taobao.com/search?q=", rich)
        self.assertEqual(len([1 for k, *_ in tg.sent if k == "html"]), 1)   # progress for PDD only

    def test_only_one_site(self):
        tg = TG()
        self.run_job(tg, sites=["pinduoduo"])
        self.assertEqual(len([1 for k, *_ in tg.sent if k == "html"]), 1)

    def test_find_result_for_buttons(self):
        self.run_job(TG())
        p, _ = search.find_result(self.root, "222", "ab12cd34", 2)
        self.assertIsNotNone(p)
        self.assertEqual(search.find_result(self.root, "222", "other", 1)[0], None)
        self.assertEqual(search.find_result(self.root, "111", "ab12cd34", 1)[0], None)  # other chat


class Repair(unittest.TestCase):
    """runner: a bad reply is re-asked once with --resume, then rejected whole."""

    def fake_run(self, replies):
        calls = []

        class P:
            def __init__(self, out):
                self.returncode, self.stdout, self.stderr = 0, out, ""

        def run(cmd, **kw):
            calls.append(cmd)
            return P(json.dumps(replies[len(calls) - 1]))
        return run, calls

    def test_repaired_once(self):
        good = pdd_answer()
        bad = dict(good, status="fine")
        run, calls = self.fake_run([{"result": json.dumps(bad), "session_id": "s1"},
                                    {"result": json.dumps(good, ensure_ascii=False), "session_id": "s1"}])
        a, _ = runner.site({"claude_cmd": "claude"}, {"claude_model": "sonnet"}, "pinduoduo",
                           "GaN 65W", "氮化镓充电器", run=run)
        self.assertEqual(a["status"], "ok")
        self.assertIn("--chrome", calls[0])
        self.assertIn("--resume", calls[1])
        self.assertNotIn("--chrome", calls[1])                # the repair never browses again

    def test_rejected_after_one_repair(self):
        bad = {"result": '{"site": "pinduoduo", "status": "fine"}', "session_id": "s1"}
        run, calls = self.fake_run([bad, bad])
        a, _ = runner.site({"claude_cmd": "claude"}, {}, "pinduoduo", "x", "y", run=run)
        self.assertEqual(a["status"], "error")
        self.assertEqual(a["results"], [])
        self.assertEqual(len(calls), 2)

    def test_api_key_never_passed(self):
        seen = {}

        def run(cmd, **kw):
            seen.update(kw["env"])

            class P:
                returncode, stdout, stderr = 0, json.dumps({"result": "{}"}), ""
            return P()
        os.environ["ANTHROPIC_API_KEY"] = "should-not-pass"
        try:
            runner.call({"claude_cmd": "claude"}, "x", run=run)
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
        self.assertNotIn("ANTHROPIC_API_KEY", seen)

    def test_chrome_tools_allow_list(self):
        self.assertNotIn("form_input", runner.CHROME_TOOLS)
        self.assertNotIn("upload", runner.CHROME_TOOLS)
        self.assertIn("form_input", runner.DENIED)


if __name__ == "__main__":
    unittest.main()
