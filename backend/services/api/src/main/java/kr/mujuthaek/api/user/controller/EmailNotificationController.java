package kr.mujuthaek.api.user.controller;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import kr.mujuthaek.api.user.service.EmailNotificationService;
import kr.mujuthaek.api.user.service.EmailNotificationService.Settings;
import kr.mujuthaek.api.user.service.EmailNotificationService.Status;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users/me/email-notifications")
public class EmailNotificationController
    implements kr.mujuthaek.api.user.controller.spec.EmailNotificationApiSpec {
  private final EmailNotificationService emails;

  EmailNotificationController(EmailNotificationService emails) {
    this.emails = emails;
  }

  public record Address(@NotBlank @Size(max = 254) String email, boolean consent) {}

  public record Token(@NotBlank @Size(max = 128) String token) {
    @Override
    public String toString() {
      return "EmailToken[REDACTED]";
    }
  }

  public record Code(@NotBlank @Pattern(regexp = "[0-9]{6}") String code) {
    @Override
    public String toString() {
      return "EmailCode[REDACTED]";
    }
  }

  @GetMapping
  public Status get(@AuthenticationPrincipal LoginUser user) {
    return emails.get(user.userId());
  }

  @PostMapping("/request")
  public Status request(@AuthenticationPrincipal LoginUser user, @Valid @RequestBody Address body) {
    requireConsent(body);
    return emails.request(user.userId(), body.email());
  }

  @PostMapping("/request-code")
  public Status requestCode(
      @AuthenticationPrincipal LoginUser user, @Valid @RequestBody Address body) {
    requireConsent(body);
    return emails.requestCode(user.userId(), body.email());
  }

  @PostMapping("/verify-code")
  public Status verifyCode(@AuthenticationPrincipal LoginUser user, @Valid @RequestBody Code body) {
    return emails.verifyCode(user.userId(), body.code());
  }

  private void requireConsent(Address body) {
    if (!body.consent())
      throw new kr.mujuthaek.api.common.exception.CustomException(
          kr.mujuthaek.api.common.exception.ErrorCode.VALIDATION_FAILED, "이메일 수집·이용 동의가 필요해요");
  }

  @PostMapping("/verify")
  public Status verify(@AuthenticationPrincipal LoginUser user, @Valid @RequestBody Token body) {
    return emails.verify(user.userId(), body.token());
  }

  @PutMapping
  public Status save(@AuthenticationPrincipal LoginUser user, @RequestBody Settings body) {
    return emails.save(user.userId(), body);
  }

  @PostMapping("/edit")
  public Status edit(@AuthenticationPrincipal LoginUser user) {
    emails.withdraw(user.userId());
    return emails.get(user.userId());
  }

  @DeleteMapping
  public void remove(@AuthenticationPrincipal LoginUser user) {
    emails.withdraw(user.userId());
  }
}
