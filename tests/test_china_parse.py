"""china/parse.py on strings captured in P0 (tests/fixtures/china/)."""
import json
import os
import unittest

from china import parse

F = os.path.join(os.path.dirname(__file__), "fixtures", "china")


def load(name):
    with open(os.path.join(F, name), encoding="utf-8") as f:
        return json.load(f)


class Prices(unittest.TestCase):
    def test_shown_forms(self):
        self.assertEqual(parse.cny("券后¥189"), 189.0)
        self.assertEqual(parse.cny("券前¥229"), 229.0)
        self.assertEqual(parse.cny("￥109.34"), 109.34)
        self.assertEqual(parse.cny("首件¥89.9"), 89.9)
        self.assertEqual(parse.cny("¥|109|.34"), 109.34)       # Taobao card split
        self.assertEqual(parse.cny("109"), 109.0)               # PDD priceInfo
        self.assertEqual(parse.cny("限时价 ¥159"), 159.0)

    def test_rejects(self):
        for bad in (None, "", "价格", "¥0", "¥", "about 100", "¥2000000"):
            self.assertIsNone(parse.cny(bad), bad)

    def test_money_currency(self):
        self.assertEqual(parse.money("$12.50"), (12.5, "USD"))
        self.assertEqual(parse.money("US$ 3.9"), (3.9, "USD"))
        self.assertEqual(parse.money("¥4.0"), (4.0, "CNY"))
        self.assertEqual(parse.money(None), (None, None))
        self.assertEqual(parse.money("n/a"), (None, None))

    def test_every_pdd_listing_parses(self):
        for row in load("pdd_search_gan65w.json")["rows"]:
            v = parse.cny(row[3])
            self.assertIsNotNone(v, row)
            self.assertLessEqual(v, row[2] / 100.0, row)       # after coupon <= list (fen)

    def test_every_taobao_card_price_parses(self):
        for _id, _host, card in load("taobao_search_gan65w.json")["rows"]:
            self.assertIsNotNone(parse.cny(card), card)

    def test_pdd_variant_prices(self):
        skus = {s["name"]: s for s in load("pdd_goods_796316919192.json")["skus"]}
        s = skus["100W伸缩线充电器【四口快充】"]
        self.assertEqual((parse.cny(s["after_coupon"]), parse.cny(s["before_coupon"])), (189.0, 229.0))


class Promo(unittest.TestCase):
    def test_marks(self):
        self.assertEqual(parse.promo("新人价CN¥3.90起"), "new-buyer price")   # live run 2026-11-09
        self.assertEqual(parse.promo("首件¥89.9"), "first-item price")
        self.assertEqual(parse.promo("$6.03 ~ $6.78"), "price range")
        self.assertEqual(parse.promo("¥14.5起"), "'from' price")
        self.assertEqual(parse.promo("券后¥189"), "")
        self.assertEqual(parse.promo(None), "")


class Counts(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse.count("全店总售523万+"), 5230000)
        self.assertEqual(parse.count("本店已拼1.2万"), 12000)
        self.assertEqual(parse.count("已拼467件"), 467)
        self.assertEqual(parse.count("5000+人付款"), 5000)
        self.assertEqual(parse.count("全部(2321)"), 2321)
        self.assertEqual(parse.count("商品评价(2,321)"), 2321)
        self.assertEqual(parse.count("3千+数码3c爱好者看过"), 3000)
        self.assertIsNone(parse.count("none"))
        self.assertIsNone(parse.count(None))


class Weights(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse.weight_kg("100g"), 0.1)
        self.assertEqual(parse.weight_kg("重量100g"), 0.1)
        self.assertEqual(parse.weight_kg("0.5kg"), 0.5)
        self.assertEqual(parse.weight_kg("1.2公斤"), 1.2)
        self.assertEqual(parse.weight_kg("500克"), 0.5)
        self.assertEqual(parse.weight_kg("180", unit_if_bare="g"), 0.18)

    def test_rejects(self):
        self.assertIsNone(parse.weight_kg("180"))              # bare, unit unknown
        self.assertIsNone(parse.weight_kg("65W"))
        self.assertIsNone(parse.weight_kg("0g"))
        self.assertIsNone(parse.weight_kg("500kg"))
        self.assertIsNone(parse.weight_kg(None))

    def test_1688_mm_labelled_cm(self):
        row = load("1688_offer_735345997702.json")["weight_table_rows"][0].split("\t")
        dims, note = parse.dims_cm(row[2], row[3], row[4], weight_g=float(row[6]))
        self.assertEqual(dims, (6.75, 3.38, 8.65))
        self.assertIn("mm", note)

    def test_plausible_cm_kept(self):
        self.assertEqual(parse.dims_cm(4.76, 3.85, 9.12, weight_g=72), ((4.76, 3.85, 9.12), ""))
        self.assertEqual(parse.dims_cm(10, 5, 2, weight_g=100), ((10.0, 5.0, 2.0), ""))

    def test_dims_rejects(self):
        self.assertEqual(parse.dims_cm("x", 1, 1)[0], None)
        self.assertEqual(parse.dims_cm(0, 1, 1)[0], None)
        self.assertEqual(parse.dims_cm(1, 1, 1, weight_g=50000)[0], None)  # 50 kg in 1 cm³
        self.assertEqual(parse.dims_cm(300, 10, 10)[0], None)


class Sellers(unittest.TestCase):
    def test_lookalike_flagships(self):
        self.assertEqual(parse.seller_class("品胜官方旗舰店")[0], parse.OFFICIAL)
        self.assertEqual(parse.seller_class("品胜快充旗舰店")[0], parse.FLAGSHIP)

    def test_other_classes(self):
        self.assertEqual(parse.seller_class("绿联UGREEN赛文斯专卖店", ["品牌正品"])[0], parse.AUTHORISED)
        self.assertEqual(parse.seller_class("某店", ["绿联·品牌授权"])[0], parse.AUTHORISED)
        self.assertEqual(parse.seller_class("联想惠泽专营店")[0], parse.RESELLER)
        self.assertEqual(parse.seller_class("华北绿联品牌直销店")[0], parse.RESELLER)
        self.assertEqual(parse.seller_class("天天特卖工厂")[0], parse.FACTORY)
        self.assertEqual(parse.seller_class("深圳市同长盛电子有限公司", [], ["Factory direct supply"])[0],
                         parse.FACTORY)
        self.assertEqual(parse.seller_class("", [])[0], parse.UNMARKED)

    def test_factory_never_official_by_brand_word(self):
        # a factory selling a brand name is not official unless marked
        self.assertEqual(parse.seller_class("绿联配件工厂")[0], parse.FACTORY)


class Restrictions(unittest.TestCase):
    def test_flags(self):
        self.assertEqual(parse.restrictions("倍魔自带伸缩线充电器65W无线磁吸快充"), ["magnet"])
        self.assertEqual(parse.restrictions("20000mAh充电宝"), ["battery"])
        self.assertEqual(parse.restrictions("绿联65W氮化镓充电器"), [])


class Links(unittest.TestCase):
    def test_built_from_ids(self):
        self.assertEqual(parse.link("pinduoduo", "796316919192"),
                         "https://mobile.yangkeduo.com/goods.html?goods_id=796316919192")
        self.assertEqual(parse.link("1688", 735345997702),
                         "https://detail.1688.com/offer/735345997702.html")
        self.assertIsNone(parse.link("taobao", "12ab"))
        self.assertIsNone(parse.link("taobao", "javascript:alert(1)"))
        self.assertIn("%E6%B0%AE", parse.search_link("taobao", "氮化镓"))


if __name__ == "__main__":
    unittest.main()
