"""시험은 LangSmith로 추적을 보내지 않습니다: .env에 추적 설정이 있어도 모델 공장이 넘기지 않게(이미 있는 환경 변수는 그대로 둠) 먼저 끕니다."""

import os

os.environ.setdefault("LANGSMITH_TRACING", "false")
