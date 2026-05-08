/* ═══════════════════════════════════════
   app.js  —  런뉴 공통 JS 로직
   ═══════════════════════════════════════ */

const KAKAO_KEY  = '6dc88714f7ade5205b72b9a2a991d530';
const GOOGLE_CID = '372085184739-6vp986ob9sa277cvcdfeill8se8i9hpg.apps.googleusercontent.com';
const MON = ['','JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

/* ── 현재 디렉토리 기준 base path ── */
function getBasePath() {
  var path = location.pathname;
  /* login.html, index.html 등 파일명 제거 → 디렉토리만 */
  var base = path.substring(0, path.lastIndexOf('/') + 1);
  return location.origin + base;
}

/* ── 전역 상태 ── */
let allRaces    = [];
let currentUser = null;
let wishlist    = [];
let openOnly    = false;

/* ════════════════════════════════
   카카오 로그인
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

/* ════════════════════════════════
   구글 로그인 (One Tap — redirect_uri 불필요)
════════════════════════════════ */
function loginGoogle() {
  if (!window.google) {
    alert('구글 SDK 로딩 중입니다. 잠시 후 다시 시도해주세요.');
    return;
  }

  google.accounts.id.initialize({
    client_id: GOOGLE_CID,
    callback: function(res) {
      try {
        /* JWT Base64 디코딩 */
        const base64 = res.credential.split('.')[1].replace(/-/g,'+').replace(/_/g,'/');
        const payload = JSON.parse(decodeURIComponent(escape(atob(base64))));
        afterLogin({
          name:     payload.name    || 'Google 유저',
          email:    payload.email   || '',
          photo:    payload.picture || '',
          provider: 'google'
        });
      } catch(e) {
        alert('구글 로그인 오류. 다시 시도해주세요.');
        console.error(e);
      }
    },
    ux_mode: 'popup',
    auto_select: false,
    cancel_on_tap_outside: false
  });

  /* 숨겨진 컨테이너에 버튼 렌더 후 자동 클릭 */
  var container = document.getElementById('googleBtnContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'googleBtnContainer';
    container.style.cssText = 'position:fixed;opacity:0;pointer-events:none;top:0;left:0;';
    document.body.appendChild(container);
  }
  container.innerHTML = '';

  google.accounts.id.renderButton(container, {
    type: 'standard', theme: 'outline', size: 'large',
    text: 'signin_with', shape: 'rectangular', locale: 'ko'
  });

  setTimeout(function() {
    var btn = container.querySelector('div[role=button]') || container.querySelector('div[tabindex="0"]');
    if (btn) {
      btn.click();
    } else {
      /* renderButton 실패시 prompt() 시도 */
      google.accounts.id.prompt(function(notification) {
        if (notification.isNotDisplayed()) {
          alert('구글 로그인 팝업이 차단됐어요.\n브라우저 팝업 차단을 해제해주세요.');
        }
      });
    }
  }, 200);
}

/* ════════════════════════════════
   로그인 없이 둘러보기
════════════════════════════════ */
function skipLogin() {
  localStorage.setItem('runnu_skip', '1');
  localStorage.removeItem('runnu_user');
  window.location.href = getBasePath() + 'index.html';
}

/* ════════════════════════════════
   로그인 후 처리
════════════════════════════════ */
function afterLogin(user) {
  currentUser = user;
  localStorage.setItem('runnu_user', JSON.stringify(user));
  localStorage.removeItem('runnu_skip');
  wishlist = JSON.parse(localStorage.getItem('runnu_wish_' + (user.email || 'guest')) || '[]');
  window.location.href = getBasePath() + 'index.html';
}

function doLogout() {
  if (!confirm('로그아웃 하시겠어요?')) return;
  if (currentUser && currentUser.provider === 'kakao' && window.Kakao && window.Kakao.Auth) {
    Kakao.Auth.logout(function() {});
  }
  currentUser = null;
  localStorage.removeItem('runnu_user');
  localStorage.removeItem('runnu_skip');
  wishlist = [];
  window.location.href = getBasePath() + 'login.html';
}

/* ════════════════════════════════
   세션 복원
════════════════════════════════ */
function restoreSession() {
  var saved = localStorage.getItem('runnu_user');
  if (saved) {
    try {
      currentUser = JSON.parse(saved);
      wishlist = JSON.parse(localStorage.getItem('runnu_wish_' + (currentUser.email || 'guest')) || '[]');
      return 'user';
    } catch(e) { return false; }
  }
  if (localStorage.getItem('runnu_skip') === '1') return 'skip';
  return false;
}

/* ════════════════════════════════
   데이터 로드
════════════════════════════════ */
async function loadRaces() {
  try {
    var res  = await fetch('races.json?t=' + Date.now());
    if (!res.ok) throw new Error(res.status);
    var data = await res.json();
    allRaces = (data.races || []).sort(function(a,b){ return new Date(a.date) - new Date(b.date); });
    var banner = document.getElementById('updateTime');
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
   필터
════════════════════════════════ */
function applyFilter() {
  var checked = Array.from(document.querySelectorAll('.c-check input:checked')).map(function(el){ return el.value; });
  var list = allRaces.slice();
  if (checked.length) {
    list = list.filter(function(r) {
      var cs = (r.courses || []).map(function(c){ return c.toLowerCase(); });
      return checked.some(function(sel) {
        if (sel === '풀')   return cs.some(function(c){ return c === '풀'  || c.includes('42'); });
        if (sel === '하프') return cs.some(function(c){ return c === '하프' || c.includes('21'); });
        if (sel === '10km') return cs.some(function(c){ return c.includes('10'); });
        if (sel === '5km')  return cs.some(function(c){ return c === '5km' || c === '5k'; });
        return false;
      });
    });
  }
  if (openOnly) list = list.filter(function(r){ return r.status === '접수중'; });
  render(list);
}

function resetFilters() {
  document.querySelectorAll('.c-check input').forEach(function(el){ el.checked = false; });
  applyFilter();
}

function toggleOpen() {
  openOnly = !openOnly;
  document.getElementById('openTog').classList.toggle('on', openOnly);
  applyFilter();
}

/* ════════════════════════════════
   렌더 유틸
════════════════════════════════ */
function badge(c) {
  var l = c.toLowerCase();
  if (l.includes('100')||l.includes('70')||l.includes('50')) return '<span class="b b-ultra">'+c+'</span>';
  if (l==='풀'  ||l.includes('42'))  return '<span class="b b-full">FULL</span>';
  if (l==='하프'||l.includes('21'))  return '<span class="b b-half">HALF</span>';
  if (l.includes('10'))               return '<span class="b b-10k">10K</span>';
  if (l.includes('5'))                return '<span class="b b-5k">5K</span>';
  return '<span class="b b-trail">'+c+'</span>';
}

function ddayHtml(r) {
  if (r.status === '마감')   return '<div class="dday close">마감</div>';
  if (r.status === '접수전') return '<div class="dday before">접수전</div>';
  var today = new Date(); today.setHours(0,0,0,0);
  var diff  = Math.ceil((new Date(r.date) - today) / 86400000);
  if (diff < 0)   return '<div class="dday close">종료</div>';
  if (diff === 0)  return '<div class="dday soon">D-DAY</div>';
  if (diff <= 7)   return '<div class="dday soon">D-'+diff+'</div>';
  return '<div class="dday open">접수중</div>';
}

function cardHtml(r, i) {
  var idx = allRaces.indexOf(r);
  return '<a class="race-card" href="detail.html?i='+idx+'" style="animation-delay:'+Math.min(i*40,300)+'ms">'
    + '<div class="date-box">'
    +   '<div class="mo">'+(MON[r.month]||'')+'</div>'
    +   '<div class="dy">'+r.day+'</div>'
    +   '<div class="dw">'+r.dow+'</div>'
    + '</div>'
    + '<div class="card-info">'
    +   '<div class="badges">'+(r.courses||[]).slice(0,3).map(badge).join('')+'</div>'
    +   '<div class="card-title">'+r.title+'</div>'
    +   '<div class="card-meta">📍 '+(r.region||'')+' '+(r.location||'')+'</div>'
    + '</div>'
    + '<div class="card-right">'+ddayHtml(r)+'</div>'
    + '</a>';
}

function render(list) {
  var cnt = document.getElementById('raceCount');
  if (cnt) cnt.textContent = list.length;
  var el = document.getElementById('raceList');
  if (!el) return;
  if (!list.length) {
    el.innerHTML = '<div class="state-box"><div style="font-size:36px">🏅</div><div class="state-text" style="margin-top:8px">해당 조건의 대회가 없어요</div></div>';
    return;
  }
  el.innerHTML = list.map(function(r,i){ return cardHtml(r,i); }).join('');
}

/* ════════════════════════════════
   찜
════════════════════════════════ */
function toggleWish(raceTitle) {
  if (!currentUser) {
    if (confirm('찜 기능은 로그인이 필요해요.\n로그인 화면으로 이동할까요?'))
      window.location.href = getBasePath() + 'login.html';
    return false;
  }
  var idx = wishlist.indexOf(raceTitle);
  if (idx === -1) wishlist.push(raceTitle);
  else            wishlist.splice(idx, 1);
  localStorage.setItem('runnu_wish_' + (currentUser.email||'guest'), JSON.stringify(wishlist));
  return wishlist.includes(raceTitle);
}

function getWishCount() { return wishlist.length; }

/* ── 공유 ── */
function shareRace(race) {
  var text = '[런뉴] ' + race.title + '\n📅 ' + race.date + '\n📍 ' + (race.location||'');
  if (navigator.share) navigator.share({ title: race.title, text: text, url: race.detail_url || location.href });
  else if (navigator.clipboard) navigator.clipboard.writeText(text).then(function(){ alert('클립보드에 복사됐어요!'); });
}
