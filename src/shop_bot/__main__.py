import argparse
import json
import os
import sys
import time

from .core import ShopBot
from .telegram_api import TelegramClient

NEED = ["greeting", "how_add", "unknown_product", "bad_qty", "cart_full", "added", "removed", "not_in_cart", "cart_empty",
        "cart_cleared", "total", "ask_phone", "bad_phone", "ask_comment", "confirm", "ordered", "save_failed", "stopped"]


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    miss = [k for k in NEED if not cfg.get("texts", {}).get(k)]
    if miss:
        raise ValueError("config.texts is missing: " + ", ".join(miss))
    ids = [str(p["id"]) for c in cfg["catalog"] for p in c["products"]]
    if len(ids) != len(set(ids)):
        raise ValueError("product ids must be unique")
    for c in cfg["catalog"]:
        for p in c["products"]:
            if not isinstance(p["price"], (int, float)) or p["price"] <= 0:
                raise ValueError("product %s has no positive price" % p["id"])
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shop_bot")
    ap.add_argument("--config", required=True)
    ap.add_argument("--orders", default="orders.csv")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.check:
        print("config ok, products:", sum(len(c["products"]) for c in cfg["catalog"]))
        return 0
    client = TelegramClient(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    owner = cfg.get("owner_chat_id")
    notify = (lambda o: client.send(owner, "New order %s: %s | total %s %s | %s %s" % (o["order_id"], o["items"], o["total"], o["currency"], o["customer"], o["phone"]))) if owner else None
    bot, offset = ShopBot(cfg, args.orders, notify), 0
    while True:
        try:
            for upd in client.updates(offset):
                offset = upd["update_id"] + 1
                m = upd.get("message") or {}
                u = m.get("from", {})
                if m.get("chat", {}).get("type") != "private" or u.get("is_bot") or not m.get("text"):
                    continue
                user = {"name": " ".join(filter(None, [u.get("first_name"), u.get("last_name")])), "username": u.get("username", "")}
                for r in bot.handle(m["chat"]["id"], user, m["text"]):
                    client.send(m["chat"]["id"], r)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print("error:", type(e).__name__, file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
