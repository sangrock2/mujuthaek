package kr.mujuthaek.api.notification.controller;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notification.controller.spec.PushSubscriptionApiSpec;
import kr.mujuthaek.api.notification.dto.request.PushSubscribeRequest;
import kr.mujuthaek.api.notification.dto.request.PushUnsubscribeRequest;
import kr.mujuthaek.api.notification.dto.response.PushDeviceResponse;
import kr.mujuthaek.api.notification.dto.response.PushPublicKeyResponse;
import kr.mujuthaek.api.notification.service.internal.PushSubscriptionService;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 웹 푸시 구독 (설명은 {@link PushSubscriptionApiSpec}). 계약은 contracts/schemas/web-push.draft.md 2장이에요. */
@RestController
class PushSubscriptionController implements PushSubscriptionApiSpec {

  static final String ME = "/api/users/me/push-subscriptions";

  private final PushSubscriptionService subscriptions;

  PushSubscriptionController(PushSubscriptionService subscriptions) {
    this.subscriptions = subscriptions;
  }

  @Override
  @GetMapping("/api/v1/push/public-key")
  public PushPublicKeyResponse publicKey() {
    return new PushPublicKeyResponse(subscriptions.publicKey());
  }

  @Override
  @PutMapping(ME)
  public ResponseEntity<Void> subscribe(
      @AuthenticationPrincipal LoginUser user, @Valid @RequestBody PushSubscribeRequest request) {
    subscriptions.subscribe(
        user.userId(),
        request.endpoint(),
        request.keys().p256dh(),
        request.keys().auth(),
        request.userAgent());
    return ResponseEntity.noContent().build();
  }

  @Override
  @DeleteMapping(ME)
  public ResponseEntity<Void> unsubscribe(
      @AuthenticationPrincipal LoginUser user,
      @RequestParam(required = false) String scope,
      @RequestBody(required = false) PushUnsubscribeRequest request) {
    if (scope != null) {
      if (!"all".equals(scope)) {
        throw new CustomException(ErrorCode.VALIDATION_FAILED, "scope: all만 돼요");
      }
      subscriptions.unsubscribeAll(user.userId());
    } else {
      if (request == null || request.endpoint() == null || request.endpoint().isBlank()) {
        throw new CustomException(ErrorCode.VALIDATION_FAILED, "endpoint: 꼭 있어야 해요");
      }
      subscriptions.unsubscribe(user.userId(), request.endpoint());
    }
    return ResponseEntity.noContent().build();
  }

  @Override
  @GetMapping(ME)
  public List<PushDeviceResponse> devices(@AuthenticationPrincipal LoginUser user) {
    return subscriptions.devices(user.userId()).stream()
        .map(d -> new PushDeviceResponse(d.id(), d.userAgent(), d.createdAt(), d.updatedAt()))
        .toList();
  }

  @Override
  @DeleteMapping(ME + "/{id}")
  public ResponseEntity<Void> remove(
      @AuthenticationPrincipal LoginUser user, @PathVariable UUID id) {
    subscriptions.remove(user.userId(), id);
    return ResponseEntity.noContent().build();
  }
}
