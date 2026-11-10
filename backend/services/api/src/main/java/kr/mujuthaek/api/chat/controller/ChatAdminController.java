package kr.mujuthaek.api.chat.controller;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.mujuthaek.api.chat.controller.spec.ChatAdminApiSpec;
import kr.mujuthaek.api.chat.domain.ReviewStatus;
import kr.mujuthaek.api.chat.dto.request.ReviewRequest;
import kr.mujuthaek.api.chat.dto.response.ChatReportResponse;
import kr.mujuthaek.api.chat.service.ChatAdminService;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 채팅 신고 검토 (설명은 {@link ChatAdminApiSpec}). /api/admin/chat/** 은 권한 CHAT이 있는 관리자만 들어와요
 * (SecurityConfig).
 */
@RestController
@RequestMapping("/api/admin/chat")
class ChatAdminController implements ChatAdminApiSpec {

  private final ChatAdminService admin;

  ChatAdminController(ChatAdminService admin) {
    this.admin = admin;
  }

  @Override
  @GetMapping("/reports")
  public CursorPageResponse<ChatReportResponse> reports(
      @RequestParam(defaultValue = "PENDING") ReviewStatus status,
      @RequestParam(required = false) String cursor,
      @RequestParam(required = false) Integer size) {
    return admin.reports(status, cursor, size);
  }

  @Override
  @GetMapping("/reports/counts")
  public ChatReportResponse.Counts counts() {
    return admin.counts();
  }

  @Override
  @PatchMapping("/messages/{id}")
  public ResponseEntity<Void> review(
      @PathVariable UUID id,
      @Valid @RequestBody ReviewRequest request,
      @AuthenticationPrincipal LoginUser user) {
    admin.review(id, request.action(), user.userId());
    return ResponseEntity.noContent().build();
  }
}
