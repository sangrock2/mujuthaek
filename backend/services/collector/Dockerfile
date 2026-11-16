# 빌드 컨텍스트는 저장소 루트예요: docker build -f services/collector/Dockerfile -t mujuthaek-collector .
FROM python:3.12-slim
# uv 버전은 uv.lock을 만든 버전과 맞춰요 (예전 uv는 새 lock 형식을 --frozen으로 읽지 못할 수 있어요)
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 TZ=Asia/Seoul

WORKDIR /app
COPY libs/python-platform libs/python-platform
COPY services/collector services/collector
WORKDIR /app/services/collector
# 바이트코드를 미리 만들어요: 코드가 읽기 전용이라 실행 중에는 .pyc를 쓸 수 없고, CPU 한도가 낮아 시작마다 다시 컴파일하면 느려요
RUN uv sync --no-dev --frozen --compile-bytecode
# 실행할 때 uv를 거치지 않고 가상환경의 python을 바로 써요 (uv run은 시작할 때마다 패키지를 다시 확인·설치해요)
ENV PATH="/app/services/collector/.venv/bin:$PATH"
RUN python -m compileall -q /app/libs/python-platform/src /app/services/collector/src

# 일반 사용자로 실행. 코드·가상환경은 root 소유(읽기 전용)로 두고, 실행 중에 쓰는 곳은 임시 폴더(/tmp: 문서 변환·지역 적재)와
# 자기 홈뿐이에요. 침해된 프로세스가 자기 코드나 패키지를 바꿔 재시작 뒤에도 남지 못하게 해요(보안 감사 4절)
RUN useradd --create-home collector
USER collector

EXPOSE 8091
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=3)"
CMD ["python", "-m", "mujuthaek_collector", "run"]
