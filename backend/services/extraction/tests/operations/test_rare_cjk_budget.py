"""AI 비용 상한 추정은 UTF-8 바이트 수로 (2026-11-16 보안 감사 L-21). 네트워크·유료 호출 없음.

o200k 토크나이저 실측(2026-11-16, 내려받아 둔 인코딩으로 오프라인): CJK 확장 B 한자 1,000자 = 3,982토큰(글자당 3.98),
확장 A 1,000자 = 2,977토큰, 보통 한국어 공고 글 1,110자 = 722토큰. 바이트 단위 BPE라 토큰 수는 UTF-8 바이트 수(4,000·3,000·2,270)를
넘지 않아요. 예전 글자 수 예약은 드문 한자 글에서 실제의 약 1/4, 장문 요율 경계를 넘으면 그보다 더 낮게 잡혔어요."""

import dataclasses
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from mujuthaek_extraction.model.base import ModelRequest
from mujuthaek_extraction.model.openai_responses import RUNAWAY_CHECK_CHARS, OpenAIResponsesModel
from mujuthaek_extraction.model.pricing import PRICES, Budget, input_token_ceiling
from mujuthaek_extraction.v2.llm.budget import worst_case_usd
from tests.model.test_openai_model import FAKE_KEY, FakeStream, deltas, request_for

RARE = "".join(chr(0x20000 + i * 7) for i in range(1000))  # CJK 확장 B 1,000자(UTF-8 4바이트씩)
MEASURED_TOKENS_PER_CHAR = 3.98  # 위 글의 o200k 실측(3,982토큰)
PRICE = PRICES["gpt-6-luna"]


def request(user: str, max_output_tokens: int = 1000) -> ModelRequest:
    return ModelRequest(prompt_version="t", call_name="c", system="", user=user, instructions="", output_schema={}, max_output_tokens=max_output_tokens)


def real_cost(text: str, max_output_tokens: int = 1000) -> float:
    """실측 비율로 센 그 글의 실제 비용(캐시 없는 입력 요율, 장문이면 장문 요율)."""
    return PRICE.usd(int(len(text) * MEASURED_TOKENS_PER_CHAR), 0, 0, max_output_tokens)


def test_token_ceiling_is_the_utf8_byte_length():
    assert input_token_ceiling(RARE) == 4000 >= 3982  # 실측 토큰 수 이상
    assert input_token_ceiling("가나다") == 9 and input_token_ceiling("abc") == 3
    assert input_token_ceiling("\ud800") == 3  # 짝 없는 서로게이트도 예외 없이 세요


def test_rare_cjk_request_is_reserved_at_or_above_its_real_cost_across_the_long_context_boundary():
    text = RARE * 70  # 7만 자 = 28만 바이트. 실측 비율이면 약 27.9만 토큰이라 장문 요율(27.2만 초과)
    worst = Budget("gpt-6-luna", 1.0).worst_case(request(text))
    assert worst >= real_cost(text)
    assert PRICE.worst_usd(len(text), 1000) * 6 < real_cost(text)  # 예전(글자 수) 예약은 실제 비용의 1/6도 안 됐어요
    # 공고 상한이 실제 비용보다 작으면 보내지 않아요(예전엔 글자 수 예약이 상한 안이라 보냈어요)
    assert not Budget("gpt-6-luna", real_cost(text) * 0.9).allow(request(text))
    short = RARE * 10  # 장문 요율 밖에서도 실제 비용 이상
    assert Budget("gpt-6-luna", 1.0).worst_case(request(short)) >= real_cost(short)


def test_v2_reservation_counts_bytes_too():
    text = RARE * 70
    req = SimpleNamespace(messages=[HumanMessage(text)], system_message=SystemMessage("공고를 읽어요"), tools=[])
    assert worst_case_usd(req, "gpt-6-luna", 1000) >= real_cost(text)


def test_aborted_stream_without_an_earlier_record_counts_input_by_bytes():
    # 폭주로 끊은 응답은 제공자가 사용량을 주지 않아 추정해요. 같은 원문을 앞서 보낸 기록이 없으면 입력을 예약과 같은 상한으로 세요
    req = dataclasses.replace(request_for(0), user=RARE * 5)
    looping = '{"quotes":[{"id":"q1","text":"' + "가" * (RUNAWAY_CHECK_CHARS * 2)
    model = OpenAIResponsesModel(FAKE_KEY, opener=FakeStream(deltas(looping)), stream=True, runaway_check=lambda raw, name: "반복")
    response = model.complete(req)
    sent = req.system + req.user + req.instructions
    assert response.usage["estimated"] is True and response.input_tokens == input_token_ceiling(sent)
    assert response.input_tokens >= len(req.user) * MEASURED_TOKENS_PER_CHAR  # 예전 추정(1.5자 = 1토큰)은 이 글에서 약 1/6
