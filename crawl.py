name: 🏃 마라톤 대회 정보 자동 업데이트
on:
  schedule:
    - cron: '0 0 * * 1'
  workflow_dispatch:

jobs:
  crawl-and-update:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: 📥 저장소 체크아웃
        uses: actions/checkout@v4

      - name: 🗂️ 이전 대회 데이터 백업
        run: |
          if [ -f races.json ]; then
            cp races.json races_prev.json
            echo "✅ races_prev.json 생성 완료"
          else
            echo "⚠️ races.json 없음 (첫 실행)"
          fi

      - name: 🔍 marathongo 접근 테스트
        run: |
          echo "=== curl 접근 테스트 ==="
          curl -s -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36" \
            -H "Accept-Language: ko-KR,ko;q=0.9" \
            -H "Accept: text/html,application/xhtml+xml" \
            -L --max-time 15 \
            https://marathongo.co.kr/raceSchedule/domestic \
            | head -c 500
          echo ""
          echo "=== 테스트 완료 ==="

      - name: 🐍 Python 3.11 설정
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 📦 의존성 설치
        run: pip install requests beautifulsoup4 lxml firebase-admin

      - name: 🕷️ 크롤러 실행
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          GOOGLE_CSE_ID: ${{ secrets.GOOGLE_CSE_ID }}
        run: python crawl.py

      - name: 📊 결과 확인
        run: |
          echo "=== races.json 미리보기 ==="
          head -50 races.json
          echo "=== 총 대회 수 ==="
          python -c "import json; d=json.load(open('races.json')); print(f'총 {d[\"total\"]}개 대회')"

      - name: 🔔 새 대회 감지 & 푸시 알림 발송
        env:
          FIREBASE_SERVICE_ACCOUNT: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          FIREBASE_PROJECT_ID: ${{ secrets.FIREBASE_PROJECT_ID }}
        run: python send_push.py

      - name: 💾 변경사항 자동 커밋
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "🏃 [자동] 마라톤 대회 정보 업데이트 - $(date '+%Y년 %m월 %d일')"
          file_pattern: races.json
          commit_user_name: "marathon-bot"
          commit_user_email: "bot@marathon-app.github"
