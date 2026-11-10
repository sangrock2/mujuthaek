package kr.mujuthaek.notification.delivery.push;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigInteger;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.ECPrivateKey;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.time.Instant;
import java.util.Base64;
import org.junit.jupiter.api.Test;

/** VAPID 서명 헤더 모양, 서명이 공개키로 확인되는지, 키 설정 실수를 서버 시작 때 막는지. */
class VapidTest {

  static final Base64.Encoder E = Base64.getUrlEncoder().withoutPadding();
  static final Base64.Decoder D = Base64.getUrlDecoder();

  @Test
  void headerCarriesASignedTokenForThePushServiceOrigin() throws Exception {
    KeyPair keys = keyPair();
    Vapid vapid = new Vapid(publicKey(keys), privateKey(keys), "mailto:team@example.com");
    Instant now = Instant.parse("2026-10-26T00:00:00Z");

    String header =
        vapid.authorization(URI.create("https://fcm.googleapis.com/fcm/send/abc?x=1"), now);

    assertThat(header).startsWith("vapid t=").endsWith(", k=" + publicKey(keys));
    String jwt = header.substring("vapid t=".length(), header.indexOf(", k="));
    String[] parts = jwt.split("\\.");
    assertThat(new String(D.decode(parts[0]), StandardCharsets.UTF_8))
        .isEqualTo("{\"typ\":\"JWT\",\"alg\":\"ES256\"}");
    assertThat(new String(D.decode(parts[1]), StandardCharsets.UTF_8))
        .isEqualTo(
            "{\"aud\":\"https://fcm.googleapis.com\",\"exp\":"
                + now.plus(Vapid.TOKEN_TTL).getEpochSecond()
                + ",\"sub\":\"mailto:team@example.com\"}");
    byte[] signature = D.decode(parts[2]);
    assertThat(signature).hasSize(64); // r‖s

    Signature verifier = Signature.getInstance("SHA256withECDSAinP1363Format");
    verifier.initVerify(keys.getPublic());
    verifier.update((parts[0] + "." + parts[1]).getBytes(StandardCharsets.US_ASCII));
    assertThat(verifier.verify(signature)).isTrue();
  }

  @Test
  void missingMismatchedOrBrokenKeysStopTheServerWithoutPrintingThem() throws Exception {
    KeyPair one = keyPair();
    KeyPair other = keyPair();

    assertThatThrownBy(() -> new Vapid("", "", "mailto:a@b.c"))
        .hasMessageContaining("PUSH_VAPID_PUBLIC_KEY");
    assertThatThrownBy(() -> new Vapid(publicKey(one), privateKey(other), "mailto:a@b.c"))
        .hasMessageContaining("모양이 맞지 않아요")
        .message()
        .doesNotContain(privateKey(other));
    assertThatThrownBy(() -> new Vapid("not+base64", privateKey(one), "mailto:a@b.c"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new Vapid(publicKey(one), privateKey(one), "team@example.com"))
        .hasMessageContaining("mailto:");
  }

  static KeyPair keyPair() throws Exception {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
    generator.initialize(new ECGenParameterSpec("secp256r1"));
    return generator.generateKeyPair();
  }

  /** npx web-push generate-vapid-keys와 같은 모양 (공개키 65바이트, 개인키 32바이트, base64url) */
  static String publicKey(KeyPair keys) {
    return E.encodeToString(WebPushCrypto.encodePublic((ECPublicKey) keys.getPublic()));
  }

  static String privateKey(KeyPair keys) {
    BigInteger s = ((ECPrivateKey) keys.getPrivate()).getS();
    byte[] raw = s.toByteArray();
    byte[] fixed = new byte[32];
    int copy = Math.min(raw.length, 32);
    System.arraycopy(raw, raw.length - copy, fixed, 32 - copy, copy);
    return E.encodeToString(fixed);
  }
}
