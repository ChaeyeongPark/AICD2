import os
import openai
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta
import re

# 🔐 환경변수 로드
load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_next_weekday(current_date: datetime, target_weekday: int) -> datetime:
    """주어진 날짜의 다음 특정 요일 날짜를 반환"""
    days_ahead = target_weekday - current_date.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return current_date + timedelta(days=days_ahead)

def extract_base_date(dialogue_texts: list[str]) -> datetime:
    """대화에서 첫 메시지의 날짜를 추출"""
    if not dialogue_texts:
        return datetime.now()
    
    # [YYYY-MM-DD HH:mm] 형식의 날짜 찾기
    date_pattern = r'\[(\d{4}-\d{2}-\d{2})\s+[^\]]+\]'
    for text in dialogue_texts:
        match = re.search(date_pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), '%Y-%m-%d')
            except ValueError:
                pass
    return datetime.now()

def analyze_dialogue(dialogue_texts: list[str], base_date: datetime = None, model_name: str = "gpt-4") -> dict:
    # 대화에서 날짜 추출 또는 주어진 base_date 사용
    today = base_date if base_date else extract_base_date(dialogue_texts)
    
    # 대화에서 날짜/시간 정보만 추출
    cleaned_texts = []
    for text in dialogue_texts:
        # 날짜 부분 제거
        cleaned_text = re.sub(r'\[\d{4}-\d{2}-\d{2}\s+[^\]]+\]\s*', '', text)
        cleaned_texts.append(cleaned_text)
    
    prompt = (
        f"오늘은 {today.year}년 {today.month}월 {today.day}일입니다.\n"
        "아래 대화를 분석하여 약속 시간과 장소를 찾아주세요.\n\n"
        "주의사항:\n"
        "1. 반드시 JSON 형식으로만 응답하세요.\n"
        "2. 다른 설명이나 텍스트는 절대 포함하지 마세요.\n"
        "3. 최대한 많은 참여자가 가능한 시간을 찾아내세요.\n"
        "4. 시간이 구체적으로 언급되지 않은 경우에만 오후 5시(17:00)를 사용하세요.\n"
        "5. 날짜는 반드시 'YYYY년 MM월 DD일 요일 HH:MM' 형식으로 반환하세요.\n"
        "6. 대화에서 언급된 구체적인 시간이 있다면 반드시 그 시간을 사용하세요.\n"
        "7. 의미 없는 대화나 무관한 발언은 무시하세요.\n"
        "8. 시간을 전혀 언급하지 않은 참여자는 분석에서 제외하세요.\n"
        "9. '다음주'는 반드시 대화 날짜 기준으로 계산하세요.\n\n"
        
        "시간 분석 규칙:\n"
        "1. 요일 기반 분석:\n"
        "- 각 참여자가 언급한 가능한 요일들을 모두 파악\n"
        "- 불가능한 요일 표현도 반드시 고려 ('월,화 빼고', 'A 제외' 등)\n"
        "- 예시:\n"
        "  * '월,화 가능' → [월,화] 가능\n"
        "  * '월,화 빼고 다 가능' → [수,목,금,토,일] 가능\n"
        "  * '월화수 제외하고' → [목,금,토,일] 가능\n"
        "- 시간을 언급한 참여자들 중 가장 많은 사람이 가능한 요일 찾기\n"
        "- '월,화' 또는 '월화수' 같은 연속된 표현도 각각의 요일로 분리\n\n"
        
        "2. 시간 표현:\n"
        "- '다음 주' → 대화 날짜({today.strftime('%Y-%m-%d')}) 기준 다음 주의 날짜\n"
        "- '다다음 주' → 대화 날짜 기준 2주 후의 주\n"
        "- '이번 주' → 대화 날짜가 속한 주간\n"
        "- 'N주 뒤' → N주 후\n"
        "- '내일' → 대화 날짜 다음 날\n"
        "- '8월 둘째 주' → 8월 두 번째 주 시작일 기준\n\n"
        
        "3. 시간대 변환:\n"
        "- 'N시' → HH:00 형식으로 변환\n"
        "- 'N시 반' → HH:30 형식으로 변환\n"
        "- '오전' = 10:00\n"
        "- '점심' = 12:00\n"
        "- '오후' = 17:00\n"
        "- '저녁' = 18:00\n"
        "- '6시 반' = 18:30\n"
        "- '7시' = 19:00\n\n"
        
        "4. 가능 시간 분석 방법:\n"
        "- 각 참여자의 가능한 요일을 리스트로 만들기\n"
        "- 불가능하다고 언급된 요일은 반드시 제외\n"
        "- 시간을 언급한 참여자들 중 가장 많은 사람이 가능한 요일 찾기\n"
        "- 시간을 전혀 언급하지 않은 참여자는 분석에서 제외\n"
        "- 무의미한 대화나 관련 없는 발언은 무시\n"
        "- 예시:\n"
        "  * '금요일 6시 반으로 할까요?' → '금요일 18:30'\n"
        "  * '신촌 6시 반으로 확정하자!' → '금요일 18:30'\n\n"
        
        "5. 장소 분석:\n"
        "- 긍정적 표현: '좋다', '괜찮다', '좋아', '가자' 등\n"
        "- 부정적 표현: '싫다', '별로', '극혐', '역겨워', '안볼래', '정신없어' 등\n"
        "- 무의미한 발언이나 관련 없는 대화는 무시\n\n"
        
        "6. 시간 정보 부족 판단:\n"
        "- 시간을 언급한 참여자가 2명 미만인 경우\n"
        "- 시간을 언급한 참여자들 간에 겹치는 시간이 전혀 없는 경우\n"
        "- 시간 정보가 부족하다고 판단되면 available_times를 빈 배열로 반환\n\n"
        
        "7. 참여자 분석:\n"
        "- 시간 관련 발언을 한 참여자만 분석에 포함\n"
        "- 장소만 언급하거나 무의미한 대화만 한 참여자는 제외\n"
        "- 예시:\n"
        "  * '퉁퉁퉁' → 무시\n"
        "  * '트랄라레로' → 무시\n"
        "  * '장소는 어디가 좋을까요?' → 시간 분석에서 제외\n\n"
        
        "아래 형식의 JSON으로만 응답하세요:\n"
        "{\n"
        "  \"available_times\": [\"2025년 6월 13일 금요일 18:30\"],\n"
        "  \"locations\": [\n"
        "    {\"sentence\": \"신촌 좋다\", \"location\": \"신촌\", \"sentiment\": \"positive\"},\n"
        "    {\"sentence\": \"홍대는 너무 붐벼서 싫어요\", \"location\": \"홍대\", \"sentiment\": \"negative\"}\n"
        "  ]\n"
        "}\n\n"
        "대화 내용:\n"
    )

    for i, text in enumerate(cleaned_texts, 1):
        prompt += f"{i}. {text}\n"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "너는 JSON 응답 전문가야. 어떤 상황에서도 반드시 순수한 JSON 형식으로만 응답해야 하며, 다른 설명이나 텍스트는 절대 포함하지 마. 분석 결과는 available_times와 locations 키를 가진 JSON 객체로만 반환해야 해. 무의미한 대화는 무시하고, 시간을 언급한 참여자들 중 가장 많은 사람이 가능한 시간을 찾아내야 해."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        output_text = response.choices[0].message.content.strip()
        
        # JSON 형식이 아닌 텍스트 제거
        try:
            # JSON 시작 위치 찾기
            json_start = output_text.find('{')
            if json_start != -1:
                # JSON 끝 위치 찾기
                json_end = output_text.rfind('}') + 1
                if json_end > json_start:
                    output_text = output_text[json_start:json_end]
            
            result = json.loads(output_text)
            return result
        except json.JSONDecodeError:
            print("⚠️ GPT 응답이 JSON 형식이 아닙니다. 응답 내용:\n", output_text)
            return {"available_times": [], "locations": []}

    except Exception as e:
        print("❌ GPT API 호출 실패:", e)
        return {"available_times": [], "locations": []}
