-- 관리자 처리 기록의 「누가 했는지」를 지우지 않아요 (2026-11-16 보안 감사 L-9).
--  · 예전에는 처리한 관리자가 탈퇴하면 granted_by·suspended_by·frozen_by·changed_by가 비어서(on delete set null),
--    관리자가 본인 탈퇴로 자기 처분 기록의 행위자를 지울 수 있었어요
--  · 이제 외래 키를 빼고 회원 ID 값을 그대로 둬요. 남는 것은 ID(UUID)뿐이고 닉네임 등은 회원 줄과 함께 지워져요
--  · 관리자는 일반 회원으로 바뀐 뒤에만 탈퇴할 수 있어요(WithdrawalService). 대상 회원이 탈퇴하면 그 회원의 기록을 지우는 것(admin_changes.user_id)은 그대로예요
alter table account.admin_permissions drop constraint if exists admin_permissions_granted_by_fkey;
alter table account.suspensions drop constraint if exists suspensions_suspended_by_fkey;
alter table account.admin_freeze drop constraint if exists admin_freeze_frozen_by_fkey;
alter table account.admin_changes drop constraint if exists admin_changes_changed_by_fkey;
