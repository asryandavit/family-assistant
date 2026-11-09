"""china/trust.py: every part of the trust score, hand-checked; the contract's new fields."""
import json
import os
import unittest

from china import parse, trust, validate

F = os.path.join(os.path.dirname(__file__), "fixtures", "china")


def p(**kw):
    d = {"seller": parse.UNMARKED, "marks": [], "badges": [], "specs": {}, "sales": None,
         "reviews": None, "rating_text": None, "complaint_types": [], "spec_mismatch": False,
         "suspicious": False, "reviews_read": False}
    d.update(kw)
    return d


def parts(x, category="other"):
    return dict(trust.score(x, category)[1])


class Parts(unittest.TestCase):
    def test_seller_points(self):
        self.assertEqual(trust.score(p(seller=parse.OFFICIAL))[0], 40)
        self.assertEqual(trust.score(p(seller=parse.AUTHORISED))[0], 35)
        self.assertEqual(trust.score(p(seller=parse.FLAGSHIP))[0], 25)
        self.assertEqual(trust.score(p(seller=parse.FACTORY))[0], 10)
        self.assertEqual(trust.score(p())[0], 0)

    def test_guarantee_once(self):
        x = p(marks=["正品险", "假一赔十"])
        self.assertEqual(trust.score(x)[0], 5)
        self.assertEqual(trust.score(p(marks=["Four times compensation for fakes"]))[0], 5)

    def test_store_age_capped(self):
        self.assertEqual(trust.store_years(["8年老店"], []), 8)
        self.assertEqual(trust.store_years([], ["入驻5年"]), 5)
        self.assertEqual(parts(p(marks=["8年老店"]))["store 8 yr"], 5)
        self.assertEqual(parts(p(badges=["入驻3年"]))["store 3 yr"], 3)

    def test_sales_and_reviews_log_scale(self):
        self.assertEqual(parts(p(sales=10000))["1.0万 sold"], 12.0)          # 3 × 4
        self.assertEqual(parts(p(sales=5230000))["523万 sold"], 15.0)        # capped
        self.assertEqual(parts(p(reviews=2321))["2,321 reviews"], 8.4)      # 2.5 × 3.366
        self.assertNotIn("5 sold", parts(p(sales=5)))                        # under 10: nothing

    def test_rating(self):
        self.assertEqual(trust.rating("好评率98%"), 0.98)
        self.assertEqual(trust.rating("4.8分"), 0.96)
        self.assertEqual(trust.rating("5.0"), 1.0)
        self.assertIsNone(trust.rating("很好"))
        self.assertEqual(parts(p(reviews=100, rating_text="好评率100%"))["100% positive"], 10.0)
        self.assertEqual(parts(p(reviews=100, rating_text="好评率90%"))["90% positive"], 0.0)
        self.assertEqual(parts(p(reviews=100, rating_text="好评率80%"))["80% positive"], -10.0)
        self.assertEqual(parts(p(reviews=100, rating_text="好评率50%"))["50% positive"], -20.0)
        self.assertNotIn("100% positive", parts(p(reviews=5, rating_text="5.0")))  # too few

    def test_complaints(self):
        x = p(complaint_types=["fake", "poor_quality", "slow_shipping"])
        self.assertEqual(trust.score(x)[0], -12 - 6 - 2)

    def test_certified_only_where_it_matters(self):
        x = p(specs={"3C认证证书编号": "2025010907813585"})
        self.assertEqual(trust.score(x, "electronics")[0], 5)
        self.assertEqual(trust.score(x, "clothes")[0], 0)
        self.assertEqual(trust.score(p(specs={"产品认证": "CE认证"}), "electronics")[0], 5)
        self.assertEqual(trust.score(p(specs={"产品认证": "无"}), "electronics")[0], 0)

    def test_spec_mismatch_and_suspicious(self):
        self.assertEqual(trust.score(p(spec_mismatch=True))[0], -15)
        self.assertEqual(trust.score(p(seller=parse.OFFICIAL, suspicious=True))[0], -60)

    def test_reason_words(self):
        x = p(seller=parse.OFFICIAL, reviews=2321, rating_text="98%", reviews_read=True,
              complaint_types=["slow_shipping"])
        x["trust"], x["trust_parts"] = trust.score(x)
        r = trust.reason(x)
        self.assertTrue(r.startswith("official flagship, 2,321 reviews, 98% positive"))
        self.assertIn("but complaints: slow shipping", r)


class Contract(unittest.TestCase):
    def good(self):
        with open(os.path.join(F, "answer_pinduoduo_contract.json"), encoding="utf-8") as f:
            d = json.load(f)
        d.pop("_source")
        return d

    def test_new_fields_accepted(self):
        d = self.good()
        d["results"][0].update(rating_text="好评率98%", complaint_types=["fake", "fake", "broken"],
                               spec_mismatch=True)
        r = validate.answer(d, "pinduoduo")["results"][0]
        self.assertEqual(r["complaint_types"], ["fake", "broken"])
        self.assertTrue(r["spec_mismatch"])
        self.assertEqual(r["rating_text"], "好评率98%")

    def test_old_answers_still_valid(self):
        r = validate.answer(self.good(), "pinduoduo")["results"][0]
        self.assertEqual((r["complaint_types"], r["spec_mismatch"], r["rating_text"]), ([], False, None))

    def test_complaint_outside_allow_list_rejected(self):
        d = self.good()
        d["results"][0]["complaint_types"] = ["smells bad"]
        with self.assertRaises(ValueError):
            validate.answer(d, "pinduoduo")

    def test_spec_mismatch_must_be_bool(self):
        d = self.good()
        d["results"][0]["spec_mismatch"] = "yes"
        with self.assertRaises(ValueError):
            validate.answer(d, "pinduoduo")


BRANDS = {"electronics": {"trusted": [["绿联", "Ugreen"], ["苹果", "Apple"], ["安克", "Anker"]],
                          "lookalike": [["UE"]]}}


class Brands(unittest.TestCase):
    def b(self, **kw):
        return dict(trust.score(p(**kw), "electronics", BRANDS)[1])

    def test_brand_from_title_start_spec_or_brand_store(self):
        self.assertEqual(self.b(title_cn="绿联65W氮化镓充电器")["known brand Ugreen"], 10)
        self.assertEqual(self.b(title_en="UGREEN Nexode 65W")["known brand Ugreen"], 10)
        self.assertIn("known brand Anker", self.b(specs={"品牌": "Anker/安克"}))
        self.assertIn("known brand Ugreen", self.b(shop_name="绿联赛文斯专卖店"))
        self.assertIn("known brand Ugreen", self.b(title_cn="【官方正品】绿联充电器"))

    def test_fits_apple_is_not_apple(self):
        self.assertEqual(self.b(title_cn="跨境65W氮化镓充电器适用苹果华为"),
                         {"unmarked seller": 0})
        self.assertNotIn("known brand Apple", self.b(shop_name="苹果配件店"))   # not a brand store

    def test_lookalike(self):
        x = self.b(title_cn="UE100W氮化镓充电器65W快充")                       # live, 2026-11-09
        self.assertEqual(x["look-alike brand UE"], -30)
        self.assertNotIn("look-alike brand UE", self.b(title_en="UEFA licensed charger"))

    def test_lists_are_per_category(self):
        self.assertEqual(trust.score(p(title_cn="绿联充电器"), "home", BRANDS)[0], 0)

    def test_config_lists_are_well_formed(self):
        with open(os.path.join(os.path.dirname(F), "..", "..", "config_china.json"), encoding="utf-8") as f:
            brands = json.load(f)["brands"]
        for cat, lists in brands.items():
            self.assertIn(cat, validate.CATEGORIES)
            for kind in ("trusted", "lookalike"):
                for spellings in lists[kind]:
                    self.assertTrue(spellings and all(isinstance(x, str) and x for x in spellings))


class VariantAndPhotos(unittest.TestCase):
    def test_variant(self):
        self.assertEqual(parts(p(reviews_read=True, review_variant="matching"))
                         ["reviews are of this variant"], 3)
        self.assertEqual(parts(p(reviews_read=True, review_variant="other"))
                         ["reviews are of other variants"], -5)
        self.assertEqual(trust.score(p(reviews_read=True, review_variant="mixed"))[0], 0)
        self.assertEqual(trust.score(p(reviews_read=False, review_variant="matching"))[0], 0)

    def test_photos(self):
        self.assertEqual(parts(p(photo_reviews=166))["166 photo reviews"], 4.4)   # 2 × 2.22
        self.assertEqual(parts(p(photo_reviews=5000))["5,000 photo reviews"], 6.0)
        self.assertEqual(trust.score(p(photo_reviews=2))[0], 0)

    def test_contract(self):
        d = Contract().good()
        d["results"][0].update(photo_review_count_text="图/视频(166)", review_variant="matching")
        r = validate.answer(d, "pinduoduo")["results"][0]
        self.assertEqual((r["photo_review_count_text"], r["review_variant"]), ("图/视频(166)", "matching"))
        self.assertEqual(parse.count(r["photo_review_count_text"]), 166)
        d["results"][0]["review_variant"] = "most"
        with self.assertRaises(ValueError):
            validate.answer(d, "pinduoduo")


if __name__ == "__main__":
    unittest.main()
