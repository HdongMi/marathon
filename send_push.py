#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────
# send_push.py
# GitHub Actions 크롤링 후 새 대회 감지 시 실행
#
# 필요한 GitHub Secrets:
#   FIREBASE_SERVICE_ACCOUNT  ← Firebase 콘솔 > 프로젝트 설정 >
#                                서비스 계정 > 새 비공개 키 생성 (JSON 전체)
#   FIREBASE_PROJECT_ID       ← Firebase 프로젝트 ID
# ─────────────────────────────────────────────────────────

import json
import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore, messaging

# ── Firebase 초기화 ──────────────────────────────────────
def init_firebase():
    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not service_account_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT secret이 없습니다.")
        sys.exit(1)

    cred = credentials.Certificate(json.loads(service_account_json))
    firebase_admin.initialize_app(cred)

# ── Firestore에서 모든 FCM 토큰 가져오기 ────────────────
def get_all_tokens():
    db = firestore.client()
    docs = db.collection("fcm_tokens").stream()
    tokens = [doc.to_dict().get("token") for doc in docs]
    return [t for t in tokens if t]  # None 제거

# ── 새 대회 감지 ─────────────────────────────────────────
def find_new_races(old_path="races_prev.json", new_path="races.json"):
    try:
        with open(old_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        old_titles = {r["title"] for r in old_data.get("races", [])}
    except FileNotFoundError:
        # 첫 실행이면 비교 대상 없음 → 새 대회 없음으로 처리
        return []

    with open(new_path, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    new_races = [
        r for r in new_data.get("races", [])
        if r["title"] not in old_titles
    ]
    return new_races

# ── FCM 멀티캐스트 발송 ───────────────────────────────────
def send_push(tokens, new_races):
    if not tokens:
        print("📭 등록된 토큰이 없습니다.")
        return
    if not new_races:
        print("✅ 새로운 대회가 없습니다. 푸시 발송 안 함.")
        return

    count = len(new_races)
    if count == 1:
        title = "🏃 새 대회가 등록됐어요!"
        body  = f"{new_races[0]['title']} — {new_races[0].get('date', '')} {new_races[0].get('region', '')}"
    else:
        title = f"🏃 새 대회 {count}개가 등록됐어요!"
        body  = ", ".join(r["title"] for r in new_races[:3])
        if count > 3:
            body += f" 외 {count - 3}개"

    print(f"📤 푸시 발송: {title}")
    print(f"   내용: {body}")
    print(f"   대상 토큰 수: {len(tokens)}")

    # 500개씩 나눠서 발송 (FCM 멀티캐스트 한도)
    batch_size = 500
    success_count = 0
    fail_count = 0

    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        message = messaging.MulticastMessage(
            tokens=batch,
            notification=messaging.Notification(title=title, body=body),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="runnu_races",
                    icon="ic_notification",
                    click_action="FLUTTER_NOTIFICATION_CLICK"
                )
            ),
            data={
                "type":  "new_race",
                "count": str(count),
                "title": new_races[0]["title"] if count == 1 else f"{count}개 신규"
            }
        )
        response = messaging.send_each_for_multicast(message)
        success_count += response.success_count
        fail_count    += response.failure_count

        # 실패한 토큰 정리 (선택)
        clean_failed_tokens(batch, response)

    print(f"✅ 발송 완료 — 성공: {success_count}, 실패: {fail_count}")

# ── 만료된 토큰 Firestore에서 삭제 ──────────────────────
def clean_failed_tokens(tokens, response):
    db = firestore.client()
    for idx, result in enumerate(response.responses):
        if not result.success:
            error_code = result.exception.code if result.exception else ""
            # 토큰 만료 또는 등록 취소된 경우 삭제
            if error_code in ("registration-token-not-registered", "invalid-argument"):
                try:
                    db.collection("fcm_tokens").document(tokens[idx]).delete()
                    print(f"🗑️ 만료 토큰 삭제: {tokens[idx][:20]}...")
                except Exception:
                    pass

# ── 메인 ─────────────────────────────────────────────────
if __name__ == "__main__":
    init_firebase()
    new_races = find_new_races()
    if new_races:
        print(f"🆕 새 대회 {len(new_races)}개 발견: {[r['title'] for r in new_races]}")
        tokens = get_all_tokens()
        send_push(tokens, new_races)
    else:
        print("✅ 새로운 대회 없음.")
