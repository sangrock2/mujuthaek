package kr.mujuthaek.api.user.controller;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.time.LocalDate;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.user.controller.spec.PreparationApiSpec;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.PreparationService;
import kr.mujuthaek.api.user.service.PreparationService.Response;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/** 로그인 사용자의 신청 준비함. 타인 준비함을 조회/수정할 수 없다. */
@RestController
@RequestMapping("/api/users/me/preparations")
public class PreparationController implements PreparationApiSpec {
  private final PreparationService service;

  public PreparationController(PreparationService service) {
    this.service = service;
  }

  public record StatusRequest(
      String status, Boolean restore, @NotNull @Min(0) Long expectedRevision) {}

  public record DocumentRequest(
      @NotBlank String state,
      @NotBlank String sourceRevision,
      @NotNull @Min(0) Long expectedRevision) {}

  public record AcknowledgementRequest(
      @NotBlank String sourceRevision, @NotNull @Min(0) Long expectedRevision) {}

  public record AddTaskRequest(
      @NotBlank @Size(max = 120) String title,
      LocalDate dueOn,
      @NotNull @Min(0) Long expectedRevision) {}

  public record UpdateTaskRequest(
      @NotBlank @Size(max = 120) String title,
      LocalDate dueOn,
      @NotNull Boolean done,
      @NotNull @Min(0) Long expectedRevision) {}

  @GetMapping
  public CursorPageResponse<Response> list(
      @AuthenticationPrincipal LoginUser user,
      @RequestParam(required = false) String status,
      @RequestParam(required = false) String cursor,
      @RequestParam(required = false) Integer size) {
    return service.list(user.userId(), status, cursor, size);
  }

  @PutMapping("/notices/{noticeId}")
  public ResponseEntity<Response> create(
      @AuthenticationPrincipal LoginUser user, @PathVariable UUID noticeId) {
    var result = service.create(user.userId(), noticeId);

    return result.created()
        ? ResponseEntity.created(
                URI.create("/api/users/me/preparations/" + result.preparation().id()))
            .body(result.preparation())
        : ResponseEntity.ok(result.preparation());
  }

  @GetMapping("/{id}")
  public Response get(@AuthenticationPrincipal LoginUser user, @PathVariable UUID id) {
    return service.get(user.userId(), id);
  }

  @PatchMapping("/{id}")
  public Response change(
      @AuthenticationPrincipal LoginUser user,
      @PathVariable UUID id,
      @Valid @RequestBody StatusRequest request) {
    return service.change(
        user.userId(),
        id,
        request.status(),
        Boolean.TRUE.equals(request.restore()),
        request.expectedRevision());
  }

  @PutMapping("/{id}/documents/{documentId}")
  public Response document(
      @AuthenticationPrincipal LoginUser user,
      @PathVariable UUID id,
      @PathVariable String documentId,
      @Valid @RequestBody DocumentRequest request) {
    return service.document(
        user.userId(),
        id,
        documentId,
        request.state(),
        request.sourceRevision(),
        request.expectedRevision());
  }

  @PostMapping("/{id}/acknowledgements")
  public Response acknowledge(
      @AuthenticationPrincipal LoginUser user,
      @PathVariable UUID id,
      @Valid @RequestBody AcknowledgementRequest request) {
    return service.acknowledge(
        user.userId(), id, request.sourceRevision(), request.expectedRevision());
  }

  @DeleteMapping("/{id}")
  public ResponseEntity<Void> delete(
      @AuthenticationPrincipal LoginUser user, @PathVariable UUID id) {
    service.delete(user.userId(), id);
    return ResponseEntity.noContent().build();
  }

  @PostMapping("/{id}/tasks")
  public Response addTask(
      @AuthenticationPrincipal LoginUser user,
      @PathVariable UUID id,
      @Valid @RequestBody AddTaskRequest request) {
    return service.addTask(
        user.userId(), id, request.title(), request.dueOn(), request.expectedRevision());
  }

  @PutMapping("/{id}/tasks/{taskId}")
  public Response updateTask(
      @AuthenticationPrincipal LoginUser user,
      @PathVariable UUID id,
      @PathVariable UUID taskId,
      @Valid @RequestBody UpdateTaskRequest request) {
    return service.updateTask(
        user.userId(),
        id,
        taskId,
        request.title(),
        request.dueOn(),
        request.done(),
        request.expectedRevision());
  }

  @DeleteMapping("/{id}/tasks/{taskId}")
  public Response deleteTask(
      @AuthenticationPrincipal LoginUser user,
      @PathVariable UUID id,
      @PathVariable UUID taskId,
      @RequestParam long expectedRevision) {
    return service.deleteTask(user.userId(), id, taskId, expectedRevision);
  }
}
