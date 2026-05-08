"""
마라톤 대회 크롤러 - marathongo.co.kr
매주 자동 실행 → races.json 업데이트
"""

import requests
from bs4 import BeautifulSoup
import json
import re
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


def parse_courses(text: str) -> list[str]:
    """코스 정보 파싱 (예: '풀하프10km5km' → ['풀', '하프', '10km', '5km'])"""
    courses = []
    patterns = ["100km", "70km", "50km", "42km", "풀", "하프", "21km", "10km", "5km", "3km", "VK", "Kids"]
    for p in patterns:
        if p.lower() in text.lower():
            courses.append(p)
    return courses


def parse_status(text: str) -> str:
    """접수 상태 파싱"""
    if "접수마감" in text or "마감" in text:
        return "마감"
    if "접수중" in text:
        return "접수중"
    if "접수전" in text:
        return "접수전"
    return "미정"


def parse_race_card(card) -> dict | None:
    """카드 하나에서 대회 정보 추출"""
    try:
        text = card.get_text(" ", strip=True)
        link_tag = card.find("a", href=True)
        href = link_tag["href"] if link_tag else ""
        detail_url = BASE_URL + href if href.startswith("/") else href

        # 날짜 추출 (예: "5월 9일 (토)")
        date_match = re.search(r"(\d+)월\s*(\d+)일", text)
        if not date_match:
            return None
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = datetime.now().year
        if month < datetime.now().month - 1:
            year += 1
        date_str = f"{year}-{month:02d}-{day:02d}"

        # 요일
        dow_match = re.search(r"\((월|화|수|목|금|토|일)\)", text)
        dow = dow_match.group(1) if dow_match else ""

        # 대회명 (링크 텍스트에서)
        title = ""
        if link_tag:
            title = link_tag.get_text(strip=True)
            # 날짜/코스 텍스트 제거
            title = re.sub(r"\d+월\s*\d+일.*?\)", "", title).strip()
            title = re.sub(r"(100km|50km|42km|풀|하프|21km|10km|5km|3km|VK|Kids)", "", title).strip()

        # 장소
        location = ""
        loc_match = re.search(r"\|\s*([^|]+)\s*\|", text)
        if loc_match:
            location = loc_match.group(1).strip()

        # 지역 (첫 번째 | 앞)
        region = ""
        region_match = re.search(r"(서울|경기|충청|충남|충북|대전|경상|경남|경북|부산|대구|전라|전남|전북|광주|제주|강원|울산|세종|인천)", text)
        if region_match:
            region = region_match.group(1)

        # 접수기간
        reg_period = ""
        reg_match = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})", text)
        if reg_match:
            reg_period = f"{reg_match.group(1)} ~ {reg_match.group(2)}"

        # 코스
        courses = parse_courses(text)

        # 상태
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

        # 대회 링크들 수집 (raceDetail 포함된 a 태그)
        links = soup.find_all("a", href=re.compile(r"/raceDetail/domestic/"))
        seen = set()

        for link in links:
            href = link.get("href", "")
            if href in seen:
                continue
            seen.add(href)

            # 부모 컨테이너에서 정보 추출
            container = link.find_parent("div") or link.find_parent("li") or link
            # 더 넓은 컨텍스트를 위해 상위 여러 단계 탐색
            for _ in range(4):
                parent = container.find_parent(["div", "li", "article"])
                if parent and len(parent.get_text()) > len(container.get_text()):
                    container = parent
                    break

            race = parse_race_card(container)
            if race:
                races.append(race)

        # 날짜순 정렬
        races.sort(key=lambda r: r["date"])

        # 중복 제거 (같은 제목+날짜)
        seen_keys = set()
        unique = []
        for r in races:
            key = f"{r['date']}_{r['title']}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(r)

        print(f"✅ 총 {len(unique)}개 대회 수집 완료")
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
