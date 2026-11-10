import crypto from 'k6/crypto';
import encoding from 'k6/encoding';

// api의 AuthTokenService와 같은 모양의 access token을 만들어요 (HS256, iss=mujuthaek-api, sub=회원 id, role·nickname).
// 소셜 로그인은 스크립트로 못 해서, 운영 JWT_SECRET으로 테스트 계정 토큰을 직접 서명해요. 비밀 값은 환경변수로만 받아요
export function accessToken(secret, userId, ttlSeconds = 6 * 60 * 60) {
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

const b64 = (s) => encoding.b64encode(s, 'rawurl');
