import os
import json
import asyncio
from datetime import datetime, date
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import anthropic

# ── CONFIG ──────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY_HERE")

# ── DATA STORE (in-memory, per user) ────────────────────────────────
# Structure: user_data[user_id] = { expenses: [...], budget: 10000 }
user_data = defaultdict(lambda: {"expenses": [], "budget": 10000})

CATEGORIES = {
    "food":          ("🍛", "খাবার"),
    "transport":     ("🚌", "যাতায়াত"),
    "shopping":      ("🛍️", "শপিং"),
    "health":        ("💊", "স্বাস্থ্য"),
    "education":     ("📚", "পড়াশোনা"),
    "bills":         ("💡", "বিল"),
    "entertainment": ("🎮", "বিনোদন"),
    "other":         ("📦", "অন্যান্য"),
}

MONTHS_BN = ["জানুয়ারি","ফেব্রুয়ারি","মার্চ","এপ্রিল","মে","জুন",
             "জুলাই","আগস্ট","সেপ্টেম্বর","অক্টোবর","নভেম্বর","ডিসেম্বর"]

def fmt(n):
    return f"৳{int(n):,}"

def today_str():
    return date.today().isoformat()

def get_expenses(uid):
    return user_data[uid]["expenses"]

def get_budget(uid):
    return user_data[uid]["budget"]

def month_expenses(uid, year=None, month=None):
    now = date.today()
    y = year or now.year
    m = month or now.month
    return [e for e in get_expenses(uid)
            if e["date"].startswith(f"{y}-{m:02d}")]

def detect_category(text):
    keywords = {
        "food":          ["খাবার","ভাত","রুটি","বিরিয়ানি","নাস্তা","চা","কফি","রেস্টুরেন্ট","দুপুর","রাতের","সকাল","মাছ","মাংস","সবজি"],
        "transport":     ["রিকশা","বাস","ট্রেন","উবার","পাঠাও","ভাড়া","যাতায়াত","সিএনজি","অটো"],
        "shopping":      ["কিনলাম","কিনেছি","বাজার","মুদি","কাপড়","জামা","শপিং","দোকান"],
        "health":        ["ডাক্তার","ওষুধ","হাসপাতাল","ক্লিনিক","ফার্মেসি","চিকিৎসা"],
        "education":     ["বই","পড়াশোনা","কোর্স","ক্লাস","টিউশন","স্কুল","কলেজ"],
        "bills":         ["বিল","ইন্টারনেট","বিদ্যুৎ","গ্যাস","পানি","মোবাইল","রিচার্জ"],
        "entertainment": ["সিনেমা","গেম","নেটফ্লিক্স","ইউটিউব","বিনোদন","ঘুরতে"],
    }
    text_lower = text.lower()
    for cat, words in keywords.items():
        if any(w in text_lower for w in words):
            return cat
    return "other"

# ── KEYBOARDS ────────────────────────────────────────────────────────
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ খরচ যোগ করুন", callback_data="help_add")],
        [InlineKeyboardButton("📅 আজকের খরচ", callback_data="today"),
         InlineKeyboardButton("📊 মাসিক রিপোর্ট", callback_data="report")],
        [InlineKeyboardButton("🤖 AI পরামর্শ", callback_data="ai"),
         InlineKeyboardButton("💰 বাজেট সেট", callback_data="set_budget")],
        [InlineKeyboardButton("🗑️ শেষ খরচ মুছুন", callback_data="delete_last")],
    ])

def category_keyboard(amount, desc):
    rows = []
    items = list(CATEGORIES.items())
    for i in range(0, len(items), 2):
        row = []
        for cat_id, (icon, label) in items[i:i+2]:
            row.append(InlineKeyboardButton(
                f"{icon} {label}",
                callback_data=f"cat|{cat_id}|{amount}|{desc}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ বাতিল", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

# ── HANDLERS ─────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    text = (
        f"আস্সালামু আলাইকুম {name}! 👋\n\n"
        "💸 *টাকার হিসাব Bot* এ স্বাগতম!\n\n"
        "📝 *খরচ যোগ করতে লিখুন:*\n"
        "`১২০ দুপুরের ভাত`\n"
        "`৫০ রিকশা ভাড়া`\n"
        "`৩৫০ মুদিখানা`\n\n"
        "অথবা নিচের বাটন ব্যবহার করুন 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *কমান্ড লিস্ট:*\n\n"
        "✏️ *খরচ যোগ:*\n"
        "`১২০ দুপুরের ভাত`\n"
        "`৫০০ ইন্টারনেট বিল`\n\n"
        "📊 *রিপোর্ট দেখতে:*\n"
        "`/report` — এই মাসের রিপোর্ট\n"
        "`/today` — আজকের খরচ\n\n"
        "⚙️ *অন্যান্য:*\n"
        "`/budget 10000` — বাজেট সেট করুন\n"
        "`/ai` — AI পরামর্শ\n"
        "`/delete` — শেষ খরচ মুছুন\n"
        "`/list` — সব খরচ দেখুন\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Check if waiting for budget input
    if ctx.user_data.get("waiting_budget"):
        try:
            amount = float(text.replace(",", "").replace("৳", ""))
            user_data[uid]["budget"] = amount
            ctx.user_data["waiting_budget"] = False
            await update.message.reply_text(
                f"✅ বাজেট সেট হয়েছে: *{fmt(amount)}*",
                parse_mode="Markdown", reply_markup=main_keyboard()
            )
        except:
            await update.message.reply_text("❌ সংখ্যা লিখুন, যেমন: `10000`", parse_mode="Markdown")
        return

    # Parse "amount description" format
    parts = text.split(maxsplit=1)
    if len(parts) >= 1:
        # Try to parse first word as number
        num_str = parts[0].replace(",", "").replace("৳", "")
        try:
            amount = float(num_str)
            desc = parts[1] if len(parts) > 1 else "অন্যান্য"
            auto_cat = detect_category(desc)
            cat_icon, cat_label = CATEGORIES[auto_cat]

            # Ask to confirm category
            msg = (
                f"💸 *{fmt(amount)}* — {desc}\n\n"
                f"ক্যাটাগরি: {cat_icon} {cat_label} (অটো ডিটেক্ট)\n\n"
                "সঠিক ক্যাটাগরি বেছে নিন 👇"
            )
            await update.message.reply_text(
                msg, parse_mode="Markdown",
                reply_markup=category_keyboard(amount, desc)
            )
            return
        except ValueError:
            pass

    # Keyword shortcuts
    low = text.lower()
    if any(w in low for w in ["রিপোর্ট", "report", "/report"]):
        await send_report(update, uid)
    elif any(w in low for w in ["আজ", "today", "/today"]):
        await send_today(update, uid)
    elif any(w in low for w in ["ai", "পরামর্শ", "/ai"]):
        await send_ai(update, uid)
    else:
        await update.message.reply_text(
            "💡 খরচ লিখুন এভাবে:\n`১২০ দুপুরের ভাত`\n`৫০ রিকশা`",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data == "cancel":
        await query.edit_message_text("❌ বাতিল করা হয়েছে।", reply_markup=main_keyboard())

    elif data == "help_add":
        await query.edit_message_text(
            "✏️ *খরচ যোগ করুন:*\n\nএভাবে লিখুন:\n`১২০ দুপুরের ভাত`\n`৫০ রিকশা ভাড়া`\n`৩৫০ মুদিখানা`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 ফিরে যান", callback_data="back")
            ]])
        )

    elif data == "back":
        await query.edit_message_text("মূল মেনু 👇", reply_markup=main_keyboard())

    elif data == "today":
        await send_today(query, uid, edit=True)

    elif data == "report":
        await send_report(query, uid, edit=True)

    elif data == "ai":
        await query.edit_message_text("🤖 AI বিশ্লেষণ করছে...", parse_mode="Markdown")
        await send_ai(query, uid, edit=True)

    elif data == "set_budget":
        ctx.user_data["waiting_budget"] = True
        await query.edit_message_text(
            "💰 নতুন মাসিক বাজেট লিখুন:\nযেমন: `10000`",
            parse_mode="Markdown"
        )

    elif data == "delete_last":
        exps = get_expenses(uid)
        if not exps:
            await query.edit_message_text("❌ কোনো খরচ নেই।", reply_markup=main_keyboard())
        else:
            last = exps[-1]
            cat_icon, cat_label = CATEGORIES[last["category"]]
            await query.edit_message_text(
                f"🗑️ এই খরচটি মুছবেন?\n\n"
                f"{cat_icon} *{last['description']}*\n"
                f"💸 {fmt(last['amount'])} — {last['date']}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ হ্যাঁ, মুছুন", callback_data="confirm_delete"),
                     InlineKeyboardButton("❌ না", callback_data="back")]
                ])
            )

    elif data == "confirm_delete":
        exps = get_expenses(uid)
        if exps:
            deleted = exps.pop()
            cat_icon, cat_label = CATEGORIES[deleted["category"]]
            await query.edit_message_text(
                f"✅ মুছে ফেলা হয়েছে:\n{cat_icon} {deleted['description']} — {fmt(deleted['amount'])}",
                reply_markup=main_keyboard()
            )
        else:
            await query.edit_message_text("❌ কিছু নেই।", reply_markup=main_keyboard())

    elif data.startswith("cat|"):
        _, cat_id, amount_str, desc = data.split("|", 3)
        amount = float(amount_str)
        expense = {
            "id": len(get_expenses(uid)) + 1,
            "amount": amount,
            "description": desc,
            "category": cat_id,
            "date": today_str(),
        }
        user_data[uid]["expenses"].append(expense)

        # Today's total
        today_total = sum(e["amount"] for e in get_expenses(uid) if e["date"] == today_str())
        month_total = sum(e["amount"] for e in month_expenses(uid))
        budget = get_budget(uid)
        remaining = budget - month_total

        cat_icon, cat_label = CATEGORIES[cat_id]
        msg = (
            f"✅ *যোগ হয়েছে!*\n\n"
            f"{cat_icon} {desc}\n"
            f"💸 {fmt(amount)} — {cat_label}\n\n"
            f"📅 আজ মোট: *{fmt(today_total)}*\n"
            f"📆 এই মাসে: *{fmt(month_total)}*\n"
            f"💰 বাকি বাজেট: *{fmt(remaining)}*"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

# ── REPORT FUNCTIONS ──────────────────────────────────────────────────

async def send_today(target, uid, edit=False):
    today = today_str()
    exps = [e for e in get_expenses(uid) if e["date"] == today]
    total = sum(e["amount"] for e in exps)

    if not exps:
        msg = "📅 আজকে এখনো কোনো খরচ নেই।"
    else:
        lines = ["📅 *আজকের খরচ*\n"]
        for e in exps:
            icon, label = CATEGORIES[e["category"]]
            lines.append(f"{icon} {e['description']} — *{fmt(e['amount'])}*")
        lines.append(f"\n💸 *মোট: {fmt(total)}*")
        msg = "\n".join(lines)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 মেনু", callback_data="back")]])
    if edit:
        await target.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await target.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

async def send_report(target, uid, edit=False):
    now = date.today()
    exps = month_expenses(uid)
    total = sum(e["amount"] for e in exps)
    budget = get_budget(uid)
    saving = budget - total
    month_name = MONTHS_BN[now.month - 1]

    if not exps:
        msg = f"📊 *{month_name} {now.year}*\n\nএই মাসে কোনো খরচ নেই।"
    else:
        # By category
        cat_totals = defaultdict(float)
        for e in exps:
            cat_totals[e["category"]] += e["amount"]
        sorted_cats = sorted(cat_totals.items(), key=lambda x: -x[1])

        lines = [f"📊 *{month_name} {now.year} রিপোর্ট*\n"]
        lines.append(f"💸 মোট খরচ: *{fmt(total)}*")
        lines.append(f"💰 বাজেট: *{fmt(budget)}*")
        lines.append(f"{'🏦 সেভিং' if saving >= 0 else '⚠️ ওভার বাজেট'}: *{fmt(abs(saving))}*")
        lines.append(f"📝 লেনদেন: *{len(exps)}টি*\n")

        lines.append("📂 *ক্যাটাগরি অনুযায়ী:*")
        for cat_id, amt in sorted_cats:
            icon, label = CATEGORIES[cat_id]
            pct = (amt / total * 100) if total > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(f"{icon} {label}\n   {bar} {fmt(amt)} ({pct:.0f}%)")

        # Top day
        day_totals = defaultdict(float)
        for e in exps:
            day_totals[e["date"]] += e["amount"]
        if day_totals:
            top_day = max(day_totals, key=day_totals.get)
            d = datetime.strptime(top_day, "%Y-%m-%d")
            lines.append(f"\n🔥 সবচেয়ে বেশি খরচের দিন: *{d.day} {MONTHS_BN[d.month-1]}* ({fmt(day_totals[top_day])})")

        msg = "\n".join(lines)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 AI পরামর্শ নিন", callback_data="ai")],
        [InlineKeyboardButton("🔙 মেনু", callback_data="back")]
    ])
    if edit:
        await target.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await target.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

async def send_ai(target, uid, edit=False):
    exps = month_expenses(uid)
    if not exps:
        msg = "❌ AI পরামর্শের জন্য আগে কিছু খরচ যোগ করুন।"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 মেনু", callback_data="back")]])
        if edit:
            await target.edit_message_text(msg, reply_markup=kb)
        else:
            await target.message.reply_text(msg, reply_markup=kb)
        return

    total = sum(e["amount"] for e in exps)
    budget = get_budget(uid)
    saving = budget - total

    cat_totals = defaultdict(float)
    for e in exps:
        cat_totals[e["category"]] += e["amount"]
    summary = ", ".join([f"{CATEGORIES[c][1]}: {fmt(a)}" for c, a in cat_totals.items()])

    prompt = (
        f"আমি এই মাসে মোট {fmt(total)} টাকা খরচ করেছি। "
        f"বাজেট ছিল {fmt(budget)} টাকা। সেভিং: {fmt(saving)} টাকা।\n"
        f"খরচের বিভাজন: {summary}।\n"
        f"আমাকে বাংলায় ৩-৪টি practical suggestion দাও কীভাবে খরচ কমিয়ে সেভিং বাড়ানো যায়। "
        f"সহজ ভাষায় বলো। প্রতিটি point এ emoji দাও।"
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        suggestion = response.content[0].text
        msg = f"🤖 *AI পরামর্শ*\n\n{suggestion}"
    except Exception as e:
        msg = "❌ AI পরামর্শ পাওয়া যাচ্ছে না। একটু পরে চেষ্টা করুন।"

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 মেনু", callback_data="back")]])
    if edit:
        await target.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await target.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

async def budget_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ctx.args:
        try:
            amount = float(ctx.args[0].replace(",", ""))
            user_data[uid]["budget"] = amount
            await update.message.reply_text(f"✅ বাজেট সেট: *{fmt(amount)}*", parse_mode="Markdown", reply_markup=main_keyboard())
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন। যেমন: `/budget 10000`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"💰 বর্তমান বাজেট: *{fmt(get_budget(uid))}*\n\nবদলাতে: `/budget 15000`", parse_mode="Markdown")

async def delete_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    exps = get_expenses(uid)
    if not exps:
        await update.message.reply_text("❌ কোনো খরচ নেই।")
        return
    last = exps[-1]
    icon, label = CATEGORIES[last["category"]]
    await update.message.reply_text(
        f"🗑️ শেষ খরচ মুছবেন?\n\n{icon} *{last['description']}*\n{fmt(last['amount'])} — {last['date']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ মুছুন", callback_data="confirm_delete"),
             InlineKeyboardButton("❌ না", callback_data="back")]
        ])
    )

async def list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    exps = get_expenses(uid)[-10:]  # last 10
    if not exps:
        await update.message.reply_text("❌ কোনো খরচ নেই।")
        return
    lines = ["📋 *শেষ ১০টি খরচ:*\n"]
    for e in reversed(exps):
        icon, _ = CATEGORIES[e["category"]]
        lines.append(f"`#{e['id']}` {icon} {e['description']} — *{fmt(e['amount'])}* ({e['date']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_keyboard())

# ── MAIN ──────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("report", lambda u, c: send_report(u, u.effective_user.id)))
    app.add_handler(CommandHandler("today", lambda u, c: send_today(u, u.effective_user.id)))
    app.add_handler(CommandHandler("ai", lambda u, c: send_ai(u, u.effective_user.id)))
    app.add_handler(CommandHandler("budget", budget_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 টাকার হিসাব Bot চালু হয়েছে!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
