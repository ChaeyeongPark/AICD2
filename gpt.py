import os
import openai
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta

# 🔐 환경변수 로드
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

class GPTAnalysisError(Exception):
    """GPT 분석 중 발생하는 에러를 처리하기 위한 커스텀 예외"""
    pass

def analyze_dialogue(dialogue_texts: list[str]) -> dict:
    if not dialogue_texts:
        raise GPTAnalysisError("분석할 대화 내용이 없습니다.")
    
    if not openai.api_key:
        raise GPTAnalysisError("OpenAI API 키가 설정되지 않았습니다.")

    # 현재 날짜 가져오기
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y년 %m월 %d일")
    
    # 다음 주 목요일 날짜 계산
    days_until_next_thursday = (3 - current_date.weekday()) % 7 + 7  # 현재 요일이 목요일이면 7일 후
    next_thursday = current_date + timedelta(days=days_until_next_thursday)
    next_thursday_str = next_thursday.strftime("%Y년 %m월 %d일")
    
    prompt = (
        f"현재 날짜는 {current_date_str}입니다. 다음은 사람들이 나눈 단체 대화입니다. 이 대화를 바탕으로 아래 정보를 추출해 주세요:\n\n"
        "1. 시간 분석:\n"
        "   - 모든 인원이 가능한 공통 시간이 있으면 그 시간을 추출\n"
        "   - 모든 인원이 가능한 시간이 없다면, 최대 인원이 가능한 시간을 추천하고 불참자 명단 작성\n"
        "   - 시간 추출 규칙:\n"
        "     * 최종 결정된 시간을 추출 (예: '~시로 하자', '~시에 만나자', '~시 시작')\n"
        "     * 시간 제약조건은 무시 (예: '~시까지 가능', '~시부터 가능', '~시 전에 나가야')\n"
        "     * 여러 시간이 언급되면, 가장 최근에 결정된 시간을 사용\n"
        "     * 시간은 24시간 형식으로 변환\n\n"
        "2. 장소 분석:\n"
        "   - 최종적으로 결정된 장소 추출\n"
        "   - 장소와 관련된 표현에서 장소 키워드와 감정(positive/negative/neutral) 추출\n\n"
        f"날짜는 현재 날짜({current_date_str}) 기준으로 계산:\n"
        f"- '다음 주 목요일' → {next_thursday_str}\n"
        "- '6일' → 현재 월의 6일\n"
        "- '다음 주'는 현재 날짜로부터 7일 이후의 주를 의미\n\n"
        "결과는 다음 JSON 형식으로 반환:\n"
        "{\n"
        "  \"available_times\": [\"목요일 18:30\"],\n"
        "  \"max_attend_time\": {\n"
        "    \"time\": \"목요일 18:30\",\n"
        "    \"absent_members\": [\"재현\"],\n"
        "    \"reason\": \"18:30 이전에 나가야 함\"\n"
        "  },\n"
        "  \"locations\": [\n"
        "    {\"sentence\": \"종로 가자! 결정!\", \"location\": \"종로\", \"sentiment\": \"positive\"}\n"
        "  ]\n"
        "}\n\n"
        "아래는 대화입니다:\n"
    )

    for i, text in enumerate(dialogue_texts, 1):
        prompt += f"{i}. {text}\n"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"너는 시간과 장소를 분석하는 전문가야. 현재 날짜는 {current_date_str}이야. '다음 주'는 현재 날짜로부터 7일 이후의 주를 의미해. 예를 들어, 현재가 {current_date_str}이면 '다음 주 목요일'은 {next_thursday_str}이야. 시간은 반드시 최종 결정된 시간을 추출하고, 시간 제약조건은 무시해. 여러 시간이 언급되면 가장 최근에 결정된 시간을 사용해. 모든 인원이 가능한 시간이 없으면 최대 인원이 가능한 시간을 추천하고, 그 시간에 불참하는 사람과 이유도 함께 알려줘. 시간은 24시간 형식으로 변환하고, 날짜는 현재 날짜를 기준으로 계산해."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        output_text = response["choices"][0]["message"]["content"]
        
        try:
            result = json.loads(output_text)
            # 필수 필드 검증
            required_fields = ["available_times", "locations"]
            for field in required_fields:
                if field not in result:
                    raise GPTAnalysisError(f"GPT 응답에 필수 필드 '{field}'가 없습니다.")
            return result
        except json.JSONDecodeError as e:
            raise GPTAnalysisError(f"GPT 응답을 JSON으로 파싱할 수 없습니다: {str(e)}")

    except openai.error.AuthenticationError:
        raise GPTAnalysisError("OpenAI API 인증에 실패했습니다. API 키를 확인해주세요.")
    except openai.error.RateLimitError:
        raise GPTAnalysisError("OpenAI API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
    except openai.error.APIError as e:
        raise GPTAnalysisError(f"OpenAI API 호출 중 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        raise GPTAnalysisError(f"예상치 못한 오류가 발생했습니다: {str(e)}")