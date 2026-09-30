# Connecting Augur: The Easy Guide 🧩

Hi Ziko! Augur is a robot that practices trading. To see prices and make pretend
trades, it needs to talk to some websites. Connecting a website is called an
**integration**. Each one takes about two minutes.

> 🛡️ **Augur uses practice money.** Nothing you do here can spend real money.
> Only a grown-up can switch that off, on purpose, by editing a file.

---

## What you need

- A grown-up to help you make the accounts (some websites need an email address).
- Augur running on the computer. If it isn't, ask a grown-up to type:
  `python src/dashboard_api.py`, then open the dashboard.

---

## The magic three steps

Every connection works the same way:

1. **Open the website** and make a free account.
2. **Copy the keys.** A key is a long secret password made of letters and numbers.
3. **Paste the keys** into Augur and press **Test**.

When it works you'll see a green **Connected** badge. 🎉

---

## Where to click in Augur

1. Open the dashboard in the web browser.
2. Click **Integrations** on the left side (the plug icon 🔌).
3. Click the card that says **Start here**. That's **Alpaca**.
4. Follow the numbered steps on the card.

---

## Your first one: Alpaca 📈

Alpaca lets Augur practice buying and selling stocks, gold, and oil.

1. Click **1. Open Alpaca** on the card and sign up (ask your grown-up).
2. In Alpaca, make sure the top-left menu says **Paper Trading**. Paper means pretend.
3. Click **Generate New Keys** on the right side.
4. You get two keys: a **Key ID** and a **Secret Key**.
   - The Secret Key is shown **only once**, so copy it right away.
5. Back in Augur, paste the **Key ID** into the first box and the **Secret Key** into the second box.
6. Press **2. Save keys**. Augur tests them by itself.

✅ If you see *"Connected! Account has $100,000.00 (practice money)"*, you did it!

---

## More connections (all optional)

| Card | What it does | Keys |
|---|---|---|
| 🪙 Binance Testnet | Practice crypto trading, like Bitcoin | 2 |
| 🏦 FRED | Economy numbers. This helps Augur understand **gold** | 1 |
| 📰 NewsAPI | News headlines | 1 |
| 🚨 CryptoPanic | Crypto news | 1 |
| 📊 Polygon | Stock price history | 1 |
| 🦎 CoinGecko | Crypto prices | 1 |
| 🔗 Glassnode | How coins move between wallets | 1 |

**Tip:** do **FRED** next. It's free, it's easy, and it makes the gold card on the
**Markets** page smarter.

---

## Something went wrong? 🔧

| What you see | What to do |
|---|---|
| *"Alpaca said no"* | A key was copied wrong. Copy it again. Make sure you got the whole thing. |
| *"Keys can't contain spaces"* | You copied an extra space. Paste it again carefully. |
| *"Can't reach Augur"* | Augur isn't running. Ask your grown-up to start it. |
| The Secret Key disappeared | That's normal. Make new keys in Alpaca and use those. |

---

## Keep your keys secret 🤫

- Keys are like passwords. **Never** send them in a chat, email, or screenshot.
- Augur keeps them only on this computer, in a file called `.env`.
- If you think someone saw your keys, make new ones on the website. The old ones stop working.

---

## Prefer typing? ⌨️

A grown-up can run the same setup in the terminal:

```
python scripts/setup_integrations.py
```

It shows a list. Type a number, follow the steps, and paste the keys. You won't
see the keys while you type them, which is on purpose.
