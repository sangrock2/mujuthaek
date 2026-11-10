-- 웹 푸시를 받은 기기가 「떴어요·눌렀어요」를 api에 알릴 수 있게 api 알림함 줄 ID를 함께 둬요 (예전 줄은 null)
alter table deliveries add column inbox_id uuid;
