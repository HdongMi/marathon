"""
마라톤 대회 크롤러 - roadrun.co.kr (marathon.pe.kr)
매주 자동 실행 → races.json 업데이트
+ 구글 Custom Search API로 공식 홈페이지 URL 자동 탐색
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
from datetime import datetime

BASE_URL  = "http://www.roadrun.co.kr"
LIST_URL  = f"{BASE_URL}/schedule/list.php"
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
    "roadrun.co.kr", "marathon.pe.kr",
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
        ("풀",    ["풀코스", "42.195km", "42km", "마라톤,하프"]),
        ("하프",  ["하프", "21km", "21.0975km"]),
        ("10km",  ["10km", "10 km"]),
        ("5km",   ["5km", "5 km"]),
        ("3km",   ["3km", "3 km"]),
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


def fetch_page(year: int, month: int | None = None) -> str:
    """roadrun.co.kr 목록 페이지 가져오기 (EUC-KR 디코딩)"""
    params = {"year": year}
    if month:
        params["month"] = month
    resp = requests.get(LIST_URL, headers=HEADERS, params=params, timeout=15)
    resp.encoding = "euc-kr"
    return resp.text


def parse_list_page(html: str, year: int) -> list[dict]:
    """목록 페이지에서 대회 파싱"""
    soup  = BeautifulSoup(html, "html.parser")
    races = []

    # roadrun.co.kr 구조: 날짜/대회명/장소/연락처가 텍스트로 묶여있음
    # bold 태그로 감싸진 대회명 링크 찾기
    race_links = soup.find_all("a", href=re.compile(r"view\.php\?no=\d+"))

    for link in race_links:
        try:
            title = link.get_text(strip=True)
            if not title or len(title) < 2:
                continue

            # no= 파라미터로 상세 URL 구성
            no_match = re.search(r"no=(\d+)", link.get("href", ""))
            if not no_match:
                continue
            race_no    = no_match.group(1)
            detail_url = f"{BASE_URL}/schedule/view.php?no={race_no}"

            # 부모 컨테이너에서 전체 텍스트 추출
            parent = link.find_parent("td") or link.find_parent("li") or link.find_parent("div")
            if not parent:
                continue
            block_text = parent.get_text(" ", strip=True)

            # 날짜 추출: "5/10(일)" 또는 "5/10" 형태
            date_match = re.search(r"(\d{1,2})/(\d{1,2})\s*[\(\（]?(월|화|수|목|금|토|일)?[\)\）]?", block_text)
            if not date_match:
                continue
            month = int(date_match.group(1))
            day   = int(date_match.group(2))
            dow   = date_match.group(3) or ""

            # 연도 보정 (현재 월보다 많이 이전이면 내년)
            cur_month = datetime.now().month
            race_year = year
            if month < cur_month - 2:
                race_year = year + 1

            date_str = f"{race_year}-{month:02d}-{day:02d}"

            # 코스 추출 (대회명 다음 줄 또는 같은 블록)
            courses = parse_courses(block_text)

            # 장소 추출: 전화번호 앞에 오는 텍스트
            location = ""
            loc_match = re.search(r"(?:풀|하프|10km|5km|3km|울트라|100km|50km)[,\s]*([가-힣\s]+(?:구|동|시|군|읍|면|로|길|공원|운동장|경기장|광장|체육관|대학교|학교)[가-힣\s\d]*)", block_text)
            if loc_match:
                location = loc_match.group(1).strip()[:30]

            region = parse_region(location) or parse_region(block_text)

            # 공식 홈페이지 URL (목록에 포함된 경우)
            official_url = None
            for a in (parent.find_all("a", href=True) if parent else []):
                href = a["href"]
                if href.startswith("http") and is_official_url(href):
                    official_url = href
                    break

            # 전화번호
            phone_match = re.search(r"(\d{2,3}-\d{3,4}-\d{4})", block_text)
            phone = phone_match.group(1) if phone_match else ""

            if not title:
                continue

            races.append({
                "title":        title,
                "date":         date_str,
                "month":        month,
                "day":          day,
                "dow":          dow,
                "region":       region,
                "location":     location,
                "courses":      courses,
                "reg_period":   "",          # roadrun에는 접수기간 별도 없음
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

    # 현재 연도 전체 크롤링 (월별로 나눠서 요청)
    cur_month = datetime.now().month
    months_to_fetch = list(range(cur_month, 13))  # 이번달 ~ 12월

    for month in months_to_fetch:
        print(f"  📅 {YEAR}년 {month}월 수집 중...")
        try:
            html  = fetch_page(YEAR, month)
            races = parse_list_page(html, YEAR)
            all_races.extend(races)
            print(f"     → {len(races)}개 수집")
            time.sleep(1)
        except Exception as e:
            print(f"     ❌ 실패: {e}")
            continue

    # 중복 제거 (같은 no 기준)
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
        "source":     "http://www.roadrun.co.kr/schedule/list.php",
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
