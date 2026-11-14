package kr.mujuthaek.api.user.controller;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import kr.mujuthaek.api.user.service.EmailNotificationService;
import kr.mujuthaek.api.user.service.EmailNotificationService.Settings;
import kr.mujuthaek.api.user.service.EmailNotificationService.Status;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users/me/email-notifications")
class EmailNotificationController {
  private final EmailNotificationService emails;

  EmailNotificationController(EmailNotificationService emails) {
    this.emails = emails;
  }

  record Address(@NotBlank @Size(max = 254) String email, boolean consent) {}

  record Token(@NotBlank @Size(max = 128) String token) {
    @Override
    public String toString() {
      return "EmailToken[REDACTED]";
    }
  }

  @GetMapping
  Status get(@AuthenticationPrincipal LoginUser user) {
    return emails.get(user.userId());
  }

  @PostMapping("/request")
  Status request(@AuthenticationPrincipal LoginUser user, @Valid @RequestBody Address body) {
    if (!body.consent())
      throw new kr.mujuthaek.api.common.exception.CustomException(
          kr.mujuthaek.api.common.exception.ErrorCode.VALIDATION_FAILED, "이메일 수집·이용 동의가 필요해요");
    return emails.request(user.userId(), body.email());
  }

  @PostMapping("/verify")
  Status verify(@AuthenticationPrincipal LoginUser user, @Valid @RequestBody Token body) {
    return emails.verify(user.userId(), body.token());
  }

  @PutMapping
  Status save(@AuthenticationPrincipal LoginUser user, @RequestBody Settings body) {
    return emails.save(user.userId(), body);
  }

  @DeleteMapping
  void remove(@AuthenticationPrincipal LoginUser user) {
    emails.remove(user.userId());
  }
}
