from typing import List, Tuple
import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# 간단한 룰 기반 NER (키워드 기반)
def ner_model(input_list: List[str]) -> List[List[Tuple[str, str]]]:
    result = []
    for text in input_list:
        ner_result = []

        # 날짜
        if "다음주" in text:
            ner_result.append(("다음주", "DT_WEEK"))
        for day in ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]:
            if day in text:
                ner_result.append((day, "DT_DAY"))
        if "주말" in text:
            ner_result.append(("주말", "DT_DURATION"))

        # 시간 표현
        if "오전" in text:
            ner_result.append(("오전", "TI_DURATION"))
        if "오후" in text:
            ner_result.append(("오후", "TI_DURATION"))
        if "저녁" in text:
            ner_result.append(("저녁", "TI_DURATION"))
        if "밤" in text:
            ner_result.append(("밤", "TI_DURATION"))
        if "아침" in text:
            ner_result.append(("아침", "TI_DURATION"))
        if "정오" in text:
            ner_result.append(("정오", "TI_DURATION"))

        for hour in ["6시", "7시", "8시", "9시", "10시", "11시"]:
            if hour in text:
                ner_result.append((hour, "TI_HOUR"))

        # 장소
        if "카페" in text:
            ner_result.append(("카페", "PLACE"))

        result.append(ner_result)
    return result

# intent 추출 모델
def intent_model(input_list: List[str]) -> List[str]:
    result = []
    for text in input_list:
        if any(word in text for word in [
            "돼", "가능", "좋아", "괜찮아", "갈게", "된다",
            "보자", "만나자", "그때 보자", "괜찮은 듯", "그 시간 어때", "오케이", "ㅇㅋ", "좋지"
        ]):
            result.append("+")
        elif any(word in text for word in [
            "안돼", "불가능", "싫어", "못", "안될", "안 될 것 같아", "불가",
            "안 될 듯", "힘들 듯", "어려울 것 같아"
        ]):
            result.append("-")
        else:
            result.append("0")
    return result

# NER 후처리 함수
def postprocess_NER(preds: List[List[Tuple[str, str]]]) -> List[List[Tuple[str, str]]]:
    processed = []
    for ner_list in preds:
        clean = []
        for word, tag in ner_list:
            if tag.startswith("DT_") or tag.startswith("TI_"):
                clean.append((word, tag))
        processed.append(clean)
    return processed

# GPT 장소 추출 함수
def gpt_place_extraction(texts):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    full_context = "\n".join(texts)

    prompt = f"""
다음은 친구들 간의 약속 잡기 대화입니다.
대화에서 사람들이 최종적으로 만나기로 결정한 장소 하나만 정확히 뽑아줘.
없으면 '없음'이라고 답해. 설명 없이 장소 이름만 출력해줘.

대화:
{full_context}

장소:
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        keyword = response['choices'][0]['message']['content'].strip()
        if keyword.lower() == '없음':
            return []
        return [(keyword, "PLACE")]
    except Exception as e:
        print(f"[GPT 오류] {e}")
        return []
