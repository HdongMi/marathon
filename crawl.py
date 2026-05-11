"""
마라톤 대회 크롤러 - marathongo.co.kr
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

BASE_URL = "https://marathongo.co.kr"
LIST_URL = f"{BASE_URL}/raceSchedule/domestic"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 공식 URL로 취급하지 않을 도메인
EXCLUDE_DOMAINS = [
    "marathongo.co.kr", "google.com", "naver.com", "daum.net",
    "kakao.com", "instagram.com", "facebook.com", "youtube.com",
    "twitter.com", "t.co", "namu.wiki", "wikipedia.org",
    "runable.me", "runningwikii.com", "kormarathon.com",
    "ahotu.com", "myresult.co.kr", "cashwalk.com",
]


def is_official_url(url: str) -> bool:
    """공식 홈페이지 URL인지 판단"""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().replace("www.", "")
        return not any(ex in host for ex in EXCLUDE_DOMAINS)
    except Exception:
        return False


# ── 기존 races.json에서 공식 URL 캐시 로드 ────────────────
def load_existing_official_urls() -> dict:
    """기존 races.json에서 title → official_url 매핑 로드 (재크롤링 방지)"""
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


# ── 구글 Custom Search API로 공식 URL 탐색 ────────────────
def search_official_url(title: str) -> str | None:
    """구글 검색으로 대회 공식 홈페이지 URL 탐색"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id  = os.environ.get("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        print("  ⚠️ GOOGLE_API_KEY 또는 GOOGLE_CSE_ID 없음 → 건너뜀")
        return None

    query = f"{title} 공식 홈페이지 마라톤 접수"
    url   = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx":  cse_id,
        "q":   query,
        "num": 5,
        "lr":  "lang_ko",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])

        for item in items:
            link = item.get("link", "")
            if is_official_url(link):
                print(f"  ✅ 공식 URL 발견: {link}")
                return link

        print(f"  ℹ️ 공식 URL 없음 (검색결과 {len(items)}개 모두 제외됨)")
        return None

    except Exception as e:
        print(f"  ⚠️ 구글 검색 오류: {e}")
        return None


def parse_courses(text: str) -> list[str]:
    courses = []
    patterns = ["100km", "70km", "50km", "42km", "풀", "하프", "21km", "10km", "5km", "3km", "VK", "Kids"]
    for p in patterns:
        if p.lower() in text.lower():
            courses.append(p)
    return courses


def parse_status(text: str) -> str:
    if "접수마감" in text or "마감" in text:
        return "마감"
    if "접수중" in text:
        return "접수중"
    if "접수전" in text:
        return "접수전"
    return "미정"


def parse_race_card(card) -> dict | None:
    try:
        text = card.get_text(" ", strip=True)
        link_tag = card.find("a", href=True)
        href = link_tag["href"] if link_tag else ""
        detail_url = BASE_URL + href if href.startswith("/") else href

        date_match = re.search(r"(\d+)월\s*(\d+)일", text)
        if not date_match:
            return None
        month = int(date_match.group(1))
        day   = int(date_match.group(2))
        year  = datetime.now().year
        if month < datetime.now().month - 1:
            year += 1
        date_str = f"{year}-{month:02d}-{day:02d}"

        dow_match = re.search(r"\((월|화|수|목|금|토|일)\)", text)
        dow = dow_match.group(1) if dow_match else ""

        title = ""
        if link_tag:
            title = link_tag.get_text(strip=True)
            title = re.sub(r"\d+월\s*\d+일.*?\)", "", title).strip()
            title = re.sub(r"(100km|50km|42km|풀|하프|21km|10km|5km|3km|VK|Kids)", "", title).strip()

        location = ""
        loc_match = re.search(r"\|\s*([^|]+)\s*\|", text)
        if loc_match:
            location = loc_match.group(1).strip()

        region = ""
        region_match = re.search(r"(서울|경기|충청|충남|충북|대전|경상|경남|경북|부산|대구|전라|전남|전북|광주|제주|강원|울산|세종|인천)", text)
        if region_match:
            region = region_match.group(1)

        reg_period = ""
        reg_match = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})", text)
        if reg_match:
            reg_period = f"{reg_match.group(1)} ~ {reg_match.group(2)}"

        courses = parse_courses(text)
        status  = parse_status(text)

        if not title or not date_str:
            return None

        return {
            "title":      title,
            "date":       date_str,
            "month":      month,
            "day":        day,
            "dow":        dow,
            "region":     region,
            "location":   location,
            "courses":    courses,
            "reg_period": reg_period,
            "status":     status,
            "detail_url": detail_url,
            "official_url": None,
        }
    except Exception as e:
        print(f"카드 파싱 오류: {e}")
        return None


def crawl() -> list[dict]:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 크롤링 시작: {LIST_URL}")

    # 기존 공식 URL 캐시 (API 호출 절약)
    url_cache = load_existing_official_urls()
    races = []

    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        links   = soup.find_all("a", href=re.compile(r"/raceDetail/domestic/"))
        seen    = set()

        for link in links:
            href = link.get("href", "")
            if href in seen:
                continue
            seen.add(href)

            container = link.find_parent("div") or link.find_parent("li") or link
            for _ in range(4):
                parent = container.find_parent(["div", "li", "article"])
                if parent and len(parent.get_text()) > len(container.get_text()):
                    container = parent
                    break

            race = parse_race_card(container)
            if race:
                races.append(race)

        races.sort(key=lambda r: r["date"])

        seen_keys = set()
        unique = []
        for r in races:
            key = f"{r['date']}_{r['title']}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(r)

        print(f"✅ 목록 {len(unique)}개 수집 완료 → 공식 URL 탐색 시작")

        # ── 공식 URL 자동 탐색 ────────────────────────────────
        for i, race in enumerate(unique):
            title = race["title"]

            # 캐시에 있으면 API 호출 안 함
            if title in url_cache:
                race["official_url"] = url_cache[title]
                print(f"  [{i+1}/{len(unique)}] {title} → 캐시 사용: {url_cache[title]}")
                continue

            print(f"  [{i+1}/{len(unique)}] {title} → 구글 검색 중...")
            official_url = search_official_url(title)
            race["official_url"] = official_url

            # API 호출 간격 (429 방지)
            time.sleep(1)

        return unique

    except Exception as e:
        print(f"❌ 크롤링 실패: {e}")
        return []


def save(races: list[dict]):
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source":     "https://marathongo.co.kr/raceSchedule/domestic",
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
