# telegram-shop-bot

A small Telegram shop **without payments**: the customer browses a catalog, builds a cart, leaves a phone number and a comment, confirms, and the order is saved to a CSV file and sent to the owner. Payment and delivery are arranged by a person afterwards. Python standard library only.

## What it does
- Commands: `/catalog`, `/add ID [qty]`, `/remove ID`, `/cart`, `/clear`, `/checkout`, `/cancel`, `/help`. Plain text, numbered by product ID.
- The catalog (categories, products, prices, currency) and **all texts** are in one JSON config; the config is validated at start (unique product IDs, positive prices, every text present).
- Cart limits: 1 to 20 pieces per product, up to 15 lines. Totals are computed from the catalog prices, never from anything the customer types.
- Checkout asks for a phone (9 to 15 digits) and a comment, shows the cart and needs an explicit "yes". If saving fails the cart is kept. `/cancel` stops checkout but keeps the cart.
- Each order gets an ID like `20261013-0001`, a row in `orders.csv` (cells starting with `=`, `+`, `-`, `@` get a leading `'`) and, if `owner_chat_id` is set, a Telegram message to the owner.
- Private chats only, rate limit per chat, token from `TELEGRAM_BOT_TOKEN` only.

## Quick start
```bash
cp examples/config.example.json config.json      # your products, prices and texts
PYTHONPATH=src python3 -m shop_bot --config config.json --check
TELEGRAM_BOT_TOKEN=123456:your-token PYTHONPATH=src python3 -m shop_bot --config config.json
```
Tests: `python3 -m unittest discover -s tests` (no internet, no real token).

## Limits (read this)
- **No payments, no stock levels, no delivery calculation, no product photos.** It takes orders; a person confirms them. Prices live in the config: when a price changes, edit the config and restart.
- Carts and dialogs are in memory (a restart empties them); saved orders are in the CSV.
- Order numbers continue after a restart (the day's last number is read from `orders.csv`); if you delete or move the CSV, numbering starts again from 1.
- The Telegram calls are covered by tests with the conversation logic only, not by a test against Telegram itself.

MIT license.

---

# telegram-shop-bot (українською)

Невеликий Telegram-магазин **без оплат**: покупець дивиться каталог, збирає кошик, залишає телефон і коментар, підтверджує — замовлення записується в CSV і надсилається власнику. Оплату й доставку узгоджує людина. Лише стандартна бібліотека Python.

**Запуск:** `cp examples/config.example.json config.json`, `--check`, потім із `TELEGRAM_BOT_TOKEN`. Каталог і всі тексти — в одному JSON.

**Важливо:** без оплат, залишків, доставки й фото; кошики зберігаються в пам'яті; номери замовлень продовжуються після перезапуску за файлом `orders.csv`.
