"""PDF 안에 그림으로 들어간 표 읽기 (2026-10-16 시험 후 추가).

글자로 읽히지 않는 큰 그림(쪽의 25% 이상, intake/pdf_reader.image_pages)이 있는 쪽만 그림으로 그려 그림을 받는 모델에 보내고,
모델이 옮긴 글자를 원문 끝에 「=== 그림 판독 … ===」 묶음으로 붙입니다. 이후 추출·근거 확인은 이 글자를 원문처럼 씁니다.
실측: SH 청년주택 공고의 임대조건 표(호실별 면적·보증금·월세)가 그림이라 가격 0개로 나오던 것.

판독 글자는 사람이 원문과 맞춰 본 것이 아니므로, 그 글자를 근거로 한 자격·공고 정보는 사람 확인으로 보냅니다
(verify/consistency.py `EVIDENCE_FROM_IMAGE`). 판독이 실패해도 추출은 계속하고, 그림 표 의심 검사가 사람 확인으로 보냅니다.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import io
import logging
import re
from typing import Any

from mujuthaek_extraction.extract import CallAttempt, ExtractionRun, _parse, schema_errors
from mujuthaek_extraction.intake.model import ExtractionMaterial, TrustedContext
from mujuthaek_extraction.intake.pdf_reader import image_pages
from mujuthaek_extraction.intake.xlsx_reader import redact_secret_values
from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelImage, ModelRequest, StopReason
from mujuthaek_extraction.rules.base import output_limit

log = logging.getLogger(__name__)

# 주민등록번호 모양(서식 예시 그림에 견본 번호가 있음, SH 특화형 매입임대 실측)은 판독 글자에 남기지 않습니다
RESIDENT_NUMBER = re.compile(r"(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)")
BLOCK_HEAD = "=== 그림 판독 "  # 판독 글자 묶음의 머리 (검증기가 이 묶음 안의 근거를 찾습니다)
BLOCK_NOTE = "(AI가 그림 속 글자를 옮김, 원문 그림으로 확인 필요)"
CHECK_CALL = "image_text_check"  # 같은 그림을 따로 한 번 더 읽는 호출(두 판독을 줄마다 맞춰 봄)
# 두 판독이 다른 줄의 묶음. 줄의 「|」는 「¦」로 바꿔 적어 표 행·인용 위치로 잡히지 않게 합니다(verify/consistency가 되돌려 비교)
DISPUTED_HEAD = "=== 그림 판독 불일치 (두 번 읽은 글자가 다른 줄) ==="
DISPUTED_LINE = "불일치 줄: "
DISPUTED_BAR = "¦"
MAX_IMAGES = 6  # 한 공고에서 그려 보낼 쪽 수 상한 (비용)
RESOLUTION = 200  # 그림 영역 해상도(dpi). 120dpi 쪽 전체 그림에서는 표의 작은 숫자(27.02/27.07)가 헷갈렸음
IMAGE_SHARE = 0.25  # pdf_reader.IMAGE_PAGE_SHARE와 같은 기준으로 자를 그림을 고릅니다
PROMPT_VERSION = "image_text/v1"
# 실측 최대 2,019(GH 783, 시도 6건)지만 한 호출에 쪽 그림을 6장까지 보내 표가 빽빽하면 쪽마다 수천 토큰이라 그대로 둡니다
# (잘리면 판독 글자를 모두 잃음). 설정 EXTRACTION_MAX_OUTPUT_TOKENS의 image_text로 바꿀 수 있습니다
MAX_OUTPUT_TOKENS = 16_000
INSTRUCTIONS = """첨부한 그림은 주거 공고 PDF의 쪽을 그린 것입니다. 그림 안의 글자를 그대로 옮깁니다.
- 표는 행마다 한 줄로, 칸은 " | "로 나눠 적습니다(머리 행 포함). 합친 칸은 해당하는 칸마다 같은 값을 적습니다.
- 숫자·단위·기호는 그림에 보이는 그대로 적습니다(계산·반올림·단위 바꾸기 하지 않음). 읽을 수 없는 칸은 [판독 불가]로 적습니다.
- 그림에 없는 내용을 지어내지 않습니다. 지도·사진·평면도처럼 옮길 글자 정보가 거의 없으면 text를 빈 글자로 둡니다.
- 출입문 비밀번호 같은 값은 옮기지 않습니다.
그림마다 {"image": <그림 번호>, "text": "<옮긴 글자>"} 하나를 pages에 넣은 JSON 객체 하나만 출력합니다."""
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pages"],
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["image", "text"],
                "properties": {"image": {"type": "integer"}, "text": {"type": "string"}},
            },
        }
    },
}


def _render(data: bytes, page_number: int) -> bytes:
    """그 쪽의 큰 그림 영역만 잘라 RESOLUTION dpi로 그립니다(쪽 전체를 그리면 작은 숫자가 뭉개짐)."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[page_number - 1]
        area = float(page.width * page.height) or 1.0
        boxes = [
            (max(float(i["x0"]), 0.0), max(float(i["top"]), 0.0), min(float(i["x1"]), float(page.width)), min(float(i["bottom"]), float(page.height)))
            for i in page.images
        ]
        boxes = [b for b in boxes if (b[2] - b[0]) * (b[3] - b[1]) / area >= IMAGE_SHARE]
        if boxes:
            page = page.crop((min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)))
        picture = page.to_image(resolution=RESOLUTION).original
        out = io.BytesIO()
        picture.save(out, format="PNG")
        return out.getvalue()


def image_targets(material: ExtractionMaterial) -> list[tuple[str, str, bytes, int]]:
    """(문서 ID, 파일 이름, PDF 바이트, 쪽 번호): 글자 없는 큰 그림이 있는 쪽. 앞에서부터 MAX_IMAGES쪽까지."""
    targets = []
    for file in material.files:
        if file.file_type != "pdf":  # 이벤트의 fileType으로 판단 (이름 끝 공백·확장자 없는 PDF도 읽음)
            continue
        for page, _ in image_pages(file.data):
            if (file.document_id, page) not in {(t[0], t[3]) for t in targets}:
                targets.append((file.document_id, file.name, file.data, page))
    return targets[:MAX_IMAGES]


def bordered(text: str) -> str:
    """판독한 표 행(「a | b | c」)을 PDF 표 글과 같은 「| a | b | c |」 모양으로 바꿉니다. 칸 글자는 그대로 둡니다.
    공급표를 코드가 행 단위로 옮길 때(supply_tables.image_tables) 인용 줄이 원문 줄과 같아지게 합니다."""
    lines = []
    for line in text.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        lines.append("| " + " | ".join(cells) + " |" if "|" in line and len(cells) >= 2 else line)
    return "\n".join(lines)


def _clean(text: str) -> str:
    return bordered(RESIDENT_NUMBER.sub("******-*******", redact_secret_values(text.strip())))


def _key(line: str) -> str:
    return "".join(line.split())


def _read(model: ExtractionModel, request: ModelRequest, run: ExtractionRun) -> dict[str, Any] | None:
    """판독 호출 한 번. 실패·잘림·형식 오류면 None(기록은 run에)."""
    name = request.call_name
    try:
        response = model.complete(request)
    except ModelError as error:
        run.attempts.append(CallAttempt(name, PROMPT_VERSION, False, None, None, None, None, None, str(error)))
        run.failed_calls.append((name, str(error)))
        return None
    run.attempts.append(
        CallAttempt(
            name,
            PROMPT_VERSION,
            False,
            response.model_id,
            response.stop_reason.value,
            response.input_tokens,
            response.output_tokens,
            response.cached_input_tokens,
            None,
            response.cache_write_tokens,
        )
    )
    run.raw_responses.append((name, response.raw_text))
    try:
        answer = _parse(response.raw_text) if response.stop_reason is StopReason.END else None
    except ValueError:
        answer = None
    if answer is None or schema_errors(answer, SCHEMA) is not None:
        run.failed_calls.append((name, "그림 판독 응답을 읽지 못했습니다."))
        return None
    return answer


def read_image_tables(
    material: ExtractionMaterial, context: TrustedContext, model: ExtractionModel
) -> tuple[ExtractionMaterial, TrustedContext, ExtractionRun | None]:
    """그림 쪽이 없거나 원문이 PDF 글자가 아니면 그대로 돌려줍니다. 판독한 글자가 있으면 원문과 문서 해시를 바꾼 새 자료를 돌려줍니다."""
    targets = image_targets(material)
    if not targets or material.text_document_id != "pdf-text":
        return material, context, None
    run = ExtractionRun()
    try:
        images = tuple(ModelImage(f"그림 {i}", "image/png", _render(data, page)) for i, (_, _, data, page) in enumerate(targets, start=1))
    except Exception as error:  # 그리기 실패는 판독 없이 진행합니다(그림 표 의심 검사가 사람 확인으로 보냄)
        log.warning("그림 쪽을 그리지 못했습니다", extra={"error": str(error)[:200]})
        return material, context, None
    listing = "\n".join(f"- 그림 {i}: {name} {page}쪽" for i, (_, name, _, page) in enumerate(targets, start=1))
    request = ModelRequest(
        prompt_version=PROMPT_VERSION,
        call_name="image_text",
        system="그림 속 글자를 정확히 옮기는 판독기입니다.",
        user=f"# 첨부 그림\n{listing}",
        instructions=INSTRUCTIONS,
        output_schema=SCHEMA,
        max_output_tokens=output_limit("image_text", MAX_OUTPUT_TOKENS),
        images=images,
    )
    answer = _read(model, request, run)
    if answer is None:
        return material, context, run
    # 같은 그림을 한 번 더 따로 읽어 줄마다 맞춰 봅니다(2026-11-05: 실행마다 250,600을 250,500으로 읽기도 함 — 한 번 읽은 값은 오독을 걸러 낼 수 없음).
    # 두 판독이 다른 줄은 불일치 묶음에 적어 두고, 그 줄을 근거로 한 값은 검증기가 사람 확인으로 보냅니다(verify/consistency).
    # 다시 읽기에 실패하면 모든 줄이 불일치입니다
    check = _read(model, dataclasses.replace(request, call_name=CHECK_CALL, max_output_tokens=output_limit(CHECK_CALL, MAX_OUTPUT_TOKENS)), run)
    second = {page["image"]: _clean(page["text"]) for page in (check or {}).get("pages", [])}

    blocks, disputed = [], []
    for page in answer["pages"]:
        index, text = page["image"], _clean(page["text"])
        if text and 1 <= index <= len(targets):
            _, name, _, number = targets[index - 1]
            blocks.append(f"{BLOCK_HEAD}{name} {number}쪽 {BLOCK_NOTE} ===\n{text}")
            agreed = {_key(line) for line in second.get(index, "").split("\n")}
            disputed += [line for line in text.split("\n") if line.strip() and _key(line) not in agreed]
    if not blocks:
        return material, context, run
    if disputed:
        blocks.append(f"{DISPUTED_HEAD}\n" + "\n".join(DISPUTED_LINE + line.replace("|", DISPUTED_BAR) for line in disputed))
    text = "\n".join([material.text, *blocks])
    documents = copy.deepcopy(list(context.documents))
    for document in documents:
        if document["id"] == material.text_document_id:
            document["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            document["name"] = f"{document['name']} + 그림 판독"
    return dataclasses.replace(material, text=text), dataclasses.replace(context, documents=tuple(documents)), run
