import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL } from './config.js';

// data/data.json은 fetch-data.sh로 운영에서 한 번 뽑아 둔 값이에요. 개선 전후에 같은 파일을 써야 비교가 돼요
const data = JSON.parse(open('../data/data.json'));

export const serverErrors = new Counter('server_errors');

const JSON_HEADERS = { 'Content-Type': 'application/json' };

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const think = () => sleep(3 + Math.random() * 2); // 행동 사이 3~5초

// type: lookup(조회) · search(목록·검색) · judge(판정이 들어간 검색). name은 그래프에서 API를 묶는 이름이에요
function call(method, path, body, type, name, auth) {
  const headers = auth ? { ...JSON_HEADERS, Authorization: `Bearer ${auth}` } : JSON_HEADERS;
  const res = http.request(method, `${BASE_URL}${path}`, body === null ? null : JSON.stringify(body), {
    headers,
    tags: { type, name },
  });
  if (res.status >= 500) serverErrors.add(1, { name });
  check(res, { [`${name} 2xx`]: (r) => r.status >= 200 && r.status < 300 });
  return res;
}

const get = (path, type, name, auth) => call('GET', path, null, type, name, auth);
const post = (path, body, type, name) => call('POST', path, body, type, name);

const regionFilter = () => ({ regionCodes: [pick(data.sidoCodes)] });

function mapPath() {
  const b = pick(data.mapBoxes);
  return `/api/v1/notices/map?swLat=${b[0]}&swLng=${b[1]}&neLat=${b[2]}&neLng=${b[3]}&zoom=${b[4]}`;
}

// 판정 입력. 실제 사람 값이 아니라 화면이 보내는 모양만 맞춘 가짜 조합이에요
function applicant() {
  const p = pick(data.applicants);
  return { ...p, regionCode: pick(data.sigunguCodes) };
}

// 요청 한 건씩. 둘러보기 · 판정 · 로그인 사용자 흐름이 이걸 이어 불러요
export const requests = {
  homeSummary: () => post('/api/v1/home/summary', { filters: regionFilter() }, 'search', 'home/summary'),
  regions: () => get('/api/v1/regions', 'lookup', 'regions'),
  noticeSearch: () =>
    post('/api/v1/notices/search', { filters: regionFilter(), sort: 'DEADLINE', size: 20 }, 'search', 'notices/search'),
  noticeMap: () => get(mapPath(), 'search', 'notices/map'),
  noticeDetail: () => get(`/api/v1/notices/${pick(data.noticeIds)}`, 'search', 'notices/{id}'),
  benefitSearch: () =>
    post('/api/v1/benefits/search', { filters: regionFilter(), size: 20 }, 'search', 'benefits/search'),
  spaceSearch: () => post('/api/v1/spaces/search', { size: 20 }, 'search', 'spaces/search'),
  supportSearch: () => post('/api/v1/supports/search', { size: 20 }, 'search', 'supports/search'),

  criteria: () => get('/api/v1/eligibility/criteria', 'lookup', 'eligibility/criteria'),
  benefitJudge: () =>
    post(
      '/api/v1/benefits/search',
      { filters: regionFilter(), applicant: applicant(), sort: 'RECOMMENDED', size: 20 },
      'judge',
      'benefits/search+applicant',
    ),
  noticeJudge: () =>
    post(
      '/api/v1/notices/search',
      { filters: regionFilter(), applicant: applicant(), sort: 'RECOMMENDED', size: 20 },
      'judge',
      'notices/search+applicant',
    ),
  homeJudge: () =>
    post('/api/v1/home/summary', { filters: regionFilter(), applicant: applicant() }, 'judge', 'home/summary+applicant'),

  me: (t) => get('/api/users/me', 'lookup', 'users/me', t),
  favorites: (t) => get('/api/users/me/favorites', 'lookup', 'users/me/favorites', t),
  notifications: (t) => get('/api/users/me/notifications', 'lookup', 'users/me/notifications', t),
  notificationSettings: (t) => get('/api/users/me/notification-settings', 'lookup', 'users/me/notification-settings', t),
  pushKey: () => get('/api/v1/push/public-key', 'lookup', 'push/public-key'),
  favoriteToggle: (t) => {
    const id = pick(data.noticeIds);
    call('PUT', `/api/users/me/favorites/NOTICE/${id}`, null, 'lookup', 'favorites PUT', t);
    call('DELETE', `/api/users/me/favorites/NOTICE/${id}`, null, 'lookup', 'favorites DELETE', t);
  },
};

const r = requests;

export function browse() {
  group('둘러보기', () => {
    for (const step of [r.homeSummary, r.regions, r.noticeSearch, r.noticeMap, r.noticeDetail]) {
      step();
      think();
    }
    pick([r.benefitSearch, r.spaceSearch, r.supportSearch])();
    think();
  });
}

export function judge() {
  group('조건 넣고 판정', () => {
    for (const step of [r.criteria, r.benefitJudge, r.noticeJudge, r.homeJudge]) {
      step();
      think();
    }
  });
}

export function member(token) {
  group('로그인 사용자', () => {
    for (const step of [r.me, r.favorites, r.favoriteToggle, r.notifications, r.notificationSettings, r.pushKey]) {
      step(token);
      think();
    }
  });
}

// 한계 찾기용: 같은 비중으로 요청 하나만 골라 보내요(쉬는 시간 없음)
export function single(token) {
  const x = Math.random();
  if (x < 0.6) {
    pick([r.homeSummary, r.regions, r.noticeSearch, r.noticeMap, r.noticeDetail, r.benefitSearch, r.spaceSearch, r.supportSearch])();
  } else if (x < 0.85 || !token) {
    pick([r.criteria, r.benefitJudge, r.noticeJudge, r.homeJudge])();
  } else {
    pick([r.me, r.favorites, r.notifications, r.notificationSettings, r.pushKey])(token);
  }
}
