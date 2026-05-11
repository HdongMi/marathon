import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
from datetime import datetime

# 설정
BASE_URL = "https://marathongo.co.kr"
LIST_URL = f"{BASE_URL}/schedule/schedule_list.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

EXCLUDE_DOMAINS = [
    "marathongo.co.kr", "roadrun.co.kr", "marathon.pe.kr",
    "google.com", "naver.com", "daum.net", "kakao.com"
]

def is_official_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().replace("www.", "")
        return bool(host) and not any(ex in host for ex in EXCLUDE_DOMAINS)
    except:
        return False

def parse_courses(text: str) -> list:
    courses = []
    patterns = [("풀", ["풀코스", "풀"]), ("하프", ["하프"]), ("10km", ["10km", "10k"]), ("5km", ["5km", "5k"]), ("울트라", ["울트라"])]
    for label, keywords in patterns:
        if any(k in text for k in keywords):
            courses.append(label)
    return courses

def parse_region(location: str) -> str:
    regions = ["서울", "경기", "인천", "강원", "충북", "충남", "대전", "세종", "전북", "전남", "광주", "경북", "대구", "경남", "부산", "울산", "제주"]
    for r in regions:
        if r in location: return r
    return ""

def determine_status(date_str: str) -> str:
    try:
        race_date = datetime.strptime(date_str, "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        diff = (race_date - today).days
        if diff < 0: return "마감"
        elif diff <= 30: return "접수중"
        else: return "접수전"
    except:
        return "미정"

def search_official_url(title: str) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    if not api_key or not cse_id: return None

    query = f"{title} 공식 홈페이지 마라톤 접수"
    params = {"key": api_key, "cx": cse_id, "q": query, "num": 3, "lr": "lang_ko"}
    try:
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        items = resp.json().get("items", [])
        for item in items:
            link = item.get("link", "")
            if is_official_url(link): return link
    except:
        pass
    return None

def crawl():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 마라톤고 크롤링 시작...")
    all_races = []
    
    # 최근 3페이지 수집 (약 45개 대회)
    for page in range(1, 4):
        print(f"  📄 {page}페이지 분석 중...", end="\r")
        try:
            resp = requests.get(LIST_URL, params={"page": page}, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 마라톤고의 실제 테이블 구조 타겟팅
            # tr 중 class가 없는 행들이 실제 데이터 행입니다.
            rows = soup.select("table tr")
            
            page_count = 0
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 5: continue

                # 1. 날짜 (형식: 2026-05-11)
                date_raw = cols[0].get_text(strip=True)
                if not re.match(r"\d{4}-\d{2}-\d{2}", date_raw): continue

                # 2. 제목 및 상세 링크
                title_tag = cols[1].find("a")
                if not title_tag: continue
                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                detail_url = f"{BASE_URL}/schedule/{href}" if "http" not in href else href

                # 3. 장소 및 코스
                location = cols[2].get_text(strip=True)
                course_raw = cols[3].get_text(strip=True)

                all_races.append({
                    "title": title,
                    "date": date_raw,
                    "region": parse_region(location),
                    "location": location,
                    "courses": parse_courses(course_raw),
                    "status": determine_status(date_raw),
                    "detail_url": detail_url,
                    "official_url": None,
                    "source": "marathongo"
                })
                page_count += 1
            
            print(f"  📄 {page}페이지 완료 ({page_count}개 수집)")
            time.sleep(0.5)
        except Exception as e:
            print(f"\n  ❌ {page}페이지 오류: {e}")
            
    # 중복 제거 (날짜와 제목 기준)
    unique_races = []
    seen = set()
    for r in all_races:
        key = f"{r['date']}_{r['title']}"
        if key not in seen:
            seen.add(key)
            unique_races.append(r)

    print(f"\n✅ 수집 완료: 총 {len(unique_races)}개")
    
    # 공식 URL 검색 (API 키가 있을 경우만 작동)
    if os.environ.get("GOOGLE_API_KEY"):
        print("🔍 공식 URL 탐색 시작...")
        for race in unique_races:
            race["official_url"] = search_official_url(race["title"])
            time.sleep(0.5)

    return unique_races

def save(races):
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(races),
        "races": races
    }
    with open("races.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 races.json 저장 완료")

if __name__ == "__main__":
    data = crawl()
    if data:
        save(data)
    else:
        print("⚠️ 수집된 데이터가 없습니다. 사이트 구조를 다시 확인하세요.")
