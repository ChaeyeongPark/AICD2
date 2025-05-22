import os
import openai
import json
from dotenv import load_dotenv

# 🔐 환경변수 로드
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def analyze_dialogue(dialogue_texts: list[str]) -> dict:
    prompt = (
        "다음은 사람들이 나눈 단체 대화입니다. 이 대화를 바탕으로 아래 두 가지 정보를 추출해 주세요:\n\n"
        "1. 시간 (available_times): 대화에서 실제로 언급된 표현을 기반으로, "
        "**모든 참여자가 동의한 가능한 시간대가 여러 개 있다면 모두** 추출해 주세요. "
        "시간 표현이 '18:00~20:00'처럼 정확하지 않더라도, '오후', '6시 이후', '저녁쯤' 등 "
        "추상적인 표현이 있다면 그것도 해석하여 포함해 주세요. 예: '목요일 오후' → '목요일 15:00', '금요일 6시 이후' → '금요일 18:00' 등.\n\n"
        "2. 장소 (locations): 장소와 관련된 표현에서 장소 키워드(Location)와 감정(Sentiment: positive, negative, neutral)을 추출해 주세요. "
        "장소가 없는 문장은 제외하고, 가능한 간결한 장소명으로 정리해 주세요.\n\n"
        "결과는 다음과 같은 JSON 형식으로 반환해 주세요:\n"
        "{\n"
        "  \"available_times\": [\"수요일 18:00\", \"목요일 오후\", \"금요일 19:00\"],\n"
        "  \"locations\": [\n"
        "    {\"sentence\": \"홍대 괜찮네\", \"location\": \"홍대\", \"sentiment\": \"positive\"},\n"
        "    {\"sentence\": \"혜화는 멀어서 별로야\", \"location\": \"혜화\", \"sentiment\": \"negative\"}\n"
        "  ]\n"
        "}\n\n"
        "아래는 대화입니다:\n"
    )

    for i, text in enumerate(dialogue_texts, 1):
        prompt += f"{i}. {text}\n"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "너는 시간과 장소를 분석하는 전문가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        output_text = response["choices"][0]["message"]["content"]
        return json.loads(output_text)

    except Exception as e:
        print("❌ GPT 응답 파싱 실패:", e)
        return {"available_times": [], "locations": []}
