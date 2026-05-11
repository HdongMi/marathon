"""
마라톤 대회 크롤러 - marathongo.co.kr
매주 자동 실행 → races.json 업데이트
+ 각 대회 상세페이지에서 공식 URL / 참가비 / 연락처 추가 크롤링
"""

import requests
from bs4 import BeautifulSoup
import json
import re
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

# marathongo 자체 도메인은 공식 URL로 취급 안 함
EXCLUDE_DOMAINS = [
    "marathongo.co.kr",
    "google.com", "naver.com", "kakao.com",
    "instagram.com", "facebook.com", "youtube.com",
    "twitter.com", "t.co",
]


def is_official_url(url: str) -> bool:
    """공식 홈페이지 URL인지 판단 (SNS·검색엔진 제외)"""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().replace("www.", "")
        return not any(ex in host for ex in EXCLUDE_DOMAINS)
    except Exception:
        return False


def crawl_detail(detail_url: str) -> dict:
    """
    마라톤고 상세페이지에서 추가 정보 크롤링
    반환: {"official_url": str, "fees": [...], "contact": {...}}
    """
    result = {"official_url": None, "fees": [], "contact": {}}
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # ── 1. 공식 홈페이지 URL 추출 ──────────────────────────
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("http") and is_official_url(href):
                result["official_url"] = href
                break

        # ── 2. 참가비 추출 ──────────────────────────────────────
        # 패턴: "풀코스 50,000원" / "하프 40,000원" / "10km 30,000원" 등
        fee_patterns = [
            r"(풀코스|풀|하프|10\s*km|10K|5\s*km|5K|3\s*km|울트라|100\s*km|50\s*km|42\s*km|21\s*km|기부|트레일)[^\d]{0,10}([\d,]+)\s*원",
        ]
        seen_courses = set()
        for pattern in fee_patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                course = m.group(1).strip()
                price  = m.group(2).strip() + "원"
                if course not in seen_courses:
                    seen_courses.add(course)
                    result["fees"].append({"course": course, "price": price})

        # ── 3. 연락처 추출 ──────────────────────────────────────
        # 전화번호: 02-xxxx-xxxx / 010-xxxx-xxxx / 0xx-xxx-xxxx
        phone_match = re.search(r"(\d{2,3}-\d{3,4}-\d{4})", text)
        if phone_match:
            result["contact"]["phone"] = phone_match.group(1)

        # 이메일
        email_match = re.search(r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", text)
        if email_match:
            result["contact"]["email"] = email_match.group(1)

    except Exception as e:
        print(f"  ⚠️ 상세 크롤링 실패 ({detail_url}): {e}")

    return result


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
        day = int(date_match.group(2))
        year = datetime.now().year
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
        status = parse_status(text)

        if not title or not date_str:
            return None

        return {
            "title": title,
            "date": date_str,
            "month": month,
            "day": day,
            "dow": dow,
            "region": region,
            "location": location,
            "courses": courses,
            "reg_period": reg_period,
            "status": status,
            "detail_url": detail_url,
            # 상세 크롤링으로 채워질 필드 (기본값)
            "official_url": None,
            "fees": [],
            "contact": {},
        }
    except Exception as e:
        print(f"카드 파싱 오류: {e}")
        return None


def crawl() -> list[dict]:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 크롤링 시작: {LIST_URL}")
    races = []

    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.find_all("a", href=re.compile(r"/raceDetail/domestic/"))
        seen = set()

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

        print(f"✅ 목록 {len(unique)}개 수집 완료 → 상세 페이지 크롤링 시작")

        # ── 각 대회 상세페이지 개별 크롤링 ──────────────────────
        for i, race in enumerate(unique):
            if not race.get("detail_url"):
                continue
            print(f"  [{i+1}/{len(unique)}] {race['title']} 상세 크롤링 중...")
            detail = crawl_detail(race["detail_url"])
            race["official_url"] = detail["official_url"]
            race["fees"]         = detail["fees"]
            race["contact"]      = detail["contact"]
            time.sleep(0.5)  # 서버 부하 방지

        return unique

    except Exception as e:
        print(f"❌ 크롤링 실패: {e}")
        return []


def save(races: list[dict]):
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "https://marathongo.co.kr/raceSchedule/domestic",
        "total": len(races),
        "races": races,
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
