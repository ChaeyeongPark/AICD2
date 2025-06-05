import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from gpt import analyze_dialogue
from naver_api import search_places, format_places_for_message
import re
from datetime import datetime, timedelta
from collections import Counter
import asyncio
import json

# .env 파일 로드 및 토큰 불러오기
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

dialogues = {}
recommendation_cache = {}
weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
appointments = {}

def save_appointments():
    with open('appointments.json', 'w', encoding='utf-8') as f:
        json.dump(appointments, f, ensure_ascii=False, indent=2)

def load_appointments():
    global appointments
    try:
        with open('appointments.json', 'r', encoding='utf-8') as f:
            appointments = json.load(f)
    except FileNotFoundError:
        appointments = {}

def resolve_date_with_weekday(weekday_name: str, reference_date: datetime) -> str:
    weekday_name = weekday_name.strip()

    if weekday_name == "오늘":
        target_date = reference_date
    elif weekday_name == "내일":
        target_date = reference_date + timedelta(days=1)
    elif weekday_name == "모레":
        target_date = reference_date + timedelta(days=2)
    elif weekday_name in weekdays:
        weekday_index = weekdays.index(weekday_name)
        days_ahead = (weekday_index - reference_date.weekday() + 7) % 7
        if days_ahead == 0:
            days_ahead = 7
        target_date = reference_date + timedelta(days=days_ahead)
    else:
        raise ValueError(f"유효하지 않은 요일 이름: {weekday_name}")

    return f"{target_date.year}년 {target_date.month}월 {target_date.day}일 {weekday_name}"

def normalize_time_str(t: str) -> str:
    return re.sub(r"[시:\s분]", "", t)

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

    times = result.get("available_times", [])
    reference_date = datetime.now()
    time_strings = []

    for t in times:
        # 전체 날짜와 시간이 포함된 형식 (예: "2025년 6월 13일 금요일 18:30")
        full_datetime_match = re.match(r"(\d{4})년\s+(\d{1,2})월\s+(\d{1,2})일\s+(\S+요일)\s+(\d{1,2}):(\d{2})", t)
        if full_datetime_match:
            time_strings.append(f"- {t}")
            continue
            
        # 요일과 시간이 포함된 형식 (예: "금요일 18:30")
        m = re.match(r"(\S+)\s+(\d{1,2}):(\d{2})", t)
        if m:
            weekday = m[1]
            hour = m[2]
            minute = m[3]
            date_str = resolve_date_with_weekday(weekday, reference_date)
            time_strings.append(f"- {date_str} {hour}:{minute}")
        else:
            # 요일만 있는 경우
            for wd in weekdays:
                if wd in t:
                    date_str = resolve_date_with_weekday(wd, reference_date)
                    # 시간이 없는 경우 마지막 대화에서 시간을 찾아봄
                    time_found = False
                    for msg in reversed(conv):
                        time_match = re.search(r"(\d{1,2})시\s*반?|\d{1,2}:\d{2}", msg["text"])
                        if time_match:
                            time_str = time_match.group()
                            if "반" in time_str:
                                hour = int(time_str.replace("시", "").replace("반", ""))
                                time_str = f"{hour:02d}:30"
                            elif "시" in time_str:
                                hour = int(time_str.replace("시", ""))
                                time_str = f"{hour:02d}:00"
                            time_found = True
                            time_strings.append(f"- {date_str} {time_str}")
                            break
                    if not time_found:
                        time_strings.append(f"- {date_str} 17:00")  # 기본값
                    break

    if time_strings:
        recommendation_cache[cid] = times[:4]
        await update.message.reply_text("🧠 분석 완료!\n📅 후보 시간:\n" + "\n".join(time_strings[:4]) + "\n\n최종 확정을 원하면 /finalize")
    else:
        await update.message.reply_text("❌ 공통 가능한 시간이 없습니다.")

    locations = result.get("locations", [])
    locs = [l["location"].replace("역", "").replace("앞", "").strip()
            for l in locations if l["sentiment"] in ("positive", "neutral")]
    if not locs:
        await update.message.reply_text("❗ 장소 정보가 부족합니다.")
        return

    keyword = Counter(locs).most_common(1)[0][0]
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
            norm_m = normalize_time_str(m)
            norm_c = normalize_time_str(cand)
            if norm_c in norm_m:
                final = cand
                break
        else:
            continue
        break

    match = re.search(r'(\d{4}년 \d{1,2}월 \d{1,2}일 \S+)\s+(\d{1,2}:\d{2})', final)
    if match:
        date_str, time_str = match.groups()
    else:
        match2 = re.search(r'(\S+요일|오늘|내일|모레)\s+(\d{1,2}:\d{2})', final)
        if match2:
            weekday_str, time_str = match2.groups()
            today = datetime.now()
            date_str = resolve_date_with_weekday(weekday_str, today)
        else:
            date_str, time_str = None, None

    if date_str and time_str:
        appointments[cid] = {
            'date': date_str,
            'time': time_str,
            'reminder_sent': False,
            'same_day_reminder_sent': False,
            'reminder_enabled': False
        }
        save_appointments()

    await update.message.reply_text(
        f"✅ 최종 약속 시간은 다음과 같습니다:\n"
        f"🕒 {final}\n\n"
        f"리마인드를 설정하려면 /remind 명령어를 사용하세요."
    )
    dialogues[cid] = []
    recommendation_cache.pop(cid, None)

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if cid not in appointments:
        await update.message.reply_text("❗ 설정된 약속이 없습니다. 먼저 /finalize 명령어로 약속을 확정하세요.")
        return

    appointment = appointments[cid]
    if appointment.get('reminder_enabled'):
        await update.message.reply_text(f"❗ 이미 리마인드가 설정되어 있습니다.\n\n📅 현재 약속: {appointment['date']} {appointment['time']}")
        return

    appointment['reminder_enabled'] = True
    appointment['reminder_sent'] = False
    appointment['same_day_reminder_sent'] = False
    save_appointments()

    await update.message.reply_text(
        f"✅ 리마인드가 설정되었습니다!\n\n📅 약속: {appointment['date']} {appointment['time']}\n🔔 리마인드는 전날 오전 9시 및 당일 오전 9시에 전송됩니다."
    )

async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if cid not in appointments:
        await update.message.reply_text("❗ 설정된 약속이 없습니다.")
        return

    appointment = appointments[cid]
    date = appointment['date']
    time = appointment['time']
    enabled = appointment.get('reminder_enabled', False)
    sent = appointment.get('reminder_sent', False)
    same_day = appointment.get('same_day_reminder_sent', False)

    status = (
        f"📅 예약된 약속: {date} {time}\n"
        f"🔔 리마인드 상태:\n"
        f"- 활성화: {'✅' if enabled else '❌'}\n"
        f"- 전날 리마인드: {'✅ 전송됨' if sent else '⏳ 대기 중'}\n"
        f"- 당일 리마인드: {'✅ 전송됨' if same_day else '⏳ 대기 중'}"
    )
    await update.message.reply_text(status)

async def remind_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if cid not in appointments:
        await update.message.reply_text("❗ 설정된 약속이 없습니다.")
        return

    appointment = appointments[cid]
    if not appointment.get('reminder_enabled'):
        await update.message.reply_text("⚠️ 리마인드가 이미 비활성화되어 있습니다.")
        return

    appointment['reminder_enabled'] = False
    save_appointments()
    await update.message.reply_text(f"🚫 리마인드가 비활성화되었습니다.\n📅 약속: {appointment['date']} {appointment['time']}")

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("clear", clear))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("finalize", finalize))
app.add_handler(CommandHandler("remind", remind))
app.add_handler(CommandHandler("reminders", reminders))
app.add_handler(CommandHandler("remind_off", remind_off))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message))

if __name__ == "__main__":
    print("GO!비서 실행 중...")
    load_appointments()
    app.run_polling(drop_pending_updates=True)
