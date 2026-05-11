"""
마라톤 대회 크롤러 - marathongo.co.kr
실제 HTML 구조: <a href="/raceDetail/..."> 안에 날짜+코스+제목+장소+상태 텍스트 포함
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

EXCLUDE_DOMAINS = [
    "marathongo.co.kr", "google.com", "naver.com", "daum.net",
    "kakao.com", "instagram.com", "facebook.com", "youtube.com",
    "twitter.com", "t.co", "namu.wiki", "wikipedia.org",
    "runable.me", "runningwikii.com", "kormarathon.com",
    "ahotu.com", "myresult.co.kr", "cashwalk.com",
]


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
        print(f"[캐시] 기존 공식 URL {len(cache)}개 로드")
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
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            link = item.get("link", "")
            if is_official_url(link):
                print(f"  [URL] {link}")
                return link
        return None
    except Exception as e:
        print(f"  [검색오류] {e}")
        return None


def parse_courses(text: str) -> list[str]:
    result = []
    # 실제 텍스트 예: "하프10km5km" "풀하프11km" "100km50km" "10km5km가족코스(5km)"
    checks = [
        ("100km", ["100km"]),
        ("울트라", ["울트라"]),
        ("50km",  ["50km"]),
        ("풀",    ["풀코스", "풀하프", "풀,"]),
        ("하프",  ["하프", "21km"]),
        ("10km",  ["10km", "10K"]),
        ("5km",   ["5km",  "5K"]),
        ("3km",   ["3km"]),
    ]
    for label, kws in checks:
        if any(k in text for k in kws):
            result.append(label)
    return result


def parse_status(text: str) -> str:
    if "접수마감" in text or "마감" in text: return "마감"
    if "접수중" in text:                      return "접수중"
    if "접수전" in text:                      return "접수전"
    return "미정"


def parse_link(a_tag) -> dict | None:
    """
    <a href="/raceDetail/domestic/..."> 태그 하나에서 대회 정보 추출
    실제 텍스트 구조 예시:
    "5월 9일 (토) 10km 2026 나는 솔로런 서울 | 여의도공원 문화의마당 | 08:30 집결 | 2026 접수마감 2026.03.18 ~ 2026.04.15 KT ENA 런코리아 5월 9일 (토) 2026 나는 솔로런 서울 | ..."
    → 텍스트가 2번 반복되는 구조이므로 앞 절반만 사용
    """
    try:
        href = a_tag.get("href", "")
        if not href.startswith("/raceDetail/domestic/"):
            return None

        detail_url = BASE_URL + href
        raw_text   = a_tag.get_text(" ", strip=True)

        # 텍스트가 중복 반복되는 구조 → 앞 절반만 사용
        half = len(raw_text) // 2
        text = raw_text[:half].strip()
        if not text:
            text = raw_text

        # ── 날짜 파싱: "5월 9일" ──────────────────────────────
        date_match = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
        if not date_match:
            return None
        month = int(date_match.group(1))
        day   = int(date_match.group(2))
        year  = datetime.now().year
        if month < datetime.now().month - 1:
            year += 1
        date_str = f"{year}-{month:02d}-{day:02d}"

        # ── 요일 파싱 ─────────────────────────────────────────
        dow_match = re.search(r"[\(（](월|화|수|목|금|토|일)[\)）]", text)
        dow = dow_match.group(1) if dow_match else ""

        # ── 접수기간 파싱: "2026.03.18 ~ 2026.04.15" ─────────
        reg_match = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})", text)
        reg_period = f"{reg_match.group(1)} ~ {reg_match.group(2)}" if reg_match else ""

        # ── 상태 파싱 ─────────────────────────────────────────
        status = parse_status(text)

        # ── 장소 파싱: "| 장소 |" 구조 ──────────────────────
        pipes = re.findall(r"\|\s*([^|]+?)\s*(?=\||$)", text)
        location = pipes[0].strip() if pipes else ""

        # ── 지역 파싱 ─────────────────────────────────────────
        region_match = re.search(
            r"(서울|경기|충청|충남|충북|대전|경상|경남|경북|부산|대구|전라|전남|전북|광주|제주|강원|울산|세종|인천)",
            text
        )
        region = region_match.group(1) if region_match else ""

        # ── 코스 파싱 ─────────────────────────────────────────
        # 날짜 이전 텍스트 또는 날짜 직후 텍스트에서 추출
        before_date = text[:date_match.start()].strip()
        courses = parse_courses(before_date) or parse_courses(text)

        # ── 제목 파싱 ─────────────────────────────────────────
        # 날짜+요일 이후 ~ 첫 | 이전 텍스트
        after_date = text[date_match.end():]
        # 요일 괄호 제거
        after_date = re.sub(r"[\(（](월|화|수|목|금|토|일)[\)）]", "", after_date).strip()
        # 접수상태 제거
        after_date = re.sub(r"(접수중|접수마감|접수전|마감)", "", after_date).strip()
        # 연도 제거 ("2026")
        after_date = re.sub(r"\b\d{4}\b", "", after_date).strip()
        # | 이후 제거
        title_raw = after_date.split("|")[0].strip()
        # 코스 텍스트 제거
        title_raw = re.sub(r"(100km|50km|42km|풀코스|풀|하프|21km|10km|5km|3km|VK|Kids|기부\s*마라톤|울트라)", "", title_raw).strip()
        # 숫자+K 제거 (예: 37K, 24K, 12K, 11km)
        title_raw = re.sub(r"\d+[kKkm]+", "", title_raw).strip()
        title = title_raw.strip()

        if not title or len(title) < 2:
            return None

        return {
            "title":        title,
            "date":         date_str,
            "month":        month,
            "day":          day,
            "dow":          dow,
            "region":       region,
            "location":     location,
            "courses":      courses,
            "reg_period":   reg_period,
            "status":       status,
            "detail_url":   detail_url,
            "official_url": None,
        }

    except Exception as e:
        print(f"  [파싱오류] {e}")
        return None


def crawl() -> list[dict]:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 크롤링 시작: {LIST_URL}")
    url_cache = load_existing_official_urls()

    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        print(f"[응답] 상태코드: {resp.status_code} | 길이: {len(resp.text)}자")

        if "Host not in allowlist" in resp.text or len(resp.text) < 100:
            print("[차단] 접근이 차단되었습니다.")
            return []

        soup  = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=re.compile(r"/raceDetail/domestic/"))
        print(f"[링크] raceDetail 링크 수: {len(links)}개")

        seen  = set()
        races = []

        for a in links:
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)

            race = parse_link(a)
            if race:
                races.append(race)

        # 날짜순 정렬
        races.sort(key=lambda r: r["date"])

        # 중복 제거
        seen_keys = set()
        unique = []
        for r in races:
            key = f"{r['date']}_{r['title']}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(r)

        print(f"[완료] {len(unique)}개 대회 수집")

        # 공식 URL 탐색
        for i, race in enumerate(unique):
            title = race["title"]
            if title in url_cache:
                race["official_url"] = url_cache[title]
                continue
            race["official_url"] = search_official_url(title)
            time.sleep(1)

        return unique

    except Exception as e:
        print(f"[실패] {e}")
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
    print(f"[저장] races.json 저장 완료 ({len(races)}개)")


if __name__ == "__main__":
    races = crawl()
    if races:
        save(races)
    else:
        print("[경고] 수집된 데이터 없음 - 기존 races.json 유지")
