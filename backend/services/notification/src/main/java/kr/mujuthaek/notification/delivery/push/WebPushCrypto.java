package kr.mujuthaek.notification.delivery.push;

import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.interfaces.ECPrivateKey;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.ECParameterSpec;
import java.security.spec.ECPoint;
import java.security.spec.ECPrivateKeySpec;
import java.security.spec.ECPublicKeySpec;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * 웹 푸시 내용 암호화 (RFC 8291, Content-Encoding: aes128gcm). 그 기기만 열 수 있게 기기의 공개키(p256dh)·비밀값(auth)으로
 * 잠가요. JDK 기본 암호 기능(P-256 ECDH, HMAC-SHA256, AES-128-GCM)만 써요.
 *
 * <p>순서: 보낼 때마다 새 키 쌍과 salt를 만들어 → 기기 공개키와 ECDH → auth로 키 섞기(HKDF) → 내용 키·nonce → AES-GCM. 결과는
 * "salt 16바이트 + 레코드 크기 4096 + 키 길이 65 + 이번 공개키 + 암호문" 한 덩어리예요. RFC 8291 부록 A의 예제 값으로 테스트해요.
 */
final class WebPushCrypto {

  /** 레코드 크기. 내용 전체가 한 레코드에 들어가야 해요 */
  static final int RECORD_SIZE = 4096;

  /** salt(16) + 레코드 크기(4) + 키 길이(1) + 공개키(65) */
  static final int HEADER_BYTES = 86;

  /** 내용 끝 구분 바이트(1) + GCM 태그(16) */
  static final int OVERHEAD_BYTES = 17;

  /** 암호화하기 전 내용의 최대 길이 (푸시 서비스는 4096바이트까지 받아요) */
  static final int MAX_PLAINTEXT_BYTES = RECORD_SIZE - HEADER_BYTES - OVERHEAD_BYTES;

  private static final ECParameterSpec P256 = p256();
  private static final SecureRandom RANDOM = new SecureRandom();
  private static final Base64.Decoder B64 = Base64.getUrlDecoder();

  private WebPushCrypto() {}

  /** 보낼 때마다 새 키·salt로 암호화해요 */
  static byte[] encrypt(byte[] plaintext, String p256dh, String auth)
      throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
    generator.initialize(new ECGenParameterSpec("secp256r1"), RANDOM);
    byte[] salt = new byte[16];
    RANDOM.nextBytes(salt);
    return encrypt(plaintext, decode(p256dh), decode(auth), generator.generateKeyPair(), salt);
  }

  /** 키 쌍·salt를 받는 쪽 (테스트에서 RFC 예제 값을 넣어요) */
  static byte[] encrypt(
      byte[] plaintext, byte[] uaPublic, byte[] authSecret, KeyPair sender, byte[] salt)
      throws GeneralSecurityException {
    if (plaintext.length > MAX_PLAINTEXT_BYTES) {
      throw new GeneralSecurityException("내용이 " + MAX_PLAINTEXT_BYTES + "바이트를 넘어요");
    }
    if (authSecret.length != 16 || salt.length != 16) {
      throw new GeneralSecurityException("auth·salt는 16바이트예요");
    }
    ECPublicKey receiver = publicKey(uaPublic); // 곡선 위의 점이 아니면 여기서 실패해요
    byte[] asPublic = encodePublic((ECPublicKey) sender.getPublic());

    KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
    agreement.init(sender.getPrivate());
    agreement.doPhase(receiver, true);
    byte[] ecdhSecret = agreement.generateSecret();

    // 기기의 auth로 키 섞기: IKM = HKDF(salt=auth, ikm=ecdh, info="WebPush: info\0"‖ua_public‖as_public)
    byte[] keyInfo = concat(ascii("WebPush: info\0"), uaPublic, asPublic);
    byte[] ikm = expand(hmac(authSecret, ecdhSecret), keyInfo, 32);
    // 내용 키·nonce: PRK = HKDF-Extract(salt, IKM) (RFC 8188)
    byte[] prk = hmac(salt, ikm);
    byte[] cek = expand(prk, ascii("Content-Encoding: aes128gcm\0"), 16);
    byte[] nonce = expand(prk, ascii("Content-Encoding: nonce\0"), 12);

    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
        Cipher.ENCRYPT_MODE, new SecretKeySpec(cek, "AES"), new GCMParameterSpec(128, nonce));
    byte[] padded = Arrays.copyOf(plaintext, plaintext.length + 1);
    padded[plaintext.length] = 0x02; // 마지막 레코드 구분 바이트
    byte[] ciphertext = cipher.doFinal(padded);

    return ByteBuffer.allocate(HEADER_BYTES + ciphertext.length)
        .put(salt)
        .putInt(RECORD_SIZE)
        .put((byte) asPublic.length)
        .put(asPublic)
        .put(ciphertext)
        .array();
  }

  /** 압축하지 않은 P-256 점(0x04 ‖ x ‖ y, 65바이트) → 공개키 */
  static ECPublicKey publicKey(byte[] uncompressed) throws GeneralSecurityException {
    if (uncompressed.length != 65 || uncompressed[0] != 0x04) {
      throw new GeneralSecurityException("P-256 공개키는 0x04로 시작하는 65바이트예요");
    }
    BigInteger x = new BigInteger(1, Arrays.copyOfRange(uncompressed, 1, 33));
    BigInteger y = new BigInteger(1, Arrays.copyOfRange(uncompressed, 33, 65));
    return (ECPublicKey)
        KeyFactory.getInstance("EC").generatePublic(new ECPublicKeySpec(new ECPoint(x, y), P256));
  }

  /** 32바이트 개인키 값 → 개인키 */
  static ECPrivateKey privateKey(byte[] d) throws GeneralSecurityException {
    if (d.length != 32) {
      throw new GeneralSecurityException("P-256 개인키는 32바이트예요");
    }
    return (ECPrivateKey)
        KeyFactory.getInstance("EC")
            .generatePrivate(new ECPrivateKeySpec(new BigInteger(1, d), P256));
  }

  /** 공개키 → 압축하지 않은 점 65바이트 */
  static byte[] encodePublic(ECPublicKey key) {
    byte[] out = new byte[65];
    out[0] = 0x04;
    fixed32(key.getW().getAffineX(), out, 1);
    fixed32(key.getW().getAffineY(), out, 33);
    return out;
  }

  static byte[] decode(String base64url) {
    return B64.decode(base64url);
  }

  private static void fixed32(BigInteger value, byte[] out, int offset) {
    byte[] raw = value.toByteArray(); // 앞에 0x00이 붙거나 32바이트보다 짧을 수 있어요
    int copy = Math.min(raw.length, 32);
    System.arraycopy(raw, raw.length - copy, out, offset + 32 - copy, copy);
  }

  /** HKDF-Expand에서 한 블록(32바이트 이하)만 쓰는 경우 */
  private static byte[] expand(byte[] prk, byte[] info, int length)
      throws GeneralSecurityException {
    return Arrays.copyOf(hmac(prk, concat(info, new byte[] {0x01})), length);
  }

  private static byte[] hmac(byte[] key, byte[] data) throws GeneralSecurityException {
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(key, "HmacSHA256"));
    return mac.doFinal(data);
  }

  private static byte[] concat(byte[]... parts) {
    ByteBuffer buffer = ByteBuffer.allocate(Arrays.stream(parts).mapToInt(p -> p.length).sum());
    for (byte[] part : parts) {
      buffer.put(part);
    }
    return buffer.array();
  }

  private static byte[] ascii(String value) {
    return value.getBytes(StandardCharsets.US_ASCII);
  }

  private static ECParameterSpec p256() {
    try {
      AlgorithmParameters parameters = AlgorithmParameters.getInstance("EC");
      parameters.init(new ECGenParameterSpec("secp256r1"));
      return parameters.getParameterSpec(ECParameterSpec.class);
    } catch (GeneralSecurityException e) {
      throw new IllegalStateException("이 JDK에 P-256이 없어요", e);
    }
  }
}
