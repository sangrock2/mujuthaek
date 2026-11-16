import crypto from 'k6/crypto';
import encoding from 'k6/encoding';

// api의 AuthTokenService와 같은 모양의 access token을 만들어요 (HS256, iss=mujuthaek-api, sub=회원 id, role·nickname).
// 소셜 로그인은 스크립트로 못 해서 JWT_SECRET으로 테스트 계정 토큰을 직접 서명해요. 비밀 값은 환경변수로만 받아요.
// 로컬·스테이징 주소에만 만들어요: 운영 JWT_SECRET이 노트북에 있으면 어느 회원·관리자 토큰이든 만들 수 있어요(2026-11-16 보안 감사 4장)
export function accessToken(baseUrl, secret, userId, ttlSeconds = 6 * 60 * 60) {
  if (!mintAllowed(baseUrl)) {
    throw new Error(`BASE_URL(${baseUrl})이 로컬·스테이징 주소가 아니라 JWT를 만들지 않아요. JWT_SECRET을 비워요`);
  }
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: 'HS256' };
  const claims = {
    iss: 'mujuthaek-api',
    sub: userId,
    iat: now,
    exp: now + ttlSeconds,
    role: 'USER',
    nickname: 'perf',
  };
  const unsigned = `${b64(JSON.stringify(header))}.${b64(JSON.stringify(claims))}`;
  return `${unsigned}.${crypto.hmac('sha256', secret, unsigned, 'base64rawurl')}`;
}

// lib/common.sh의 token_host_allowed와 같은 규칙: localhost·127.0.0.1·::1·*.localhost·*.test, staging.·dev.·test.·qa.로 시작하는 이름
export function mintAllowed(baseUrl) {
  const match = /^[a-z][a-z0-9+.-]*:\/\/(?:\[([^\]]*)\]|([^/:?#]*))/i.exec(baseUrl || '');
  if (!match) return false;
  const host = (match[1] || match[2] || '').toLowerCase();
  if (['localhost', '127.0.0.1', '::1'].includes(host)) return true;
  if (host.endsWith('.localhost') || host.endsWith('.test')) return true;
  return /^(staging|dev|test|qa)\./.test(host);
}

const b64 = (s) => encoding.b64encode(s, 'rawurl');
