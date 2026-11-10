package kr.mujuthaek.api.user.controller;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.user.controller.spec.AdminUserApiSpec;
import kr.mujuthaek.api.user.dto.request.AdminRequests;
import kr.mujuthaek.api.user.dto.request.RoleChangeRequest;
import kr.mujuthaek.api.user.dto.response.AdminMeResponse;
import kr.mujuthaek.api.user.dto.response.AdminUserResponse;
import kr.mujuthaek.api.user.service.AdminUserService;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 관리자 회원 관리 (설명은 {@link AdminUserApiSpec}). 경로마다 필요한 권한은 SecurityConfig(AdminAuthorization)가 먼저 보고,
 * 주고 빼는 규칙은 AdminUserService가 봐요.
 */
@RestController
@RequestMapping("/api/admin")
class AdminUserController implements AdminUserApiSpec {

  private final AdminUserService users;

  AdminUserController(AdminUserService users) {
    this.users = users;
  }

  @Override
  @GetMapping("/me")
  public AdminMeResponse me(@AuthenticationPrincipal LoginUser admin) {
    return users.me(admin.userId());
  }

  @Override
  @GetMapping("/users")
  public AdminUserResponse.Page list(
      @RequestParam(required = false) String query,
      @RequestParam(required = false) String filter,
      @RequestParam(defaultValue = "0") int page) {
    return users.search(query, filter, page);
  }

  @Override
  @GetMapping("/users/names")
  public List<AdminUserResponse.Name> names(@RequestParam List<UUID> ids) {
    return users.names(ids);
  }

  @Override
  @PatchMapping("/users/{id}/role")
  public AdminUserResponse changeRole(
      @PathVariable UUID id,
      @Valid @RequestBody RoleChangeRequest request,
      @AuthenticationPrincipal LoginUser admin) {
    return users.changeRole(id, request.role(), admin.userId());
  }

  @Override
  @PutMapping("/users/{id}/permissions")
  public AdminUserResponse permissions(
      @PathVariable UUID id,
      @Valid @RequestBody AdminRequests.Permissions request,
      @AuthenticationPrincipal LoginUser admin) {
    return users.setPermissions(id, request.permissions(), admin.userId());
  }

  @Override
  @PutMapping("/users/{id}/suspension")
  public AdminUserResponse suspend(
      @PathVariable UUID id,
      @Valid @RequestBody AdminRequests.Suspend request,
      @AuthenticationPrincipal LoginUser admin) {
    return users.suspend(id, request.reason(), request.until(), admin.userId());
  }

  @Override
  @DeleteMapping("/users/{id}/suspension")
  public AdminUserResponse unsuspend(
      @PathVariable UUID id, @AuthenticationPrincipal LoginUser admin) {
    return users.unsuspend(id, admin.userId());
  }

  @Override
  @GetMapping("/users/changes")
  public List<AdminUserResponse.Change> changes(@RequestParam(defaultValue = "30") int days) {
    return users.changes(days);
  }

  @Override
  @PostMapping("/super/transfer")
  public AdminUserResponse transfer(
      @Valid @RequestBody AdminRequests.Transfer request,
      @AuthenticationPrincipal LoginUser admin) {
    return users.transfer(request.userId(), admin.userId());
  }

  @Override
  @PutMapping("/super/freeze")
  public AdminMeResponse freeze(
      @Valid @RequestBody(required = false) AdminRequests.Freeze request,
      @AuthenticationPrincipal LoginUser admin) {
    return users.freeze(request == null ? null : request.reason(), admin.userId());
  }

  @Override
  @DeleteMapping("/super/freeze")
  public AdminMeResponse unfreeze(@AuthenticationPrincipal LoginUser admin) {
    return users.unfreeze(admin.userId());
  }
}
