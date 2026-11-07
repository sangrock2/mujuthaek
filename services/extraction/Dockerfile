# 빌드 컨텍스트는 저장소 루트입니다: docker build -f services/extraction/Dockerfile -t mujuthaek-extraction .
FROM python:3.12-slim
# uv 버전은 uv.lock을 만든 버전과 맞춥니다
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 TZ=Asia/Seoul

WORKDIR /app
COPY libs/python-platform libs/python-platform
# 결합·검증이 계약 스키마와 검사 도구를 읽습니다
COPY contracts contracts
COPY services/extraction services/extraction
WORKDIR /app/services/extraction
# OCR: 두 판독이 같아도 OCR에 없는 숫자는 불일치로(같은 쪽으로 잘못 읽은 값 막기), 남은 불일치는 세 번째 판독(EXTRACTION_IMAGE_THIRD_READING)
RUN uv sync --no-dev --frozen --extra ocr
ENV PATH="/app/services/extraction/.venv/bin:$PATH" CONTRACTS_DIR=/app/contracts EXTRACTION_REVIEW_HOST=0.0.0.0

RUN useradd --create-home extraction && chown -R extraction /app
USER extraction

EXPOSE 8092
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health', timeout=3)"
CMD ["python", "-m", "mujuthaek_extraction", "run"]
