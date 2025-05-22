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

# 약속 정보를 저장할 딕셔너리
appointments = {}

def save_appointments():
    """약속 정보를 파일에 저장"""
    with open('appointments.json', 'w', encoding='utf-8') as f:
        json.dump(appointments, f, ensure_ascii=False, indent=2)

def load_appointments():
    """저장된 약속 정보를 불러옴"""
    global appointments
    try:
        with open('appointments.json', 'r', encoding='utf-8') as f:
            appointments = json.load(f)
    except FileNotFoundError:
        appointments = {}

def resolve_date_with_weekday(weekday_name: str, reference_date: datetime) -> str:
    weekday_index = weekdays.index(weekday_name)
    days_ahead = (weekday_index - reference_date.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = reference_date + timedelta(days=days_ahead)
    return f"{target_date.year}년 {target_date.month}월 {target_date.day}일 {weekday_name}"

# send_reminder 함수 시그니처를 JobQueue용으로 변경
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """리마인드 메시지 전송"""
    now = datetime.now()
    for chat_id, appointment in list(appointments.items()):
        try:
            if not appointment.get('reminder_enabled'):
                continue
            match = re.search(r'(\d{1,2}):(\d{2})', appointment['time'])
            if match:
                hour, minute = map(int, match.groups())
                # 한글 요일을 영어로 변환
                date_str = appointment['date']
                weekday_map = {
                    '월요일': 'Monday', '화요일': 'Tuesday', '수요일': 'Wednesday',
                    '목요일': 'Thursday', '금요일': 'Friday', '토요일': 'Saturday', '일요일': 'Sunday'
                }
                for kor, eng in weekday_map.items():
                    date_str = date_str.replace(kor, eng)
                
                appointment_time = datetime.strptime(date_str, '%Y년 %m월 %d일 %A').replace(hour=hour, minute=minute)
                reminder_time = appointment_time - timedelta(days=1)
                reminder_time = reminder_time.replace(hour=9, minute=0)
                same_day_reminder = appointment_time.replace(hour=9, minute=0)
                
                if now >= reminder_time and not appointment.get('reminder_sent'):
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🔔 리마인드: 내일 {appointment['time']}에 약속이 있어요!"
                    )
                    appointment['reminder_sent'] = True
                    save_appointments()
                if now >= same_day_reminder and not appointment.get('same_day_reminder_sent'):
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🔔 리마인드: 오늘 {appointment['time']}에 약속이 있어요!"
                    )
                    appointment['same_day_reminder_sent'] = True
                    save_appointments()
                if now > appointment_time + timedelta(hours=1):
                    del appointments[chat_id]
                    save_appointments()
        except Exception as e:
            print(f"리마인드 전송 중 오류 발생: {e}")

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

    # 약속 정보 저장 (요일+시간 형식도 지원)
    # 1. 'YYYY년 MM월 DD일 요일 HH:MM' 형식
    match = re.search(r'(\d{4}년 \d{1,2}월 \d{1,2}일 \S+)\s+(\d{1,2}:\d{2})', final)
    if match:
        date_str, time_str = match.groups()
    else:
        # 2. '요일 HH:MM' 형식
        match2 = re.search(r'(\S+요일)\s+(\d{1,2}:\d{2})', final)
        if match2:
            weekday_str, time_str = match2.groups()
            # 오늘 기준 다음 해당 요일 날짜 계산
            today = datetime.now()
            weekday_index = weekdays.index(weekday_str)
            days_ahead = (weekday_index - today.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = today + timedelta(days=days_ahead)
            # 현재 시스템의 년도 사용
            current_year = datetime.now().year
            date_str = f"{current_year}년 {target_date.month}월 {target_date.day}일 {weekday_str}"
        else:
            date_str, time_str = None, None

    if date_str and time_str:
        appointments[cid] = {
            'date': date_str,
            'time': time_str,
            'reminder_sent': False,
            'same_day_reminder_sent': False,
            'reminder_enabled': False  # 리마인드 활성화 상태 추가
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
    """리마인드 메시지 예약"""
    cid = update.effective_chat.id
    if cid not in appointments:
        await update.message.reply_text(
            "❗ 리마인드를 설정할 약속이 없습니다.\n\n"
            "리마인드를 설정하려면 다음 순서로 진행해주세요:\n"
            "1. 대화 내용을 입력\n"
            "2. /analyze 명령어로 분석\n"
            "3. /finalize 명령어로 약속 확정\n"
            "4. /remind 명령어로 리마인드 설정"
        )
        return
    
    appointment = appointments[cid]
    if appointment.get('reminder_enabled'):
        await update.message.reply_text(
            "❗ 이미 리마인드가 설정되어 있습니다.\n\n"
            f"📅 현재 약속: {appointment['date']} {appointment['time']}\n"
            "리마인드 상태를 확인하려면 /reminders 명령어를 사용하세요."
        )
        return
    
    # 리마인드 활성화
    appointment['reminder_enabled'] = True
    appointment['reminder_sent'] = False
    appointment['same_day_reminder_sent'] = False
    save_appointments()
    
    date_str = appointment['date']
    time_str = appointment['time']
    
    await update.message.reply_text(
        f"✅ 리마인드가 설정되었습니다!\n\n"
        f"📅 약속: {date_str} {time_str}\n"
        f"🔔 리마인드 예정:\n"
        f"- 전날 오전 9시\n"
        f"- 당일 오전 9시\n\n"
        f"리마인드 상태는 /reminders 명령어로 확인할 수 있습니다."
    )

async def remind_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """리마인드 비활성화"""
    cid = update.effective_chat.id
    if cid not in appointments:
        await update.message.reply_text(
            "❗ 설정된 약속이 없습니다.\n\n"
            "리마인드를 설정하려면 다음 순서로 진행해주세요:\n"
            "1. 대화 내용을 입력\n"
            "2. /analyze 명령어로 분석\n"
            "3. /finalize 명령어로 약속 확정\n"
            "4. /remind 명령어로 리마인드 설정"
        )
        return
    
    appointment = appointments[cid]
    if not appointment.get('reminder_enabled'):
        await update.message.reply_text(
            "❗ 이미 리마인드가 비활성화되어 있습니다.\n\n"
            f"📅 현재 약속: {appointment['date']} {appointment['time']}\n"
            "리마인드 상태를 확인하려면 /reminders 명령어를 사용하세요."
        )
        return
    
    # 리마인드 비활성화
    appointment['reminder_enabled'] = False
    save_appointments()
    
    await update.message.reply_text(
        f"✅ 리마인드가 비활성화되었습니다.\n\n"
        f"📅 약속: {appointment['date']} {appointment['time']}\n\n"
        f"다시 리마인드를 설정하려면 /remind 명령어를 사용하세요."
    )

async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """예약된 리마인드 목록을 보여줌"""
    cid = update.effective_chat.id
    if cid not in appointments:
        await update.message.reply_text("❗ 예약된 약속이 없습니다.")
        return
    
    appointment = appointments[cid]
    date_str = appointment['date']
    time_str = appointment['time']
    
    if not appointment.get('reminder_enabled'):
        await update.message.reply_text(
            f"📅 예약된 약속:\n"
            f"날짜: {date_str}\n"
            f"시간: {time_str}\n\n"
            f"❗ 리마인드가 설정되어 있지 않습니다.\n"
            f"리마인드를 설정하려면 /remind 명령어를 사용하세요."
        )
        return
    
    # 리마인드 상태 확인
    reminder_status = "✅ 전송됨" if appointment.get('reminder_sent') else "⏳ 예정"
    same_day_status = "✅ 전송됨" if appointment.get('same_day_reminder_sent') else "⏳ 예정"
    
    message = (
        f"📅 예약된 약속:\n"
        f"날짜: {date_str}\n"
        f"시간: {time_str}\n\n"
        f"🔔 리마인드 상태:\n"
        f"- 전날 리마인드: {reminder_status}\n"
        f"- 당일 리마인드: {same_day_status}"
    )
    
    await update.message.reply_text(message)

# ───── 핸들러 등록 ─────

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("clear", clear))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("finalize", finalize))
app.add_handler(CommandHandler("remind", remind))
app.add_handler(CommandHandler("remind_off", remind_off))
app.add_handler(CommandHandler("reminders", reminders))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message))

if __name__ == "__main__":
    print("🤖 GO!비서 실행 중...")
    load_appointments()  # 저장된 약속 정보 불러오기
    # JobQueue에 리마인드 작업 등록
    app.job_queue.run_repeating(send_reminder, interval=60, first=0)
    app.run_polling(drop_pending_updates=True)