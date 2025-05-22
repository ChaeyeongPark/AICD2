import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from gpt import analyze_dialogue
from naver_api import search_places, format_places_for_message
import re
from datetime import datetime, timedelta
from collections import Counter

# .env 파일 로드 및 토큰 불러오기
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

dialogues = {}
recommendation_cache = {}
weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

def resolve_date_with_weekday(weekday_name: str, reference_date: datetime) -> str:
    weekday_index = weekdays.index(weekday_name)
    days_ahead = (weekday_index - reference_date.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = reference_date + timedelta(days=days_ahead)
    return f"{target_date.year}년 {target_date.month}월 {target_date.day}일 {weekday_name}"

# ───── 핸들러 함수들 ─────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ GO!비서 챗봇이 시작되었습니다!")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    dialogues[cid] = []
    recommendation_cache.pop(cid, None)
    await update.message.reply_text("🧹 대화 기록이 초기화되었습니다!")

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    txt = update.message.text.strip()
    if cid not in dialogues:
        dialogues[cid] = []
    person = str(update.message.from_user.first_name or update.message.from_user.id)
    dialogues[cid].append({"person": person, "text": txt})

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    conv = dialogues.get(cid, [])
    if not conv:
        await update.message.reply_text("❗ 분석할 대화가 없습니다.")
        return

    texts = [d["text"] for d in conv]
    result = analyze_dialogue(texts)

    # 시간 추천 출력
    times = result.get("available_times", [])
    reference_date = datetime.now()
    time_strings = []

    for t in times:
        m = re.match(r"(\S+)\s+(\d{1,2}):\d{2}", t) or re.match(r"(\S+)\s+(오전|오후|저녁|밤|아침|\d{1,2})", t)
        if m:
            time_part = m[2]
            if time_part.isdigit():  # "18" → "18:00"
                time_part = f"{time_part}:00"
            date_str = resolve_date_with_weekday(m[1], reference_date)
            time_strings.append(f"- {date_str} {time_part}")
        else:
            for wd in weekdays:
                if wd in t:
                    date_str = resolve_date_with_weekday(wd, reference_date)
                    time_strings.append(f"- {date_str}")
                    break

    if time_strings:
        recommendation_cache[cid] = times[:4]
        await update.message.reply_text("🧠 분석 완료!\n📅 후보 시간:\n" + "\n".join(time_strings[:4]) + "\n\n최종 확정을 원하면 /finalize")
    else:
        await update.message.reply_text("❌ 공통 가능한 시간이 없습니다.")

    # 장소 추천
    locations = result.get("locations", [])
    locs = [l["location"].replace("역", "").replace("앞", "").strip()
            for l in locations if l["sentiment"] in ("positive", "neutral")]
    if not locs:
        await update.message.reply_text("❗ 장소 정보가 부족합니다.")
        return

    keyword = Counter(locs).most_common(1)[0][0] + " 조용한 카페"
    places = search_places(keyword)

    if places:
        msg = f"📍 '{keyword}' 추천 장소:\n\n" + format_places_for_message(places)
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(f"🔍 '{keyword}' 검색 결과가 없습니다.")

async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    cands = recommendation_cache.get(cid)
    if not cands:
        await update.message.reply_text("❗ 먼저 /analyze 를 실행하세요.")
        return

    msgs = [d["text"] for d in dialogues.get(cid, [])[::-1]]
    final = cands[0]
    for m in msgs:
        for cand in cands:
            if cand in m:
                final = cand
                break
        else:
            continue
        break

    await update.message.reply_text(f"✅ 최종 약속 시간은 다음과 같습니다:\n🕒 {final}")
    dialogues[cid] = []
    recommendation_cache.pop(cid, None)

# ───── 핸들러 등록 ─────

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("clear", clear))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("finalize", finalize))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message))

if __name__ == "__main__":
    print("🤖 GO!비서 실행 중...")
    app.run_polling(drop_pending_updates=True)