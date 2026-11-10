"""/china photo search (decision 095), offline.

china/photo.py (pick the image, caption command, Bot API download, delete), the photo plan
validator on the live capture and its rejection paths, the runner's command lines (the photo
goes in on stdin, never the command line; file_upload is allowed only for the photo run),
the worker flow (1688 by photo, Pinduoduo by words, Taobao link + app tip, photo deleted),
and the bot (a /china caption searches; any other photo gets one question)."""
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import date
from unittest import mock

from china import bot, photo, queue, runner, search, validate
from tests.test_china_search import RATES, TG, pdd_answer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "tests", "fixtures", "china")
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def write_jpeg(token, file_id, dest):
    with open(dest, "wb") as f:
        f.write(JPEG)


def live_plan():
    with open(os.path.join(F, "photo_plan_live.json"), encoding="utf-8") as f:
        return validate.extract_json(json.load(f)["result"])


class Resp:
    def __init__(self, js=None, content=b"", status=200):
        self._js, self.content, self.status_code = js, content, status

    def json(self):
        return self._js


def fake_get(file_path="photos/file_7.jpg", size=1000, content=JPEG, ok=True, status=200):
    calls = []

    def get(url, params=None, timeout=None):
        calls.append(url)
        if url.endswith("/getFile"):
            return Resp({"ok": ok, "result": {"file_path": file_path, "file_size": size}})
        return Resp(content=content, status=status)
    get.calls = calls
    return get


class Helpers(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_pick_largest_photo_under_limit(self):
        msg = {"photo": [{"file_id": "s", "width": 90, "height": 90, "file_size": 2000},
                         {"file_id": "m", "width": 800, "height": 800, "file_size": 90000},
                         {"file_id": "huge", "width": 9000, "height": 9000, "file_size": 11 << 20}]}
        self.assertEqual(photo.pick(msg), {"file_id": "m", "size": 90000, "ext": "jpg"})

    def test_pick_image_file_but_not_other_files(self):
        self.assertEqual(photo.pick({"document": {"file_id": "d", "mime_type": "image/png",
                                                  "file_size": 5}})["ext"], "png")
        self.assertIsNone(photo.pick({"document": {"file_id": "d", "mime_type": "application/pdf"}}))
        self.assertIsNone(photo.pick({"sticker": {"file_id": "x"}}))
        self.assertIsNone(photo.pick({"text": "hi"}))

    def test_caption_command(self):
        self.assertIsNone(photo.caption_command(None))
        self.assertIsNone(photo.caption_command("my new shoes"))
        self.assertEqual(photo.caption_command("/china"), (None, ""))
        self.assertEqual(photo.caption_command("/china red, size 42"), (None, "red, size 42"))
        self.assertEqual(photo.caption_command("/china@FamilyBot only PDD red"), (["pinduoduo"], "red"))
        self.assertEqual(photo.caption_command("/CHINA only 1688"), (["1688"], ""))
        with self.assertRaises(ValueError):
            photo.caption_command("/china only amazon red")

    def test_download_writes_file(self):
        dest = photo.path_for(self.root, "ab12cd34")
        get = fake_get()
        photo.download("TOKEN", "FILEID", dest, get=get)
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), JPEG)
        self.assertTrue(get.calls[1].endswith("/file/botTOKEN/photos/file_7.jpg"))
        self.assertEqual(os.listdir(photo.photos_dir(self.root)), ["ab12cd34.jpg"])

    def test_download_rejections_leave_nothing(self):
        dest = photo.path_for(self.root, "ab12cd34")
        cases = [fake_get(ok=False), fake_get(size=11 << 20), fake_get(file_path="../../etc/x"),
                 fake_get(content=b""), fake_get(status=404), fake_get(content=b"0" * (10 * 1024 * 1024 + 1))]
        for get in cases:
            with self.assertRaises(ValueError):
                photo.download("TOKEN", "FILEID", dest, get=get)
        self.assertEqual(os.listdir(photo.photos_dir(self.root)), [])

    def test_download_error_never_shows_token(self):
        def boom(url, params=None, timeout=None):
            raise ConnectionError("https://api.telegram.org/botSECRET/getFile failed")
        with self.assertRaises(ValueError) as e:
            photo.download("SECRET", "F", photo.path_for(self.root, "ab12cd34"), get=boom)
        self.assertNotIn("SECRET", str(e.exception))

    def test_path_for_refuses_odd_names(self):
        for bad in ("../x", "ab12cd3", "AB12CD34", None):
            with self.assertRaises(ValueError):
                photo.path_for(self.root, bad)
        with self.assertRaises(ValueError):
            photo.path_for(self.root, "ab12cd34", "exe")

    def test_sweep_and_find(self):
        old = photo.path_for(self.root, "aaaaaaaa")
        new = photo.path_for(self.root, "bbbbbbbb", "png")
        for p in (old, new):
            with open(p, "wb") as f:
                f.write(JPEG)
        os.utime(old, (time.time() - 3600, time.time() - 3600))
        self.assertEqual(photo.sweep(self.root, 30), 1)
        self.assertIsNone(photo.find(self.root, "aaaaaaaa"))
        self.assertEqual(photo.find(self.root, "bbbbbbbb"), new)
        self.assertEqual(photo.sweep(self.root, 0), 1)

    def test_mask(self):
        self.assertEqual(photo.mask("123456789"), "…789")
        self.assertEqual(photo.mask(None), "…")


class PlanValidator(unittest.TestCase):
    def test_live_capture_accepted(self):
        p = validate.photo_plan(live_plan())
        self.assertTrue(p["is_product"])
        self.assertEqual(p["category"], "electronics")
        self.assertIn("氮化镓", p["query_cn"])
        self.assertEqual((p["vague"], p["questions"]), (False, []))

    def test_not_a_product(self):
        self.assertEqual(validate.photo_plan({"is_product": False, "seen": "a sunset"}),
                         {"is_product": False, "seen": "a sunset"})

    def test_rejections(self):
        good = live_plan()
        for bad in ([], dict(good, query_cn=None), dict(good, query_cn="x" * 41),
                    dict(good, category="cars"), dict(good, is_product="yes"),
                    dict(good, query_en=None), dict(good, brand_seen="see https://x.com"),
                    dict(good, query_cn="http://evil")):
            with self.assertRaises(ValueError):
                validate.photo_plan(bad)


class Proc:
    def __init__(self, stdout, rc=0):
        self.stdout, self.returncode, self.stderr = stdout, rc, ""


class Runner(unittest.TestCase):
    def test_image_goes_in_on_stdin_with_no_tools(self):
        seen = {}
        img = os.path.join(tempfile.mkdtemp(), "ab12cd34.jpg")
        with open(img, "wb") as f:
            f.write(JPEG)

        def run(cmd, input=None, **kw):
            seen["cmd"], seen["input"] = cmd, input
            return Proc('{"type":"system"}\n{"type":"result","result":"{\\"is_product\\": false, '
                        '\\"seen\\": \\"a cat\\"}","session_id":"s"}\n')
        p, _ = runner.photo_plan({}, {"claude_model": "sonnet"}, img, "red", run=run)
        self.assertEqual(p, {"is_product": False, "seen": "a cat"})
        cmd = seen["cmd"]
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertNotIn("--chrome", cmd)
        self.assertFalse(any(len(c) > 200 for c in cmd))            # no image on the command line
        msg = json.loads(seen["input"])
        block = msg["message"]["content"][0]
        self.assertEqual((block["type"], block["source"]["media_type"]), ("image", "image/jpeg"))
        self.assertIn("red", msg["message"]["content"][1]["text"])

    def test_stream_result(self):
        self.assertEqual(runner.stream_result('x\n{"type":"result","result":"ok"}')["result"], "ok")
        with self.assertRaises(RuntimeError):
            runner.stream_result('{"type":"assistant"}')
        with self.assertRaises(RuntimeError):
            runner.stream_result('{"type":"result","is_error":true,"result":"quota"}')

    def test_upload_allowed_only_for_photo_run(self):
        cmds = []

        def run(cmd, **kw):
            cmds.append(cmd)
            return Proc('{"result": "{}", "session_id": null}')
        runner.call({}, "x", chrome=True, run=run)
        runner.call({}, "x", chrome=True, run=run, upload=True)
        text, ph = cmds
        def allowed(c):
            return c[c.index("--allowedTools") + 1].split(",")

        def denied(c):
            return c[c.index("--disallowedTools") + 1].split(",")
        self.assertNotIn(runner.UPLOAD, allowed(text))
        self.assertIn(runner.UPLOAD, denied(text))
        self.assertIn(runner.UPLOAD, allowed(ph))
        self.assertNotIn(runner.UPLOAD, denied(ph))
        for c in (text, ph):
            self.assertIn("mcp__claude-in-chrome__upload_image", denied(c))
            self.assertIn("mcp__claude-in-chrome__form_input", denied(c))
            self.assertIn("Bash", denied(c))
        self.assertEqual(set(allowed(ph)) - set(allowed(text)), {runner.UPLOAD})

    def test_photo_body(self):
        b = runner.photo_body("%E5%85%85", 3, r"D:\x\ab12cd34.jpg")
        self.assertIn('paths ["D:\\x\\ab12cd34.jpg"]', b)
        self.assertIn("data-renderkey", b)
        self.assertIn("2. For each chosen id: navigate to https://detail.1688.com/offer/", b)
        self.assertEqual(b.count("1. navigate"), 1)                # the word-search step 1 is left out
        self.assertIn("Reviews (first 3 chosen ids)", b)

    def test_site_photo_error_on_bad_reply(self):
        def run(cmd, **kw):
            return Proc('{"result": "not json", "session_id": null}')
        a, _ = runner.site_photo({}, {}, "charger", "充电器", "x.jpg", run=run)
        self.assertEqual((a["site"], a["status"]), ("1688", "error"))


class Worker(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "market"))
        shutil.copy(os.path.join(ROOT, "config_china.json"), self.root)
        shutil.copy(os.path.join(ROOT, "market", "tariffs.json"), os.path.join(self.root, "market"))
        self.read_calls = []

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def set_keep(self, minutes):
        p = os.path.join(self.root, "config_china.json")
        with open(p, encoding="utf-8") as f:
            c = json.load(f)
        c["photo_keep_minutes"] = minutes
        with open(p, "w", encoding="utf-8") as f:
            json.dump(c, f)

    def reader(self, cfg, ccfg, site, desc, q, log=print):
        self.read_calls.append((site, q))
        if site == "pinduoduo":
            return pdd_answer(), {}
        if site == "taobao":
            return {"site": "taobao", "status": "link", "notice": None, "category": "other",
                    "brand_guidance": None, "search_ids": [], "results": []}, {}
        return runner.error(site, "word search not expected"), {}

    def photo_reader(self, status="ok"):
        def read(cfg, ccfg, desc, q, path):
            self.assertTrue(os.path.exists(path))                     # the photo is there while it runs
            self.photo_path = path
            if status == "error":
                return runner.error("1688", "upload refused"), {}
            a = dict(pdd_answer(), site="1688", results=[])
            return a, {}
        return read

    def run_job(self, tg, plan=None, photo_status="ok", **job):
        j = {"job": "ab12cd34", "kind": "photo", "chat_id": "222", "file_id": "FILE", "ext": "jpg",
             "note": "", "sites": ["pinduoduo", "taobao", "1688"], "user_id": 222, "role": "adult"}
        j.update(job)
        p = plan or live_plan()
        return search.run_photo(
            j, {"telegram": {"bot_token_env": "NO_SUCH_ENV"}}, self.root, tg, date(2026, 11, 10),
            log=lambda m: None, plan_fn=lambda cfg, ccfg, path, note: (validate.photo_plan(p), {}),
            read=self.reader, read_photo=self.photo_reader(photo_status),
            rates_get=lambda r, d: RATES,
            download=write_jpeg)

    def test_full_photo_answer(self):
        tg = TG()
        self.assertEqual(self.run_job(tg), "rich")
        kind, chat, rich, _ = tg.sent[-1]
        self.assertEqual((kind, chat), ("rich", "222"))
        self.assertIn("China photo search", rich)
        self.assertIn("📷 UGREEN 65W GaN wall charger", rich)
        self.assertIn("searched as 绿联 65W氮化镓充电器 旅行套装", rich)
        self.assertIn("searched by the words read from your photo", rich)
        self.assertIn("tap the camera in the search bar", rich)
        self.assertIn("🏆", rich)
        self.assertIn(("pinduoduo", "绿联 65W氮化镓充电器 旅行套装"), self.read_calls)
        self.assertNotIn("1688", [s for s, q in self.read_calls])     # 1688 went by photo
        self.assertFalse(os.path.exists(self.photo_path))             # deleted after the answer
        last = search.load_last(self.root, "222")
        self.assertEqual((last["kind"], last["photo_of"], last["role"]), ("photo", "ab12cd34", "adult"))

    def test_live_1688_photo_answer_priced(self):
        with open(os.path.join(F, "answer_1688_photo_live.json"), encoding="utf-8") as f:
            live = validate.answer(json.load(f), "1688")          # the real reply still validates
        tg = TG()
        search.run_photo(
            {"job": "ab12cd34", "kind": "photo", "chat_id": "222", "file_id": "F", "ext": "jpg",
             "sites": ["1688"]}, {"telegram": {"bot_token_env": "X"}}, self.root, tg,
            date(2026, 11, 10), log=lambda m: None,
            plan_fn=lambda *a: (validate.photo_plan(live_plan()), {}),
            read_photo=lambda *a: (live, {}), rates_get=lambda r, d: RATES,
            download=write_jpeg)
        rich = tg.sent[-1][2]
        self.assertIn("🏆", rich)
        self.assertIn("1688", rich)
        ranked = search.load_last(self.root, "222")["sites"][0]["ranked"]
        self.assertEqual(len(ranked), 4)
        self.assertTrue(all(p["total_amd"] for p in ranked))
        self.assertFalse(any(p["weight_assumed"] for p in ranked))   # weights read from the pages

    def test_photo_kept_when_configured(self):
        self.set_keep(30)
        self.run_job(TG())
        self.assertTrue(os.path.exists(self.photo_path))

    def test_1688_photo_failure_falls_back_to_words(self):
        tg = TG()
        self.run_job(tg, photo_status="error")
        self.assertIn(("1688", "绿联 65W氮化镓充电器 旅行套装"), self.read_calls)
        self.assertIn("photo search failed (upload refused)", tg.sent[-1][2])

    def test_not_a_product(self):
        tg = TG()
        r = self.run_job(tg, plan={"is_product": False, "seen": "a sunset over the sea"})
        self.assertEqual(r, "not_product")
        self.assertIn("a sunset over the sea", tg.sent[-1][2])
        self.assertEqual(os.listdir(photo.photos_dir(self.root)), [])
        self.assertIsNone(search.load_last(self.root, "222"))

    def test_download_failure(self):
        tg = TG()
        j = {"job": "ab12cd34", "kind": "photo", "chat_id": "222", "file_id": "F", "ext": "jpg"}

        def bad(tok, fid, dest):
            raise ValueError("Telegram did not give the photo")
        r = search.run_photo(j, {"telegram": {"bot_token_env": "X"}}, self.root, tg,
                             date(2026, 11, 10), log=lambda m: None, download=bad)
        self.assertEqual(r, "photo_failed")
        self.assertIn("could not get the photo", tg.sent[-1][2])

    def test_rerun_with_deleted_photo(self):
        tg = TG()
        r = search.run_photo({"job": "cd34ab12", "kind": "photo", "chat_id": "222",
                              "photo_of": "ab12cd34"}, {}, self.root, tg, date(2026, 11, 10),
                             log=lambda m: None)
        self.assertEqual(r, "photo_failed")


class BotPhoto(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "market"))
        for n in ("config_china.json", "config_miniapp.json"):
            shutil.copy(os.path.join(ROOT, n), self.root)
        shutil.copy(os.path.join(ROOT, "market", "tariffs.json"), os.path.join(self.root, "market"))
        self.patches = [mock.patch.object(queue, "start_worker", lambda root=None, **kw: None),
                        mock.patch.object(bot.telegram, "send_html",
                                          lambda cfg, text, **kw: self.sent.append((text, kw))),
                        mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111",
                                                     "TELEGRAM_CHAT_ID_2": "222"})]
        self.sent = []
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def msg(self, caption=None, uid=222):
        m = {"from": {"id": uid}, "photo": [{"file_id": "FILE", "width": 800, "height": 800,
                                             "file_size": 90000}]}
        if caption is not None:
            m["caption"] = caption
        return m

    def test_caption_command_queues_photo_job(self):
        r = bot.photo({}, self.root, self.msg("/china only pdd red"), "222")
        self.assertIn("Pinduoduo by the words in it", r)
        job = queue.pop(self.root)
        self.assertEqual((job["kind"], job["sites"], job["note"], job["file_id"], job["chat_id"]),
                         ("photo", ["pinduoduo"], "red", "FILE", "222"))
        self.assertEqual((job["user_id"], job["role"]), (222, "adult"))

    def test_owner_role(self):
        bot.photo({}, self.root, self.msg("/china", uid=111), "111")
        self.assertEqual(queue.pop(self.root)["role"], "owner")

    def test_photo_without_command_asks_once(self):
        self.assertIsNone(bot.photo({}, self.root, self.msg("for the kitchen"), "222"))
        self.assertEqual(queue.pending(self.root), [])                  # nothing searched yet
        text, kw = self.sent[-1]
        self.assertIn("Search China for the item in this photo?", text)
        (yes, no), = kw["buttons"]
        self.assertTrue(yes[1].startswith("cn:ph:") and no[1].startswith("cn:phx:"))
        r = bot.callback({}, self.root, yes[1], "222")
        self.assertIn("Searching China by your photo", r)
        job = queue.pop(self.root)
        self.assertEqual((job["kind"], job["note"], job["file_id"]), ("photo", "for the kitchen", "FILE"))
        self.assertIn("expired", bot.callback({}, self.root, yes[1], "222"))  # one tap only

    def test_no_button_and_other_chat(self):
        bot.photo({}, self.root, self.msg(), "222")
        yes, no = self.sent[-1][1]["buttons"][0]
        self.assertIn("expired", bot.callback({}, self.root, yes[1], "111"))   # not their photo
        self.assertEqual(bot.callback({}, self.root, no[1], "222"), "OK — not searching.")
        self.assertEqual(queue.pending(self.root), [])

    def test_old_question_expires(self):
        bot.photo({}, self.root, self.msg(), "222")
        yes = self.sent[-1][1]["buttons"][0][0][1]
        name = f"pending_photo_{yes.split(':')[2]}.json"
        d = search.read_json(self.root, name)
        d["saved"] -= 2 * 3600
        search.write_json(self.root, name, d)
        self.assertIn("expired", bot.callback({}, self.root, yes, "222"))

    def test_not_an_image_is_ignored(self):
        self.assertIsNone(bot.photo({}, self.root, {"document": {"file_id": "x",
                                                               "mime_type": "application/pdf"}}, "222"))
        self.assertEqual(self.sent, [])

    def test_bad_site_and_big_photo(self):
        self.assertIn("Which site?", bot.photo({}, self.root, self.msg("/china only ebay"), "222"))
        big = {"document": {"file_id": "x", "mime_type": "image/jpeg", "file_size": 11 << 20}}
        self.assertIn("larger than 10 MB", bot.photo({}, self.root, big, "222"))

    def test_viewer_may_not_search(self):
        with mock.patch.object(bot, "who", return_value={"user_id": 5, "role": "viewer"}):
            self.assertIn("not available for your role", bot.photo({}, self.root, self.msg("/china"), "222"))

    def _photo_answer(self, keep=0):
        TGx = TG()
        w = Worker()
        w.root, w.read_calls = self.root, []
        if keep:
            w.set_keep(keep)
        w.run_job(TGx)
        return w

    def test_only_button_on_photo_answer_goes_by_words_when_deleted(self):
        self._photo_answer()
        r = bot.callback({}, self.root, "cn:only:1688:ab12cd34", "222")
        self.assertIn("goes by its words", r)
        job = queue.pop(self.root)
        self.assertEqual((job["kind"], job["sites"], job["plan"]["query_cn"]),
                         ("search", ["1688"], "绿联 65W氮化镓充电器 旅行套装"))

    def test_only_button_on_photo_answer_by_photo_when_kept(self):
        self._photo_answer(keep=30)
        r = bot.callback({}, self.root, "cn:only:1688:ab12cd34", "222")
        self.assertIn("1688 by photo", r)
        job = queue.pop(self.root)
        self.assertEqual((job["kind"], job["photo_of"], job["sites"]), ("photo", "ab12cd34", ["1688"]))
        self.assertTrue(job["plan"]["is_product"])


if __name__ == "__main__":
    unittest.main()
