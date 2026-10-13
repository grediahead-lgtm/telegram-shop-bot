"""Catalog, cart and checkout as a text dialog. Pure logic (no network)."""
import csv
import datetime as dt
import os
import re
import time

FIELDS = ["created_at", "order_id", "customer", "username", "phone", "items", "total", "currency", "comment"]
MAX_QTY, MAX_CART_LINES = 20, 15


def clean(s, n=200):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def money(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


class ShopBot:
    def __init__(self, cfg, orders_csv, notify_owner=None, now=dt.datetime.now, rate_limit=30):
        self.cfg, self.csv_path, self.notify_owner, self.now = cfg, orders_csv, notify_owner, now
        self.carts, self.state, self.counter = {}, {}, 0
        self.products = {str(p["id"]): p for c in cfg["catalog"] for p in c["products"]}
        self.rate_limit, self._hits = rate_limit, {}

    def _limited(self, chat):
        t = time.monotonic()
        h = [x for x in self._hits.get(chat, []) if t - x < 60] + [t]
        self._hits[chat] = h
        return len(h) > self.rate_limit

    # ---- entry point ----
    def handle(self, chat, user, text):
        if self._limited(chat):
            return []
        T, text = self.cfg["texts"], clean(text)
        low = text.lower()
        cmd = low.split(" ")[0] if low.startswith("/") else ""
        if cmd in ("/start", "/help"):
            return [T["greeting"]]
        if cmd == "/catalog":
            return [self.catalog_text()]
        if cmd == "/cart":
            return [self.cart_text(chat)]
        if cmd == "/clear":
            self.carts.pop(chat, None)
            return [T["cart_cleared"]]
        if cmd == "/cancel":
            self.state.pop(chat, None)
            return [T["stopped"]]
        if cmd == "/add":
            return [self.add(chat, text)]
        if cmd == "/remove":
            return [self.remove(chat, text)]
        if cmd == "/checkout":
            return self.start_checkout(chat)
        st = self.state.get(chat)
        if st:
            return getattr(self, "_" + st["step"])(chat, user, st, text)
        return [T["greeting"]]

    # ---- catalog and cart ----
    def catalog_text(self):
        lines = []
        for c in self.cfg["catalog"]:
            lines.append(c["name"])
            lines += ["  %s. %s, %s %s" % (p["id"], p["name"], money(p["price"]), self.cfg["currency"]) for p in c["products"]]
        return "\n".join(lines) + "\n" + self.cfg["texts"]["how_add"]

    def add(self, chat, text):
        T = self.cfg["texts"]
        m = re.fullmatch(r"/add\s+(\S+)(?:\s+(\d{1,3}))?", text.lower())
        if not m or m.group(1) not in self.products:
            return T["unknown_product"]
        qty = int(m.group(2) or 1)
        cart = self.carts.setdefault(chat, {})
        if not 1 <= qty <= MAX_QTY:
            return T["bad_qty"].format(n=MAX_QTY)
        if m.group(1) not in cart and len(cart) >= MAX_CART_LINES:
            return T["cart_full"]
        cart[m.group(1)] = min(cart.get(m.group(1), 0) + qty, MAX_QTY)
        return T["added"].format(name=self.products[m.group(1)]["name"], qty=cart[m.group(1)])

    def remove(self, chat, text):
        m = re.fullmatch(r"/remove\s+(\S+)", text.lower())
        cart = self.carts.get(chat, {})
        if not m or m.group(1) not in cart:
            return self.cfg["texts"]["not_in_cart"]
        del cart[m.group(1)]
        return self.cfg["texts"]["removed"]

    def total(self, chat):
        return sum(self.products[i]["price"] * q for i, q in self.carts.get(chat, {}).items())

    def cart_text(self, chat):
        cart = self.carts.get(chat)
        if not cart:
            return self.cfg["texts"]["cart_empty"]
        lines = ["%s x%d = %s" % (self.products[i]["name"], q, money(self.products[i]["price"] * q)) for i, q in cart.items()]
        return "\n".join(lines) + "\n" + self.cfg["texts"]["total"].format(total=money(self.total(chat)), currency=self.cfg["currency"])

    # ---- checkout ----
    def start_checkout(self, chat):
        if not self.carts.get(chat):
            return [self.cfg["texts"]["cart_empty"]]
        self.state[chat] = {"step": "phone"}
        return [self.cfg["texts"]["ask_phone"]]

    def _phone(self, chat, user, st, text):
        digits = re.sub(r"\D", "", text)
        if not 9 <= len(digits) <= 15:
            return [self.cfg["texts"]["bad_phone"]]
        st.update(step="comment", phone=text)
        return [self.cfg["texts"]["ask_comment"]]

    def _comment(self, chat, user, st, text):
        if text.startswith("/"):
            return [self.cfg["texts"]["ask_comment"]]
        st.update(step="confirm", comment="" if text == "-" else text)
        return [self.cart_text(chat) + "\n" + self.cfg["texts"]["confirm"]]

    def _confirm(self, chat, user, st, text):
        T = self.cfg["texts"]
        if text.lower() not in ("так", "да", "yes", "y"):
            return [T["confirm"]]
        self.counter += 1
        cart = self.carts[chat]
        order = {"created_at": self.now().isoformat(timespec="seconds"),
                 "order_id": "%s-%04d" % (self.now().strftime("%Y%m%d"), self.counter),
                 "customer": clean(user.get("name"), 80), "username": clean(user.get("username"), 40), "phone": st["phone"],
                 "items": "; ".join("%s x%d" % (self.products[i]["name"], q) for i, q in cart.items()),
                 "total": money(self.total(chat)), "currency": self.cfg["currency"], "comment": st["comment"]}
        try:
            self.save(order)
        except OSError:
            return [T["save_failed"]]
        self.carts.pop(chat, None)
        self.state.pop(chat, None)
        if self.notify_owner:
            self.notify_owner(order)
        return [T["ordered"].format(order_id=order["order_id"])]

    def save(self, order):
        new = not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: ("'" + v if str(v).startswith(("=", "+", "-", "@")) else v) for k, v in order.items()})
