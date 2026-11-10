package kr.mujuthaek.notification.delivery.push;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

/** 내용 암호화가 RFC 8291 예제(5장·부록 A)와 바이트까지 같은지, 그리고 기기 쪽에서 풀리는지. */
class WebPushCryptoTest {

  // RFC 8291 5장 예제 값
  static final String PLAINTEXT = "When I grow up, I want to be a watermelon";
  static final String AUTH = "BTBZMqHH6r4Tts7J_aSIgg";
  static final String UA_PUBLIC =
      "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4";
  static final String UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94";
  static final String AS_PUBLIC =
      "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8";
  static final String AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw";
  static final String SALT = "DGv6ra1nlYgDCS1FRnbzlw";
  static final String BODY =
      "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
          + "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
          + "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN";

  static final Base64.Decoder D = Base64.getUrlDecoder();

  @Test
  void matchesTheRfcExampleByteForByte() throws Exception {
    KeyPair sender =
        new KeyPair(
            WebPushCrypto.publicKey(D.decode(AS_PUBLIC)),
            WebPushCrypto.privateKey(D.decode(AS_PRIVATE)));

    byte[] body =
        WebPushCrypto.encrypt(
            PLAINTEXT.getBytes(StandardCharsets.US_ASCII),
            D.decode(UA_PUBLIC),
            D.decode(AUTH),
            sender,
            D.decode(SALT));

    assertThat(body).isEqualTo(D.decode(BODY));
    assertThat(body).hasSize(WebPushCrypto.HEADER_BYTES + PLAINTEXT.length() + 17);
  }

  @Test
  void deviceCanOpenAFreshlyEncryptedMessage() throws Exception {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
    generator.initialize(new ECGenParameterSpec("secp256r1"));
    KeyPair device = generator.generateKeyPair();
    byte[] auth = new byte[16];
    new java.security.SecureRandom().nextBytes(auth);
    String p256dh = b64(WebPushCrypto.encodePublic((ECPublicKey) device.getPublic()));
    byte[] message = "{\"title\":\"내일 마감: 서리풀 청년아트타운\"}".getBytes(StandardCharsets.UTF_8);

    byte[] first = WebPushCrypto.encrypt(message, p256dh, b64(auth));
    byte[] second = WebPushCrypto.encrypt(message, p256dh, b64(auth));

    assertThat(decrypt(first, device, auth)).isEqualTo(message);
    assertThat(first).as("보낼 때마다 새 키·salt").isNotEqualTo(second);
  }

  @Test
  void rejectsKeysOffTheCurveAndOversizedContent() throws Exception {
    byte[] notOnCurve = new byte[65];
    notOnCurve[0] = 0x04;
    notOnCurve[64] = 1;

    assertThatThrownBy(() -> WebPushCrypto.encrypt(new byte[1], b64(notOnCurve), AUTH))
        .isInstanceOf(GeneralSecurityException.class);
    assertThatThrownBy(() -> WebPushCrypto.encrypt(new byte[1], b64(new byte[33]), AUTH))
        .isInstanceOf(GeneralSecurityException.class);
    assertThatThrownBy(
            () ->
                WebPushCrypto.encrypt(
                    new byte[WebPushCrypto.MAX_PLAINTEXT_BYTES + 1], UA_PUBLIC, AUTH))
        .hasMessageContaining("바이트를 넘어요");
    assertThat(WebPushCrypto.encrypt(new byte[WebPushCrypto.MAX_PLAINTEXT_BYTES], UA_PUBLIC, AUTH))
        .hasSize(WebPushCrypto.RECORD_SIZE);
  }

  /** 브라우저가 하는 일 (RFC 8291 받는 쪽) */
  static byte[] decrypt(byte[] body, KeyPair device, byte[] auth) throws Exception {
    ByteBuffer in = ByteBuffer.wrap(body);
    byte[] salt = new byte[16];
    in.get(salt);
    assertThat(in.getInt()).isEqualTo(4096);
    byte[] asPublic = new byte[in.get()];
    in.get(asPublic);
    byte[] ciphertext = new byte[in.remaining()];
    in.get(ciphertext);

    KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
    agreement.init(device.getPrivate());
    agreement.doPhase(WebPushCrypto.publicKey(asPublic), true);
    byte[] ecdh = agreement.generateSecret();
    byte[] uaPublic = WebPushCrypto.encodePublic((ECPublicKey) device.getPublic());
    byte[] keyInfo =
        concat("WebPush: info\0".getBytes(StandardCharsets.US_ASCII), uaPublic, asPublic);
    byte[] ikm = expand(hmac(auth, ecdh), keyInfo, 32);
    byte[] prk = hmac(salt, ikm);
    byte[] cek =
        expand(prk, "Content-Encoding: aes128gcm\0".getBytes(StandardCharsets.US_ASCII), 16);
    byte[] nonce = expand(prk, "Content-Encoding: nonce\0".getBytes(StandardCharsets.US_ASCII), 12);
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
        Cipher.DECRYPT_MODE, new SecretKeySpec(cek, "AES"), new GCMParameterSpec(128, nonce));
    byte[] padded = cipher.doFinal(ciphertext);
    assertThat(padded[padded.length - 1]).isEqualTo((byte) 0x02);
    return Arrays.copyOf(padded, padded.length - 1);
  }

  static String b64(byte[] bytes) {
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }

  private static byte[] expand(byte[] prk, byte[] info, int length) throws Exception {
    return Arrays.copyOf(hmac(prk, concat(info, new byte[] {1})), length);
  }

  private static byte[] hmac(byte[] key, byte[] data) throws Exception {
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(key, "HmacSHA256"));
    return mac.doFinal(data);
  }

  private static byte[] concat(byte[]... parts) {
    ByteBuffer b = ByteBuffer.allocate(Arrays.stream(parts).mapToInt(p -> p.length).sum());
    Arrays.stream(parts).forEach(b::put);
    return b.array();
  }
}
