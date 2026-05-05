import os
import logging
import requests
from dotenv import load_dotenv
from anthropic import Anthropic
import discord
from discord.ext import commands

load_dotenv()

DISCORD_TOKEN    = os.getenv("DISCORD_TOKEN")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY")
XQ_SERVER        = os.getenv("XQ_SERVER", "http://10.211.55.3:8089")
ALLOWED_USER_ID  = int(os.getenv("ALLOWED_USER_ID", "0"))

logging.basicConfig(level=logging.INFO)
claude   = Anthropic(api_key=ANTHROPIC_KEY)
history: dict[int, list] = {}

SYSTEM_PROMPT = """你是財務助理，服務的對象是台灣台中的獨立股票交易者與財務顧問。
你熟悉台灣股市（尤其電線電纜、記憶體晶片、半導體封測），可以協助分析個股、
解讀技術指標，以及回答財務與投資問題。回答用繁體中文，簡短精確。"""

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def _allowed(user_id: int) -> bool:
    return ALLOWED_USER_ID == 0 or user_id == ALLOWED_USER_ID

def _xq_quote(code: str) -> str:
    try:
        r = requests.get(f"{XQ_SERVER}/quote/{code}", timeout=5)
        d = r.json()
        if d.get("last", 0) == 0:
            return f"{code}：盤後無即時資料（開盤後才有數值）"
        return (
            f"{code}\n"
            f"現價：{d['last']}　開盤：{d['open']}\n"
            f"最高：{d['high']}　最低：{d['low']}\n"
            f"成交量：{d['volume']}"
        )
    except Exception as e:
        return f"XQ server 無法連線：{e}"

def _xq_batch(codes: list[str]) -> str:
    try:
        r = requests.get(
            f"{XQ_SERVER}/batch",
            params={"codes": ",".join(codes), "fields": "LTP,High,Low,VOL"},
            timeout=8
        )
        d = r.json()
        lines = []
        for code, vals in d.items():
            ltp = vals.get("LTP", 0)
            if ltp == 0:
                lines.append(f"{code}：盤後")
            else:
                lines.append(f"{code}  現價 {ltp}  量 {vals.get('VOL',0)}")
        return "\n".join(lines)
    except Exception as e:
        return f"XQ server 無法連線：{e}"

@bot.event
async def on_ready():
    print(f"Bot 已上線：{bot.user}")

@bot.command(name="help")
async def cmd_help(ctx):
    if not _allowed(ctx.author.id):
        return
    await ctx.send(
        "指令列表：\n"
        "`!quote <代號>` — XQ 即時報價\n"
        "`!batch <代號1> <代號2> ...` — 批次報價\n"
        "`!clear` — 清除對話紀錄\n\n"
        "直接輸入文字即可與 Claude 對話。"
    )

@bot.command(name="quote")
async def cmd_quote(ctx, code: str = None):
    if not _allowed(ctx.author.id):
        return
    if not code:
        await ctx.send("用法：`!quote 2330`")
        return
    await ctx.send(_xq_quote(code.upper()))

@bot.command(name="batch")
async def cmd_batch(ctx, *args):
    if not _allowed(ctx.author.id):
        return
    if not args:
        await ctx.send("用法：`!batch 2330 2317 2412`")
        return
    codes = [c.upper() for c in args]
    await ctx.send(_xq_batch(codes))

@bot.command(name="clear")
async def cmd_clear(ctx):
    if not _allowed(ctx.author.id):
        return
    history.pop(ctx.author.id, None)
    await ctx.send("對話紀錄已清除。")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not _allowed(message.author.id):
        return

    await bot.process_commands(message)
    if message.content.startswith("!"):
        return

    user_id = message.author.id
    msgs = history.setdefault(user_id, [])
    msgs.append({"role": "user", "content": message.content})

    if len(msgs) > 20:
        msgs[:] = msgs[-20:]

    async with message.channel.typing():
        resp = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=msgs,
        )
    reply = resp.content[0].text
    msgs.append({"role": "assistant", "content": reply})

    await message.channel.send(reply)

if __name__ == "__main__":
    if not DISCORD_TOKEN or "你的" in DISCORD_TOKEN:
        print("請先填寫 .env 的 DISCORD_TOKEN 和 ANTHROPIC_API_KEY")
        exit(1)
    bot.run(DISCORD_TOKEN)
