"""
마라톤 대회 크롤러 - marathongo.co.kr
상세페이지 Next.js API에서 공식 홈페이지 URL 추출
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
    # 트래킹/분석 도구
    "googletagmanager.com", "analytics.google.com",
    "doubleclick.net", "googlesyndication.com",
]


def is_valid_url(url: str) -> bool:
    """URL에 유니코드 한글이 포함된 경우 제외 (잘못 인코딩된 도메인)"""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        # 유니코드 이스케이프(\uXXXX)가 남아있는 경우 제외
        if "\\u" in url:
            return False
        # 퍼센트 인코딩된 한글이 도메인에 있는 경우 제외
        if re.search(r"%[0-9A-Fa-f]{2}", host):
            return False
        return True
    except Exception:
        return False


def is_official_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        if not is_valid_url(url):
            return False
        host = urlparse(url).netloc.lower().replace("www.", "")
        return bool(host) and not any(ex in host for ex in EXCLUDE_DOMAINS)
    except Exception:
        return False


def load_existing_urls() -> dict:
    """기존 races.json에서 title → official_url 캐시 로드"""
    cache = {}
    try:
        with open("races.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("races", []):
            if r.get("official_url"):
                cache[r["detail_url"]] = r["official_url"]
        print(f"[캐시] 기존 공식 URL {len(cache)}개 로드")
    except FileNotFoundError:
        pass
    return cache


def get_build_id(html: str) -> str | None:
    """Next.js buildId 추출"""
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
    return match.group(1) if match else None


def fetch_official_url(detail_url: str, build_id: str | None) -> str | None:
    """
    marathongo 상세페이지에서 공식 URL 추출
    1) Next.js JSON API 시도
    2) 실패 시 HTML에서 외부 링크 추출
    """
    slug = detail_url.split("/raceDetail/domestic/")[-1]

    # ── 방법 1: Next.js _next/data API ──────────────────────
    if build_id:
        api_url = f"{BASE_URL}/_next/data/{build_id}/raceDetail/domestic/{slug}.json"
        try:
            resp = requests.get(api_url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # pageProps 안에서 홈페이지 URL 탐색
                page_props = data.get("pageProps", {})
                race_data  = page_props.get("race", page_props.get("data", page_props))
                # 가능한 필드명들
                for key in ["homepageUrl", "homepage_url", "officialUrl", "official_url",
                            "websiteUrl", "website_url", "link", "url", "siteUrl"]:
                    url = race_data.get(key, "")
                    if url and is_official_url(url):
                        return url
                # 전체 JSON 문자열에서 http로 시작하는 외부 URL 탐색
                json_str = json.dumps(data)
                urls = re.findall(r'https?://[^\s"\'<>]+', json_str)
                for url in urls:
                    if is_official_url(url) and not url.endswith((".png", ".jpg", ".svg", ".ico")):
                        return url
        except Exception:
            pass

    # ── 방법 2: HTML 파싱으로 외부 링크 추출 ───────────────
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            # <a href="http..."> 중 공식 URL 찾기
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and is_official_url(href):
                    if not href.endswith((".png", ".jpg", ".svg", ".ico")):
                        return href

            # __NEXT_DATA__ 스크립트에서 URL 탐색
            next_data = soup.find("script", {"id": "__NEXT_DATA__"})
            if next_data:
                try:
                    nd = json.loads(next_data.string)
                    nd_str = json.dumps(nd)
                    urls = re.findall(r'https?://[^\s"\'<>]+', nd_str)
                    for url in urls:
                        if is_official_url(url) and not url.endswith((".png", ".jpg", ".svg", ".ico")):
                            return url
                except Exception:
                    pass
    except Exception:
        pass

    return None


def parse_courses(text: str) -> list[str]:
    result = []
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
    try:
        href = a_tag.get("href", "")
        if not href.startswith("/raceDetail/domestic/"):
            return None

        detail_url = BASE_URL + href
        raw_text   = a_tag.get_text(" ", strip=True)
        half       = len(raw_text) // 2
        text       = raw_text[:half].strip() if half > 10 else raw_text

        date_match = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
        if not date_match:
            return None

        month = int(date_match.group(1))
        day   = int(date_match.group(2))
        year  = datetime.now().year
        if month < datetime.now().month - 1:
            year += 1
        date_str = f"{year}-{month:02d}-{day:02d}"

        dow_match  = re.search(r"[\(（](월|화|수|목|금|토|일)[\)）]", text)
        dow        = dow_match.group(1) if dow_match else ""

        reg_match  = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})", text)
        reg_period = f"{reg_match.group(1)} ~ {reg_match.group(2)}" if reg_match else ""

        status   = parse_status(text)
        pipes    = re.findall(r"\|\s*([^|]+?)\s*(?=\|)", text)
        location = pipes[0].strip() if pipes else ""

        region_match = re.search(
            r"(서울|경기|충청|충남|충북|대전|경상|경남|경북|부산|대구|전라|전남|전북|광주|제주|강원|울산|세종|인천)",
            text
        )
        region = region_match.group(1) if region_match else ""
        before_date = text[:date_match.start()].strip()
        courses     = parse_courses(before_date) or parse_courses(text)

        after_date = text[date_match.end():]
        after_date = re.sub(r"[\(（](월|화|수|목|금|토|일)[\)）]", "", after_date).strip()
        after_date = re.sub(r"(접수중|접수마감|접수전|마감)", "", after_date).strip()
        after_date = re.sub(r"\b20\d{2}\b", "", after_date).strip()
        title_raw  = after_date.split("|")[0].strip()
        title_raw  = re.sub(
            r"(100km|50km|42km|풀코스|풀|하프|21km|10km|5km|3km|VK|Kids|기부\s*마라톤|울트라)",
            "", title_raw
        ).strip()
        title_raw  = re.sub(r"\d+[kKkm]+", "", title_raw).strip()
        title      = title_raw.strip()

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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 크롤링 시작")
    url_cache = load_existing_urls()

    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text

        print(f"[응답] {resp.status_code} | {len(html)}자")

        if "Host not in allowlist" in html or len(html) < 100:
            print("[차단] 접근 차단됨")
            return []

        # Next.js buildId 추출 (상세 API 호출에 필요)
        build_id = get_build_id(html)
        print(f"[빌드] Next.js buildId: {build_id}")

        soup  = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=re.compile(r"/raceDetail/domestic/"))
        print(f"[링크] {len(links)}개")

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

        races.sort(key=lambda r: r["date"])
        seen_keys = set()
        unique = []
        for r in races:
            key = f"{r['date']}_{r['title']}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(r)

        print(f"[파싱] {len(unique)}개 완료")

        # ── 공식 URL 탐색 ──────────────────────────────────
        print("[URL] 공식 URL 탐색 시작...")
        found = 0
        for i, race in enumerate(unique):
            detail_url = race["detail_url"]

            # 캐시에 있으면 스킵
            if detail_url in url_cache:
                race["official_url"] = url_cache[detail_url]
                found += 1
                continue

            url = fetch_official_url(detail_url, build_id)
            if url:
                race["official_url"] = url
                found += 1
                print(f"  [{i+1}/{len(unique)}] ✅ {race['title'][:15]} → {url}")
            else:
                print(f"  [{i+1}/{len(unique)}] ❌ {race['title'][:15]}")

            time.sleep(0.5)  # 상세 요청 간 딜레이

        print(f"[URL] 공식 URL 확보: {found}/{len(unique)}개")
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
    print(f"[저장] races.json {len(races)}개 저장 완료")


if __name__ == "__main__":
    races = crawl()
    if races:
        save(races)
        print(f"[성공] 총 {len(races)}개!")
    else:
        print("[경고] 데이터 없음 - 기존 유지")
