# 빌드 컨텍스트는 저장소 루트예요: docker build -f services/collector/Dockerfile -t mujuthaek-collector .
FROM python:3.12-slim
# uv 버전은 uv.lock을 만든 버전과 맞춰요 (예전 uv는 새 lock 형식을 --frozen으로 읽지 못할 수 있어요)
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 TZ=Asia/Seoul

WORKDIR /app
COPY libs/python-platform libs/python-platform
COPY services/collector services/collector
WORKDIR /app/services/collector
RUN uv sync --no-dev --frozen
# 실행할 때 uv를 거치지 않고 가상환경의 python을 바로 써요 (uv run은 시작할 때마다 패키지를 다시 확인·설치해요)
ENV PATH="/app/services/collector/.venv/bin:$PATH"

# 일반 사용자로 실행
RUN useradd --create-home collector && chown -R collector /app
USER collector

EXPOSE 8091
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=3)"
CMD ["python", "-m", "mujuthaek_collector", "run"]
