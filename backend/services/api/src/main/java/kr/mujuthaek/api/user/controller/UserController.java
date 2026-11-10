package kr.mujuthaek.api.user.controller;

import jakarta.validation.Valid;
import java.util.Locale;
import kr.mujuthaek.api.user.controller.spec.UserApiSpec;
import kr.mujuthaek.api.user.dto.request.ContactEmailRequest;
import kr.mujuthaek.api.user.dto.response.MeResponse;
import kr.mujuthaek.api.user.dto.response.MyReportsResponse;
import kr.mujuthaek.api.user.dto.response.WithdrawalResponse;
import kr.mujuthaek.api.user.service.ContactEmailService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.MyReportService;
import kr.mujuthaek.api.user.service.UserService;
import kr.mujuthaek.api.user.service.WithdrawalService;
import kr.mujuthaek.api.user.service.WithdrawalStart;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

/** 내 계정 (설명은 {@link UserApiSpec}). */
@RestController
@RequestMapping("/api/users")
class UserController implements UserApiSpec {

  private final UserService userService;
  private final WithdrawalService withdrawalService;
  private final ContactEmailService contactEmails;
  private final MyReportService myReports;

  UserController(
      UserService userService,
      WithdrawalService withdrawalService,
      ContactEmailService contactEmails,
      MyReportService myReports) {
    this.userService = userService;
    this.withdrawalService = withdrawalService;
    this.contactEmails = contactEmails;
    this.myReports = myReports;
  }

  @Override
  @PostMapping("/me/withdrawal")
  public WithdrawalResponse startWithdrawal(
      @AuthenticationPrincipal LoginUser user, @RequestParam(required = false) String provider) {
    WithdrawalStart start = withdrawalService.start(user.userId(), provider);
    String reauthUrl =
        ServletUriComponentsBuilder.fromCurrentContextPath()
            .path("/oauth2/authorization/{provider}")
            .queryParam("withdraw", start.ticket())
            .buildAndExpand(start.provider().toLowerCase(Locale.ROOT))
            .toUriString();
    return new WithdrawalResponse(
        start.provider(), reauthUrl, start.ttl().toSeconds(), start.otherProviders());
  }

  @Override
  @GetMapping("/me")
  public MeResponse me(@AuthenticationPrincipal LoginUser user) {
    return userService.getMe(user.userId());
  }

  @Override
  @GetMapping("/me/reports")
  public MyReportsResponse myReports(@AuthenticationPrincipal LoginUser user) {
    return new MyReportsResponse(myReports.mine(user.userId()));
  }

  @Override
  @PutMapping("/me/email")
  public ResponseEntity<Void> changeEmail(
      @AuthenticationPrincipal LoginUser user, @Valid @RequestBody ContactEmailRequest request) {
    contactEmails.change(user.userId(), request.email(), request.consentVersion());
    return ResponseEntity.noContent().build();
  }

  @Override
  @DeleteMapping("/me/email")
  public ResponseEntity<Void> removeEmail(@AuthenticationPrincipal LoginUser user) {
    contactEmails.remove(user.userId());
    return ResponseEntity.noContent().build();
  }
}
