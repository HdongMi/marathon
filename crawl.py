import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
from datetime import datetime

BASE_URL  = "https://marathongo.co.kr"
LIST_URL  = f"{BASE_URL}/schedule/schedule_list.php"
YEAR      = datetime.now().year

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

EXCLUDE_DOMAINS = [
    "roadrun.co.kr", "marathon.pe.kr", "marathongo.co.kr",
    "google.com", "naver.com", "daum.net",
    "kakao.com", "instagram.com", "facebook.com",
    "youtube.com", "twitter.com", "t.co",
    "namu.wiki", "wikipedia.org",
    "runable.me", "runningwikii.com", "kormarathon.com",
    "ahotu.com", "myresult.co.kr", "cashwalk.com",
]

DOW_MAP = {"월": "월", "화": "화", "수": "수", "목": "목", "금": "금", "토": "토", "일": "일"}


def is_official_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().replace("www.", "")
        return bool(host) and not any(ex in host for ex in EXCLUDE_DOMAINS)
    except Exception:
        return False


def load_existing_official_urls() -> dict:
    cache = {}
    try:
        with open("races.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("races", []):
            if r.get("official_url"):
                cache[r["title"]] = r["official_url"]
        print(f"📦 기존 공식 URL 캐시 {len(cache)}개 로드")
    except FileNotFoundError:
        pass
    return cache


def search_official_url(title: str) -> str | None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id  = os.environ.get("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return None

    query  = f"{title} 공식 홈페이지 마라톤 접수"
    params = {"key": api_key, "cx": cse_id, "q": query, "num": 5, "lr": "lang_ko"}
    try:
        resp  = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            link = item.get("link", "")
            if is_official_url(link):
                print(f"  ✅ 공식 URL: {link}")
                return link
        print(f"  ℹ️ 공식 URL 없음")
        return None
    except Exception as e:
        print(f"  ⚠️ 구글 검색 오류: {e}")
        return None


def parse_courses(text: str) -> list[str]:
    """코스 파싱"""
    courses = []
    patterns = [
        ("100km", ["100km", "100 km"]),
        ("울트라", ["울트라"]),
        ("50km",  ["50km", "50 km"]),
        ("풀",    ["풀코스", "42.195km", "42km", "마라톤,하프", "풀"]),
        ("하프",  ["하프", "21km", "21.0975km"]),
        ("10km",  ["10km", "10 km", "10k"]),
        ("5km",   ["5km", "5 km", "5k"]),
        ("3km",   ["3km", "3 km", "3k"]),
    ]
    text_lower = text.lower()
    for label, keywords in patterns:
        if any(k.lower() in text_lower for k in keywords):
            if label not in courses:
                courses.append(label)
    return courses


def parse_region(location: str) -> str:
    """장소에서 지역 추출"""
    regions = ["서울", "경기", "인천", "강원", "충북", "충남", "대전", "세종",
               "전북", "전남", "광주", "경북", "대구", "경남", "부산", "울산", "제주"]
    for r in regions:
        if r in location:
            return r
    return ""


def fetch_page(page: int) -> str:
    """marathongo.co.kr 목록 페이지 가져오기 (UTF-8 디코딩)"""
    params = {"page": page}
    resp = requests.get(LIST_URL, headers=HEADERS, params=params, timeout=15)
    resp.encoding = "utf-8"
    return resp.text


def parse_list_page(html: str) -> list[dict]:
    """목록 페이지에서 대회 파싱 (테이블 구조)"""
    soup  = BeautifulSoup(html, "html.parser")
    races = []

    # 마라톤고 구조: table 내의 tr 행 단위로 데이터가 존재
    rows = soup.select("table.table_list tbody tr")
    if not rows:
        rows = soup.select("table tr")  # 혹시 모를 대비책

    for row in rows:
        try:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # 날짜 추출 (예: 2024-05-19)
            date_raw = cols[0].get_text(strip=True)
            if not re.match(r"\d{4}-\d{2}-\d{2}", date_raw):
                continue
                
            date_obj = datetime.strptime(date_raw, "%Y-%m-%d")
            month = date_obj.month
            day = date_obj.day
            dow = ""  # 마라톤고 리스트에서는 기본적으로 요일을 제공하지 않음

            # 대회명 및 상세 URL 추출
            title_tag = cols[1].find("a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            
            href = title_tag.get("href", "")
            if href.startswith("http"):
                detail_url = href
            else:
                detail_url = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"

            # 장소
            location = cols[2].get_text(strip=True)
            region = parse_region(location)

            # 코스
            course_raw = cols[3].get_text(strip=True)
            courses = parse_courses(course_raw)

            # 주최/연락처
            phone = cols[4].get_text(strip=True)
            
            # 리스트에 공식 URL이 없으므로 None (이후 기존 로직인 구글 검색에서 채움)
            official_url = None

            if not title:
                continue

            races.append({
                "title":        title,
                "date":         date_raw,
                "month":        month,
                "day":          day,
                "dow":          dow,
                "region":       region,
                "location":     location,
                "courses":      courses,
                "reg_period":   "",
                "status":       "미정",
                "detail_url":   detail_url,
                "official_url": official_url,
                "contact": {"phone": phone} if phone else {},
            })

        except Exception as e:
            print(f"  파싱 오류: {e}")
            continue

    return races


def determine_status(date_str: str) -> str:
    """날짜 기준으로 상태 추정"""
    try:
        race_date = datetime.strptime(date_str, "%Y-%m-%d")
        today     = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        diff      = (race_date - today).days
        if diff < 0:
            return "마감"
        elif diff <= 30:
            return "접수중"
        else:
            return "접수전"
    except Exception:
        return "미정"


def crawl() -> list[dict]:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 크롤링 시작: {LIST_URL}")
    url_cache = load_existing_official_urls()
    all_races = []

    # 마라톤고는 페이지네이션을 사용합니다. 최근 데이터 확보를 위해 1~3페이지 수집 (필요시 숫자 조정)
    pages_to_fetch = list(range(1, 4)) 

    for page in pages_to_fetch:
        print(f"  📄 {page}페이지 수집 중...")
        try:
            html  = fetch_page(page)
            races = parse_list_page(html)
            all_races.extend(races)
            print(f"     → {len(races)}개 수집")
            time.sleep(1)
        except Exception as e:
            print(f"     ❌ 실패: {e}")
            continue

    # 중복 제거 (같은 url 기준)
    seen_urls = set()
    unique = []
    for r in all_races:
        key = r["detail_url"]
        if key not in seen_urls:
            seen_urls.add(key)
            # 상태 추정
            r["status"] = determine_status(r["date"])
            unique.append(r)

    # 날짜순 정렬
    unique.sort(key=lambda r: r["date"])

    print(f"\n✅ 총 {len(unique)}개 대회 수집 완료 → 공식 URL 탐색 시작")

    # 공식 URL 자동 탐색
    for i, race in enumerate(unique):
        title = race["title"]

        # 이미 목록에서 공식 URL 확보한 경우
        if race.get("official_url"):
            print(f"  [{i+1}/{len(unique)}] {title[:20]} → 목록에서 확보")
            continue

        # 캐시 확인
        if title in url_cache:
            race["official_url"] = url_cache[title]
            print(f"  [{i+1}/{len(unique)}] {title[:20]} → 캐시 사용")
            continue

        # 구글 검색
        print(f"  [{i+1}/{len(unique)}] {title[:20]} → 구글 검색 중...")
        race["official_url"] = search_official_url(title)
        time.sleep(1)

    return unique


def save(races: list[dict]):
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source":     "https://marathongo.co.kr/schedule/schedule_list.php",
        "total":      len(races),
        "races":      races,
    }
    with open("races.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 races.json 저장 완료 ({len(races)}개)")


if __name__ == "__main__":
    races = crawl()
    if races:
        save(races)
    else:
        print("⚠️ 수집된 데이터 없음 - 기존 races.json 유지")
