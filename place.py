import os
import requests
from dotenv import load_dotenv

# 🔐 환경변수 로드
load_dotenv()

# ✅ .env에서 인증 정보 가져오기
CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

headers = {
    "X-Naver-Client-Id": CLIENT_ID,
    "X-Naver-Client-Secret": CLIENT_SECRET
}

def search_places(keyword, display=3):
    """네이버 로컬 검색 API"""
    url = "https://openapi.naver.com/v1/search/local.json"
    params = {
        "query": keyword,
        "display": display,
        "start": 1,
        "sort": "random"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json().get('items', []) if response.status_code == 200 else []

def search_image(keyword):
    """네이버 이미지 검색 API"""
    url = "https://openapi.naver.com/v1/search/image"
    params = {
        "query": keyword,
        "display": 1,
        "sort": "sim"
    }
    response = requests.get(url, headers=headers, params=params)
    items = response.json().get('items', [])
    return items[0]['link'] if items else None

def get_blog_snippet(keyword):
    """네이버 블로그 검색 API"""
    url = "https://openapi.naver.com/v1/search/blog"
    params = {
        "query": keyword,
        "display": 1,
        "sort": "sim"
    }
    response = requests.get(url, headers=headers, params=params)
    items = response.json().get('items', [])
    return items[0]['description'].replace('<b>', '').replace('</b>', '') if items else "리뷰 정보 없음"

def format_places_for_message(places):
    """텔레그램 메시지 출력용 포맷 함수"""
    lines = []
    for idx, place in enumerate(places, 1):
        title = place['title'].replace('<b>', '').replace('</b>', '')
        address = place['roadAddress'] or place['address']
        link = place['link']
        lines.append(f"{idx}. {title}\n   - 📌 {address}\n   - 🔗 {link}")
    return "\n".join(lines)

def print_cards(places):
    """터미널 출력용 카드 포맷"""
    for idx, place in enumerate(places, 1):
        title = place['title'].replace('<b>', '').replace('</b>', '')
        image = search_image(title)
        snippet = get_blog_snippet(title)

        print(f"\n[{idx}] {title}")
        print(f"📍 주소: {place['roadAddress'] or place['address']}")
        print(f"📞 전화번호: {place['telephone'] or '정보 없음'}")
        print(f"📝 리뷰요약: {snippet}")
        print(f"🔗 링크: {place['link']}")
        print(f"🖼️ 이미지: {image if image else '없음'}")

if __name__ == "__main__":
    keyword = input("검색할 장소 키워드를 입력하세요: ")
    places = search_places(keyword)
    if places:
        print_cards(places)
    else:
        print("검색 결과가 없습니다.")