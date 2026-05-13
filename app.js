/* ═══════════════════════════════════════
   app.js  —  런뉴 공통 JS 로직
   ═══════════════════════════════════════ */

const MON = ['','JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

/* ── 전역 상태 ── */
let allRaces   = [];   // 현재 접수중·예정 대회만
let endedRaces = [];   // 접수 마감 또는 날짜 지난 대회
let wishlist   = [];

/* ════════════════════════════════
   찜 — 로컬스토리지 (로그인 없이 guest로 저장)
════════════════════════════════ */
function loadWishlist() {
  wishlist = JSON.parse(localStorage.getItem('runnu_wish_guest') || '[]');
}

function toggleWish(raceTitle) {
  loadWishlist();
  const idx = wishlist.indexOf(raceTitle);
  if (idx === -1) wishlist.push(raceTitle);
  else            wishlist.splice(idx, 1);
  localStorage.setItem('runnu_wish_guest', JSON.stringify(wishlist));
  return wishlist.includes(raceTitle);
}

function getWishCount() {
  loadWishlist();
  return wishlist.length;
}

/* ════════════════════════════════
   데이터 로드
════════════════════════════════ */
async function loadRaces() {
  try {
    const res  = await fetch('races.json?t=' + Date.now());
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const sorted = (data.races || []).sort((a, b) => new Date(a.date) - new Date(b.date));

    // 마감 판단: status가 '마감' 이거나 대회 날짜가 오늘 이전
    endedRaces = sorted.filter(r => {
      if (r.status === '마감') return true;
      const raceDate = new Date(r.date);
      raceDate.setHours(0, 0, 0, 0);
      return raceDate < today;
    });

    allRaces = sorted.filter(r => !endedRaces.includes(r));

    // ended.html에서 쓸 수 있도록 sessionStorage에 보관
    sessionStorage.setItem('endedRaces', JSON.stringify(endedRaces));

    const banner = document.getElementById('updateTime');
    if (banner) banner.textContent = data.updated_at
      ? '마지막 업데이트: ' + data.updated_at + ' · 매주 월요일 자동 갱신'
      : '데이터 로드 완료';

    return allRaces;
  } catch (e) {
    console.error('races.json 로드 실패:', e);
    return [];
  }
}

/* ════════════════════════════════
   필터 (allRaces — 마감 제외된 목록 기준)
════════════════════════════════ */
let openOnly = false;

function applyFilter() {
  const checked = Array.from(document.querySelectorAll('.c-check input:checked')).map(el => el.value);
  let list = allRaces.slice();
  if (checked.length) {
    list = list.filter(r => {
      const cs = (r.courses || []).map(c => c.toLowerCase());
      return checked.some(sel => {
        if (sel === '풀')   return cs.some(c => c === '풀'   || c.includes('42'));
        if (sel === '하프') return cs.some(c => c === '하프' || c.includes('21'));
        if (sel === '10km') return cs.some(c => c.includes('10'));
        if (sel === '5km')  return cs.some(c => c === '5km'  || c === '5k');
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

/* ════════════════════════════════
   렌더 유틸
════════════════════════════════ */
function badge(c) {
  const l = c.toLowerCase();
  if (l.includes('100') || l.includes('70') || l.includes('50')) return `<span class="b b-ultra">${c}</span>`;
  if (l === '풀'   || l.includes('42')) return '<span class="b b-full">FULL</span>';
  if (l === '하프' || l.includes('21')) return '<span class="b b-half">HALF</span>';
  if (l.includes('10'))                 return '<span class="b b-10k">10K</span>';
  if (l.includes('5'))                  return '<span class="b b-5k">5K</span>';
  return `<span class="b b-trail">${c}</span>`;
}

function ddayHtml(r) {
  if (r.status === '마감')   return '<div class="dday close">마감</div>';
  if (r.status === '접수전') return '<div class="dday before">접수전</div>';
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff  = Math.ceil((new Date(r.date) - today) / 86400000);
  if (diff < 0)  return '<div class="dday close">종료</div>';
  if (diff === 0) return '<div class="dday soon">D-DAY</div>';
  if (diff <= 7)  return '<div class="dday soon">D-' + diff + '</div>';
  return '<div class="dday open">접수중</div>';
}

function cardHtml(r, i, sourceArr) {
  // sourceArr: 카드 클릭 시 detail.html?i= 에 쓸 인덱스 기준 배열
  const arr = sourceArr || allRaces;
  const idx = arr.indexOf(r);
  return `<a class="race-card" href="detail.html?i=${idx}" style="animation-delay:${Math.min(i * 40, 300)}ms">
    <div class="date-box">
      <div class="mo">${MON[r.month] || ''}</div>
      <div class="dy">${r.day}</div>
      <div class="dw">${r.dow}</div>
    </div>
    <div class="card-info">
      <div class="badges">${(r.courses || []).slice(0, 3).map(badge).join('')}</div>
      <div class="card-title">${r.title}</div>
      <div class="card-meta">📍 ${r.region || ''} ${r.location || ''}</div>
    </div>
    <div class="card-right">${ddayHtml(r)}</div>
  </a>`;
}

function render(list, sourceArr) {
  const cnt = document.getElementById('raceCount');
  if (cnt) cnt.textContent = list.length;
  const el = document.getElementById('raceList');
  if (!el) return;
  if (!list.length) {
    el.innerHTML = '<div class="state-box"><div style="font-size:36px">🏅</div><div class="state-text" style="margin-top:8px">해당 조건의 대회가 없어요</div></div>';
    return;
  }
  el.innerHTML = list.map((r, i) => cardHtml(r, i, sourceArr)).join('');
}

/* ════════════════════════════════
   공유
════════════════════════════════ */
function shareRace(race) {
  const text = '[런뉴] ' + race.title + '\n📅 ' + race.date + '\n📍 ' + (race.location || '');
  if (navigator.share) navigator.share({ title: race.title, text, url: race.detail_url || location.href });
  else if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => alert('클립보드에 복사됐어요!'));
}

/* ── 페이지 진입 시 찜 목록 초기화 ── */
loadWishlist();
