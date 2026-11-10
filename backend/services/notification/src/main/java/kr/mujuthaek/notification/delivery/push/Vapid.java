package kr.mujuthaek.notification.delivery.push;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Signature;
import java.security.interfaces.ECPrivateKey;
import java.security.interfaces.ECPublicKey;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;

/**
 * VAPID (RFC 8292): "이 알림은 그 공개키를 가진 서비스가 보냈다"는 서명. 기기가 구독할 때 우리 공개키를 넣었기 때문에, 푸시 서비스는 이 서명이 맞는 요청만
 * 받아요. {@code Authorization: vapid t=<JWT>, k=<공개키>}로 보내요.
 *
 * <p>JWT는 ES256(P-256 + SHA-256) 서명, 받는 쪽(aud)은 푸시 서비스 주소의 앞부분(https://fcm.googleapis.com), 만료는
 * 12시간 뒤예요 (최대 24시간).
 */
final class Vapid {

  static final Duration TOKEN_TTL = Duration.ofHours(12);

  private static final Base64.Encoder B64 = Base64.getUrlEncoder().withoutPadding();
  private static final String HEADER =
      B64.encodeToString(utf8("{\"typ\":\"JWT\",\"alg\":\"ES256\"}"));

  private final ECPrivateKey privateKey;
  private final String publicKey;
  private final String subject;

  /**
   * @throws IllegalArgumentException 키가 비었거나 모양이 틀리거나 두 키가 짝이 아니면 (서버가 뜨지 않게)
   */
  Vapid(String publicKey, String privateKey, String subject) {
    if (publicKey.isBlank() || privateKey.isBlank()) {
      throw new IllegalArgumentException(
          "웹 푸시로 보내려면 PUSH_VAPID_PUBLIC_KEY·PUSH_VAPID_PRIVATE_KEY가 있어야 해요");
    }
    if (!subject.startsWith("mailto:") && !subject.startsWith("https:")) {
      throw new IllegalArgumentException("PUSH_VAPID_SUBJECT는 mailto: 또는 https: 주소예요");
    }
    try {
      ECPublicKey pub = WebPushCrypto.publicKey(WebPushCrypto.decode(publicKey));
      this.privateKey = WebPushCrypto.privateKey(WebPushCrypto.decode(privateKey));
      this.publicKey = B64.encodeToString(WebPushCrypto.encodePublic(pub));
      checkPair(pub, this.privateKey);
    } catch (GeneralSecurityException | IllegalArgumentException e) {
      // 키 값은 오류 문구에 넣지 않아요
      throw new IllegalArgumentException("VAPID 키 모양이 맞지 않아요: " + e.getClass().getSimpleName());
    }
    this.subject = subject;
  }

  /** {@code endpoint}로 보낼 Authorization 헤더 값 */
  String authorization(URI endpoint, Instant now) throws GeneralSecurityException {
    String audience = endpoint.getScheme() + "://" + endpoint.getRawAuthority();
    String claims =
        "{\"aud\":\""
            + audience
            + "\",\"exp\":"
            + now.plus(TOKEN_TTL).getEpochSecond()
            + ",\"sub\":\""
            + subject.replace("\"", "")
            + "\"}";
    String signingInput = HEADER + "." + B64.encodeToString(utf8(claims));
    return "vapid t=" + signingInput + "." + sign(signingInput) + ", k=" + publicKey;
  }

  private String sign(String signingInput) throws GeneralSecurityException {
    Signature signature =
        Signature.getInstance("SHA256withECDSAinP1363Format"); // JWT 모양(r‖s 64바이트)
    signature.initSign(privateKey);
    signature.update(utf8(signingInput));
    return B64.encodeToString(signature.sign());
  }

  /** 공개키가 이 개인키의 짝인지 (설정 실수로 다른 키를 넣으면 모든 발송이 403이라 서버를 띄우기 전에 막아요) */
  private static void checkPair(ECPublicKey pub, ECPrivateKey priv)
      throws GeneralSecurityException {
    byte[] probe = utf8("vapid-key-check");
    Signature signer = Signature.getInstance("SHA256withECDSA");
    signer.initSign(priv);
    signer.update(probe);
    byte[] sig = signer.sign();
    Signature verifier = Signature.getInstance("SHA256withECDSA");
    verifier.initVerify(pub);
    verifier.update(probe);
    if (!verifier.verify(sig)) {
      throw new GeneralSecurityException("공개키와 개인키가 짝이 아니에요");
    }
  }

  private static byte[] utf8(String value) {
    return value.getBytes(StandardCharsets.UTF_8);
  }
}
