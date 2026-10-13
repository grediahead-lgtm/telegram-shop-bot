import csv
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from shop_bot.__main__ import load_config  # noqa: E402
from shop_bot.core import ShopBot, money  # noqa: E402

CFG = load_config(os.path.join(ROOT, "examples", "config.example.json"))
USER = {"name": "Ira K", "username": "ira"}


def bot(d, **kw):
    return ShopBot(CFG, os.path.join(d, "o.csv"), now=lambda: dt.datetime(2026, 10, 13, 10, 0), **kw)


def say(b, chat, *msgs):
    out = []
    for m in msgs:
        out += b.handle(chat, USER, m)
    return out


class CartTests(unittest.TestCase):
    def test_add_remove_total(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            say(b, 1, "/add b1 2", "/add c1")
            self.assertEqual(b.total(1), 2 * 1250 + 2340.5)
            self.assertIn("Total: 4840.5 UAH", b.handle(1, USER, "/cart")[0])
            say(b, 1, "/remove b1")
            self.assertEqual(b.total(1), 2340.5)

    def test_validation(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            self.assertEqual(say(b, 1, "/add zzz")[0], CFG["texts"]["unknown_product"])
            self.assertEqual(say(b, 1, "/add b1 0")[0], CFG["texts"]["bad_qty"].format(n=20))
            self.assertEqual(say(b, 1, "/add b1 abc")[0], CFG["texts"]["unknown_product"])
            self.assertEqual(say(b, 1, "/remove b1")[0], CFG["texts"]["not_in_cart"])

    def test_quantity_is_capped(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            for _ in range(5):
                say(b, 1, "/add b1 15")
            self.assertEqual(b.carts[1]["b1"], 20)

    def test_carts_are_separate_and_clear(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            say(b, 1, "/add b1")
            self.assertEqual(b.handle(2, USER, "/cart")[0], CFG["texts"]["cart_empty"])
            say(b, 1, "/clear")
            self.assertEqual(b.handle(1, USER, "/cart")[0], CFG["texts"]["cart_empty"])

    def test_money(self):
        self.assertEqual((money(1250.0), money(2340.5), money(0.1 + 0.2)), ("1250", "2340.5", "0.3"))


class CheckoutTests(unittest.TestCase):
    def test_full_order_saved_and_owner_notified(self):
        with tempfile.TemporaryDirectory() as d:
            seen = []
            b = bot(d, notify_owner=seen.append)
            out = say(b, 1, "/add b1 2", "/checkout", "+380501112233", "Kyiv, Novapost 5", "yes")
            self.assertIn("Order 20261013-0001", out[-1])
            with open(os.path.join(d, "o.csv"), encoding="utf-8") as f:
                row = list(csv.DictReader(f))[0]
            self.assertEqual((row["items"], row["total"], row["comment"]), ("Bed Comfort 40x30 x2", "2500", "Kyiv, Novapost 5"))
            self.assertEqual(seen[0]["phone"], "+380501112233")
            self.assertEqual(b.carts.get(1), None)

    def test_empty_cart_cannot_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(say(bot(d), 1, "/checkout"), [CFG["texts"]["cart_empty"]])

    def test_bad_phone_keeps_step_and_confirm_needs_yes(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            say(b, 1, "/add b1", "/checkout")
            self.assertEqual(say(b, 1, "123")[0], CFG["texts"]["bad_phone"])
            say(b, 1, "380501112233", "-")
            self.assertEqual(say(b, 1, "maybe")[0], CFG["texts"]["confirm"])
            self.assertFalse(os.path.exists(os.path.join(d, "o.csv")))

    def test_cancel_keeps_cart(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            say(b, 1, "/add b1", "/checkout", "/cancel")
            self.assertEqual(b.carts[1], {"b1": 1})
            self.assertNotIn(1, b.state)

    def test_save_failure_keeps_the_cart(self):
        with tempfile.TemporaryDirectory() as d:
            b = ShopBot(CFG, os.path.join(d, "missing-dir", "o.csv"))
            out = say(b, 1, "/add b1", "/checkout", "380501112233", "-", "yes")
            self.assertEqual(out[-1], CFG["texts"]["save_failed"])
            self.assertEqual(b.carts[1], {"b1": 1})

    def test_formula_guard(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d)
            say(b, 1, "/add b1", "/checkout", "380501112233", "=SUM(A1)", "yes")
            with open(os.path.join(d, "o.csv"), encoding="utf-8") as f:
                self.assertTrue(list(csv.DictReader(f))[0]["comment"].startswith("'="))

    def test_rate_limit(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot(d, rate_limit=2)
            self.assertEqual([len(b.handle(1, USER, "/help")) for _ in range(4)], [1, 1, 0, 0])


class ConfigTests(unittest.TestCase):
    def test_duplicate_ids_and_prices(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(ROOT, "examples", "config.example.json"), encoding="utf-8") as f:
                good = json.load(f)
            dup = json.loads(json.dumps(good))
            dup["catalog"][1]["products"][0]["id"] = "b1"
            free = json.loads(json.dumps(good))
            free["catalog"][0]["products"][0]["price"] = 0
            for name, cfg in (("dup", dup), ("free", free)):
                p = os.path.join(d, name + ".json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f)
                with self.assertRaises(ValueError, msg=name):
                    load_config(p)


if __name__ == "__main__":
    unittest.main()
