/* ═══════════════════════════════════════
   app.js  —  런뉴 공통 JS 로직
   ═══════════════════════════════════════ */

const KAKAO_KEY   = '6dc88714f7ade5205b72b9a2a991d530';
const GOOGLE_CID  = '372085184739-6vp986ob9sa277cvcdfeill8se8i9hpg.apps.googleusercontent.com';
const MON = ['','JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

/* ── 전역 상태 ── */
let allRaces    = [];
let currentUser = null;
let wishlist    = [];
let openOnly    = false;

/* ════════════════════════════════
   인증
════════════════════════════════ */
function initKakao() {
  if (window.Kakao && !Kakao.isInitialized()) Kakao.init(KAKAO_KEY);
}

function loginKakao() {
  initKakao();
  Kakao.Auth.login({
    success() {
      Kakao.API.request({
        url: '/v2/user/me',
        success(res) {
          const k = res.kakao_account;
          afterLogin({
            name:     k?.profile?.nickname || '카카오 유저',
            email:    k?.email || '',
            photo:    k?.profile?.profile_image_url || '',
            provider: 'kakao'
          });
        },
        fail(e) { alert('카카오 정보 오류: ' + JSON.stringify(e)); }
      });
    },
    fail(e) { alert('카카오 로그인 실패: ' + JSON.stringify(e)); }
  });
}

function loginGoogle() {
  google.accounts.id.initialize({
    client_id: GOOGLE_CID,
    callback(res) {
      const p = JSON.parse(atob(res.credential.split('.')[1]));
      afterLogin({
        name:     p.name  || 'Google 유저',
        email:    p.email || '',
        photo:    p.picture || '',
        provider: 'google'
      });
    },
    ux_mode: 'popup'
  });
  google.accounts.id.prompt(n => {
    if (n.isNotDisplayed() || n.isSkippedMoment()) {
      /* One Tap 실패 시 OAuth 팝업 fallback */
      const params = new URLSearchParams({
        client_id:    GOOGLE_CID,
        redirect_uri: location.origin + '/oauth/google',   // 더미 URI (토큰 파싱용)
        response_type:'token',
        scope:        'openid email profile',
        prompt:       'select_account'
      });
      const popup = window.open(
        'https://accounts.google.com/o/oauth2/v2/auth?' + params,
        'glogin', 'width=480,height=600'
      );
      const t = setInterval(() => {
        try {
          if (popup.closed) { clearInterval(t); return; }
          const url = popup.location.href;
          if (url.includes('access_token')) {
            clearInterval(t); popup.close();
            const hash = new URLSearchParams(url.split('#')[1]);
            fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
              headers: { Authorization: 'Bearer ' + hash.get('access_token') }
            }).then(r => r.json()).then(u => afterLogin({
              name: u.name || 'Google 유저', email: u.email || '',
              photo: u.picture || '', provider: 'google'
            }));
          }
        } catch(e) {}
      }, 300);
    }
  });
}

function skipLogin() {
  /* 비로그인 — 대회목록만 이용 가능 */
  localStorage.removeItem('runnu_user');
  currentUser = null;
  wishlist    = [];
  goToList();
}

function afterLogin(user) {
  currentUser = user;
  localStorage.setItem('runnu_user', JSON.stringify(user));
  wishlist = JSON.parse(localStorage.getItem('runnu_wish_' + (user.email || 'guest')) || '[]');
  goToList();
}

function doLogout() {
  if (!confirm('로그아웃 하시겠어요?')) return;
  if (currentUser?.provider === 'kakao' && window.Kakao?.Auth) Kakao.Auth.logout(() => {});
  currentUser = null;
  localStorage.removeItem('runnu_user');
  wishlist = [];
  window.location.href = 'login.html';
}

/* 로그인 후 이동 — 페이지 방식이라 href */
function goToList() { window.location.href = 'index.html'; }

/* ════════════════════════════════
   로그인 세션 복원
════════════════════════════════ */
function restoreSession() {
  const saved = localStorage.getItem('runnu_user');
  if (saved) {
    currentUser = JSON.parse(saved);
    wishlist = JSON.parse(localStorage.getItem('runnu_wish_' + (currentUser.email || 'guest')) || '[]');
    return true;
  }
  return false;
}

/* ════════════════════════════════
   데이터 로드
════════════════════════════════ */
async function loadRaces() {
  try {
    const res  = await fetch('races.json?t=' + Date.now());
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    allRaces   = data.races || [];
    const banner = document.getElementById('updateTime');
    if (banner) banner.textContent = data.updated_at
      ? '마지막 업데이트: ' + data.updated_at + ' · 매주 월요일 자동 갱신'
      : '데이터 로드 완료';
    return allRaces;
  } catch(e) {
    console.error('races.json 로드 실패:', e);
    return [];
  }
}

/* ════════════════════════════════
   필터 / 렌더 유틸
════════════════════════════════ */
function applyFilter() {
  const checked = [...document.querySelectorAll('.c-check input:checked')].map(el => el.value);
  let list = allRaces.slice();
  if (checked.length) {
    list = list.filter(r => {
      const cs = (r.courses || []).map(c => c.toLowerCase());
      return checked.some(sel => {
        if (sel === '풀')   return cs.some(c => c === '풀'  || c.includes('42'));
        if (sel === '하프') return cs.some(c => c === '하프' || c.includes('21'));
        if (sel === '10km') return cs.some(c => c.includes('10'));
        if (sel === '5km')  return cs.some(c => c === '5km' || c === '5k');
        return false;
      });
    });
  }
  if (openOnly) list = list.filter(r => r.status === '접수중');
  render(list);
}

function resetFilters() {
  document.querySelectorAll('.c-check input').forEach(el => el.checked = false);
  applyFilter();
}

function toggleOpen() {
  openOnly = !openOnly;
  document.getElementById('openTog').classList.toggle('on', openOnly);
  applyFilter();
}

/* ── 뱃지 HTML ── */
function badge(c) {
  const l = c.toLowerCase();
  if (l.includes('100')||l.includes('70')||l.includes('50')) return `<span class="b b-ultra">${c}</span>`;
  if (l==='풀'  ||l.includes('42'))  return `<span class="b b-full">FULL</span>`;
  if (l==='하프'||l.includes('21'))  return `<span class="b b-half">HALF</span>`;
  if (l.includes('10'))               return `<span class="b b-10k">10K</span>`;
  if (l.includes('5'))                return `<span class="b b-5k">5K</span>`;
  return `<span class="b b-trail">${c}</span>`;
}

/* ── D-Day HTML ── */
function ddayHtml(r) {
  if (r.status === '마감')   return `<div class="dday close">마감</div>`;
  if (r.status === '접수전') return `<div class="dday before">접수전</div>`;
  const today = new Date(); today.setHours(0,0,0,0);
  const diff  = Math.ceil((new Date(r.date) - today) / 86400000);
  if (diff < 0)   return `<div class="dday close">종료</div>`;
  if (diff === 0)  return `<div class="dday soon">D-DAY</div>`;
  if (diff <= 7)   return `<div class="dday soon">D-${diff}</div>`;
  return `<div class="dday open">접수중</div>`;
}

/* ── 카드 HTML ── */
function cardHtml(r, i) {
  const idx = allRaces.indexOf(r);
  return `
    <a class="race-card" href="detail.html?i=${idx}" style="animation-delay:${Math.min(i*40,300)}ms">
      <div class="date-box">
        <div class="mo">${MON[r.month]||''}</div>
        <div class="dy">${r.day}</div>
        <div class="dw">${r.dow}</div>
      </div>
      <div class="card-info">
        <div class="badges">${(r.courses||[]).slice(0,3).map(badge).join('')}</div>
        <div class="card-title">${r.title}</div>
        <div class="card-meta">📍 ${r.region||''} ${r.location||''}</div>
      </div>
      <div class="card-right">${ddayHtml(r)}</div>
    </a>`;
}

/* ── 목록 렌더 ── */
function render(list) {
  const cnt = document.getElementById('raceCount');
  if (cnt) cnt.textContent = list.length;
  const el = document.getElementById('raceList');
  if (!el) return;
  if (!list.length) {
    el.innerHTML = `<div class="state-box"><div style="font-size:36px">🏅</div><div class="state-text" style="margin-top:8px">해당 조건의 대회가 없어요</div></div>`;
    return;
  }
  el.innerHTML = list.map((r,i) => cardHtml(r,i)).join('');
}

/* ════════════════════════════════
   찜
════════════════════════════════ */
function toggleWish(raceTitle) {
  if (!currentUser) {
    if (confirm('찜 기능은 로그인이 필요해요.\n로그인 화면으로 이동할까요?'))
      window.location.href = 'login.html';
    return;
  }
  const idx = wishlist.indexOf(raceTitle);
  if (idx === -1) wishlist.push(raceTitle);
  else            wishlist.splice(idx, 1);
  localStorage.setItem('runnu_wish_' + (currentUser.email||'guest'), JSON.stringify(wishlist));
  return wishlist.includes(raceTitle);
}

function getWishCount() { return wishlist.length; }

/* ── 공유 ── */
function shareRace(race) {
  const text = `[런뉴] ${race.title}\n📅 ${race.date}\n📍 ${race.location||''}`;
  if (navigator.share) navigator.share({ title: race.title, text, url: race.detail_url || location.href });
  else if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => alert('클립보드에 복사됐어요!'));
}
