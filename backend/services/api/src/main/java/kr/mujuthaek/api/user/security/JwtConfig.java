package kr.mujuthaek.api.user.security;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import kr.mujuthaek.api.user.service.JwtProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

/** access token 서명(HS256)과 검증. 검증은 서명·만료·발급자(iss)를 봐요. */
@Configuration
class JwtConfig {

  @Bean
  JwtEncoder jwtEncoder(JwtProperties props) {
    return new NimbusJwtEncoder(new ImmutableSecret<>(key(props)));
  }

  @Bean
  JwtDecoder jwtDecoder(JwtProperties props) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withSecretKey(key(props)).macAlgorithm(MacAlgorithm.HS256).build();
    decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(props.issuer()));
    return decoder;
  }

  private static SecretKey key(JwtProperties props) {
    return new SecretKeySpec(props.secretBytes(), "HmacSHA256");
  }
}
