package kr.mujuthaek.api.traffic.log;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * IP 해시에 섞는 비밀 값을 정해요.
 *
 * <p>예전에는 TRAFFIC_IP_SALT가 없으면 저장소에 적힌 기본값(local-dev-salt)을 썼고, 운영에도 이 값이 들어가 있었어요. 값이 공개돼 있으니 IPv4
 * 전체를 넣어 보면 해시에서 원래 IP를 되찾을 수 있었고, "14일 뒤 원본 IP 삭제"가 실질적으로 지켜지지 않았어요(2026-11-16 보안 감사 L-1).
 *
 * <p>이제 따로 넣은 값이 없거나 너무 짧으면 JWT 비밀값에서 용도 이름을 붙여 HMAC으로 따로 만든 값을 써요. JWT 비밀값은 공개되지 않고, 만든 값에서 JWT
 * 비밀값을 거꾸로 알아낼 수도 없어요. JWT 비밀값도 없으면 서버가 켜질 때마다 새로 만든 무작위 값을 써요(그러면 다시 켜기 전후로 같은 사람이 다른 해시가 돼요).
 */
final class IpSalt {

  /** 예전 기본값. 공개돼 있어서 넣어 둬도 쓰지 않아요 */
  static final String PUBLIC_DEFAULT = "local-dev-salt";

  /** 이보다 짧은 값은 맞혀 볼 수 있어서 쓰지 않아요 */
  static final int MIN_LENGTH = 16;

  private static final String PURPOSE = "mujuthaek.traffic.ip-salt.v1";
  private static final SecureRandom RANDOM = new SecureRandom();

  private IpSalt() {}

  /** 쓸 값과, 따로 넣은 값을 썼는지 */
  record Resolved(String value, Source source) {}

  enum Source {
    CONFIGURED,
    DERIVED_FROM_JWT_SECRET,
    RANDOM_PER_PROCESS
  }

  static Resolved resolve(String configured, String jwtSecret) {
    String value = configured == null ? "" : configured.strip();
    if (value.length() >= MIN_LENGTH && !value.equals(PUBLIC_DEFAULT)) {
      return new Resolved(value, Source.CONFIGURED);
    }
    if (jwtSecret != null && !jwtSecret.isBlank()) {
      return new Resolved(
          hmacHex(jwtSecret.getBytes(StandardCharsets.UTF_8), PURPOSE),
          Source.DERIVED_FROM_JWT_SECRET);
    }
    return new Resolved(HexFormat.of().formatHex(randomKey()), Source.RANDOM_PER_PROCESS);
  }

  /** 서버가 켜져 있는 동안만 쓰는 무작위 키 (화면에 보낼 이름표용) */
  static byte[] randomKey() {
    byte[] key = new byte[32];
    RANDOM.nextBytes(key);
    return key;
  }

  static String hmacHex(byte[] key, String message) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(key, "HmacSHA256"));
      return HexFormat.of().formatHex(mac.doFinal(message.getBytes(StandardCharsets.UTF_8)));
    } catch (GeneralSecurityException impossible) {
      throw new IllegalStateException(impossible);
    }
  }
}
