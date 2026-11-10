-- 적재기가 내용이 같은 줄은 건드리지 않게 바뀌어서(기준일도 그대로), 줄의 data_date 뜻을 칸 설명으로 남겨요.
-- 원천 파일의 기준일은 area.load_runs.data_date에 있어요.
comment on column area.facilities.data_date is '이 줄이 마지막으로 바뀐 적재의 원천 기준일 (원천 파일 기준일은 area.load_runs.data_date)';
comment on column area.stores.data_date is '이 줄이 마지막으로 바뀐 적재의 원천 기준일 (원천 파일 기준일은 area.load_runs.data_date)';
