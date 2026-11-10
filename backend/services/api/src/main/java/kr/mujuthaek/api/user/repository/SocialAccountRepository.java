package kr.mujuthaek.api.user.repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.SocialAccount;
import kr.mujuthaek.api.user.domain.SocialProvider;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SocialAccountRepository extends JpaRepository<SocialAccount, UUID> {

  Optional<SocialAccount> findByProviderAndProviderUserId(
      SocialProvider provider, String providerUserId);

  List<SocialAccount> findByUserIdOrderByCreatedAt(UUID userId);
}
