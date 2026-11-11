// 목업(시연) 모드에서 앱 안 PDF 보기로 여는 「시연용 예시 문서」를 만들어요. 실제 기관 공고문이 아니에요.
// 목업 공고(src/mocks/notice-doc.ts)의 근거 인용 문장(anchors)과 추출 과정 목업(src/features/admin/trace.ts)의 근거 글(refs)이
// 해당 쪽에 실제 글자로 꼭 한 번씩 들어 있어야 PDF 보기가 그 문장을 강조해요. 문장을 바꾸면 이 파일과 목업을 함께 바꾸고 다시 만들어요.
//
// 도구는 프론트 의존성이 아니라서 임시 폴더에 받아 써요 (저장소에 의존성을 더하지 않아요):
//   npm install --prefix <임시>/js pdf-lib@1.17.1 @pdf-lib/fontkit@1.1.1
//   python -m pip install --target <임시>/py fonttools==4.55.0
//   node scripts/make-demo-pdfs.mjs <임시>/js <임시>/py        (frontend 폴더에서)
// 글꼴은 의존성에 있는 pretendard(OFL)에서 쓴 글자만 fontTools로 잘라 넣어요(pdf-lib 자체 subset은 한글 조합 글리프를 빠뜨려요).
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const [libDir, pyDir] = process.argv.slice(2);
if (!libDir || !pyDir) {
  console.error("사용법: node scripts/make-demo-pdfs.mjs <pdf-lib 폴더> <fonttools 폴더>");
  process.exit(1);
}
const require = createRequire(path.join(path.resolve(libDir), "noop.js"));
const { PDFDocument, rgb } = require("pdf-lib");
const fontkit = require("@pdf-lib/fontkit");

const FONT = "node_modules/pretendard/dist/public/static/alternative/Pretendard-Regular.ttf";
const OUT = "public/mock";

const A4 = [595.28, 841.89];
const MARGIN = 52;
const BODY = 12;
const LEAD = 1.55;
const INK = rgb(0.13, 0.15, 0.17);
const SUB = rgb(0.42, 0.45, 0.48);
const BRAND = rgb(0.03, 0.5, 0.36);
const LINE = rgb(0.85, 0.87, 0.89);
const TINT = rgb(0.94, 0.97, 0.95);

const DEMO_HEAD = "시연용 예시 문서 · 실제 기관 공고문이 아니에요";
const demoBox = (service) =>
  `이 문서는 「${service}」 서비스 시연을 위해 만든 예시 문서입니다. 실제 기관 공고가 아니며, 단지 이름·날짜·금액은 화면 설명을 위한 예시입니다. 신청은 반드시 기관의 실제 공고문으로 확인하세요.`;

// ---- 문서 내용 (블록: h 제목 · p 문단 · li 항목 · table 표 · gap 빈 줄) ----

const parkville = {
  file: "notice-n7.pdf",
  title: "양산 삼성파크빌 국민임대주택 선착순 입주자 모집 공고",
  sub: "공고일 2026. 9. 30. · 시연용 예시 문서",
  pages: [
    [
      { box: demoBox("무주택자들") },
      { h: "■ 신청 전 꼭 확인할 사항" },
      {
        li: "동호를 지정한 날 16시까지 안내받은 계좌로 계약금 50만 원을 입금하여야 하며, 기한 내 입금하지 않으면 지정한 동호는 취소됩니다.",
      },
      { li: "구비서류가 하나라도 누락되면 동호 지정 및 계약을 할 수 없습니다." },
      { li: "모든 서류는 공고일(2026. 9. 30.) 이후 발급분에 한합니다." },
      { li: "공고일부터 입주 시까지 세대구성원 전원이 무주택을 유지하여야 합니다." },
      { li: "1세대 1주택 신청 원칙이며, 중복 신청 시 모두 무효 처리합니다." },
      { li: "자격 적격 통보 후 단순 변심으로 계약을 해지하면 위약금을 공제하고 돌려드립니다." },
      {
        li: "현재 다른 공공임대주택에 거주 중이면 입주 전까지 기존 주택을 비워 주어야 합니다.",
      },
    ],
    [
      { h: "■ 공급 대상 및 임대 조건" },
      { p: "단지명: 삼성파크빌 · 소재지: 경상남도 양산시 두전길 42 (어곡동 8-1)" },
      {
        table: [
          ["주택형", "전용면적", "모집 호수", "임대보증금", "월 임대료"],
          ["55", "55.68㎡", "32호", "18,551,000원", "114,150원"],
        ],
        widths: [0.14, 0.18, 0.18, 0.26, 0.24],
      },
      { p: "임대보증금은 계약금 500,000원과 잔금 18,051,000원으로 나누어 납부합니다." },
      {
        p: "위 금액은 기본 임대조건이며, 보증금과 월 임대료 상호 전환 조건은 7쪽을 참고하시기 바랍니다.",
      },
      { gap: 1 },
      { h: "■ 문의처" },
      { li: "삼성파크빌 관리사무소 055-367-0335 (세대 열람 전 문의)" },
      { li: "LH 콜센터 1600-1004 (신청 관련 문의)" },
    ],
    [
      { h: "■ 신청 자격" },
      {
        p: "아래 기준을 모두 충족하는 분은 거주 지역과 관계없이 신청할 수 있습니다.",
      },
      {
        li: "신청일 현재 세대구성원 전원이 무주택이어야 하며, 공고일부터 계약 체결 시까지 이를 유지하여야 합니다.",
      },
      {
        li: "전용면적 60㎡ 이하이면서 공시가격 1억 원(수도권 1억 6천만 원) 이하인 소형·저가주택을 소유한 경우 무주택으로 봅니다.",
      },
      {
        li: "신청자는 만 19세 이상이어야 합니다. 다만, 자녀를 양육하거나 형제자매를 부양하는 미성년 세대주는 신청할 수 있습니다.",
      },
      { li: "세대가 보유한 자동차의 가액 합계가 4,542만 원 이하이어야 합니다." },
      { li: "이번 모집은 소득 및 총자산 기준을 적용하지 않습니다." },
      {
        li: "1인 가구도 신청할 수 있으며, 단독세대주의 공급 면적 제한을 적용하지 않습니다.",
      },
      { li: "외국인은 신청할 수 없습니다." },
      {
        li: "세대구성원 중 공공임대주택 불법 양도·전대로 적발된 후 4년이 지나지 않은 사람이 있으면 신청할 수 없습니다.",
      },
    ],
    [
      { h: "■ 무주택세대구성원 (참고)" },
      {
        p: "무주택세대구성원은 세대주와 주민등록표등본에 함께 오른 배우자, 직계존속, 직계비속을 말하며, 세대 분리된 배우자와 그 세대원도 포함합니다.",
      },
      {
        p: "주택 소유 여부는 건물 등기사항증명서와 건축물대장 등으로 확인하며, 분양권과 입주권도 주택으로 봅니다.",
      },
    ],
    [
      { h: "■ 모집 일정" },
      {
        p: "방문 신청 및 동호 지정·계약은 2026. 10. 12.(월)부터 11. 12.(목)까지 진행합니다.",
      },
      {
        table: [
          ["구분", "일정", "비고"],
          ["공고", "2026. 9. 30.(수)", ""],
          ["세대 열람", "10. 6.(화) ~ 11. 12.(목)", "주말·공휴일 제외"],
          ["방문 신청·계약", "10. 12.(월) ~ 11. 12.(목)", "금요일·주말·공휴일 제외"],
          ["자격 확인 결과 안내", "계약 후 약 2개월", "적격자에게 개별 안내"],
          ["입주 기간", "12. 14.(월) ~ 2027. 1. 14.(목)", "입주 전 잔금 납부"],
        ],
        widths: [0.28, 0.4, 0.32],
      },
      { gap: 1 },
      { h: "■ 선정 방법" },
      {
        li: "거주지, 순위, 배점과 관계없이 방문한 순서대로 동호를 지정하여 계약하고, 계약자의 무주택 및 자동차 기준은 계약 후 확인합니다.",
      },
      {
        li: "당일 오전 10시 이전에 도착하여 명부에 서명한 사람이 2명 이상이면 추첨으로 순번을 정합니다.",
      },
      {
        li: "오전 10시 이후 도착한 사람은 앞 순번이 끝난 뒤 명부 순서대로 남은 세대를 지정합니다.",
      },
      {
        li: "3회 호명에도 응답이 없으면 다음 순번으로 넘어가며, 해당자는 당일 마지막 순번 뒤에 지정할 수 있습니다.",
      },
      { li: "순번이 되면 즉시 동호를 지정하여야 하며, 지정 후에는 변경할 수 없습니다." },
    ],
    [
      { h: "■ 신청 방법" },
      { p: "인터넷 신청은 받지 않으며 현장 방문 접수만 가능합니다." },
      {
        li: "접수 장소: LH 경남양산권주거복지지사 (경남 양산시 물금읍 청운로 358, 국민연금공단 양산지사 2층)",
      },
      { li: "접수 시간: 10:00~16:00 (금요일·주말·공휴일 제외)" },
      { h: "■ 구비 서류" },
      { li: "개인정보 수집·이용 및 제3자 제공 동의서 (세대구성원 전원 서명)" },
      { li: "신청자 신분증 (주민등록증, 운전면허증, 여권)" },
      { li: "주민등록표등본 (세대구성 사유·일자, 세대주와의 관계 등 전부 표기)" },
      { li: "본인 도장 (서명으로 대신할 수 있음)" },
      { gap: 1 },
      { h: "■ 입주 및 거주 안내" },
      { li: "잔금을 납부하고 이삿짐 반입 후 본인 확인을 거쳐 열쇠를 받습니다." },
      {
        li: "입주 기간이 지나면 실제 입주 여부와 관계없이 다음 날부터 임대료와 관리비를 부과합니다.",
      },
      { li: "임대차계약 기간은 2년이며, 자격을 유지하면 2년 단위로 갱신할 수 있습니다." },
      { li: "관리비는 입주일부터 임대료와 별도로 부과합니다." },
    ],
    [
      { h: "■ 임대보증금과 월 임대료 상호 전환 (참고)" },
      {
        p: "임차인이 원하면 임대보증금을 올리고 월 임대료를 낮추거나, 임대보증금을 낮추고 월 임대료를 올릴 수 있습니다. 전환 한도와 전환 이율은 계약 시 안내합니다.",
      },
    ],
    [
      { h: "■ 개인정보 수집·이용 동의 (서식 예시)" },
      {
        p: "수집 항목: 성명, 주민등록번호, 주소, 연락처, 세대구성원 정보 · 이용 목적: 입주자격 확인 및 계약 관리 · 보유 기간: 계약 종료 후 5년",
      },
      { p: "위 내용은 시연용 예시이며 실제 서식이 아닙니다." },
    ],
  ],
};

const happyHousing = {
  file: "notice-n1.pdf",
  title: "○○지구 행복주택 입주자 모집 공고",
  sub: "공고일 2026. 10. 7. · 시연용 예시 문서",
  pages: [
    [
      { box: demoBox("무주택자들") },
      { h: "■ 공급 개요" },
      { p: "○○지구 행복주택 120호를 청년·신혼부부에게 주변 시세보다 낮은 임대료로 공급합니다." },
      { h: "■ 유의 사항" },
      { li: "1세대 1주택 신청 원칙이며, 중복 신청 시 모두 무효 처리합니다." },
      { li: "신청 내용이 사실과 다르면 당첨 후에도 계약할 수 없습니다." },
    ],
    [
      { h: "■ 공급 대상 및 임대 조건" },
      { p: "단지명: ○○지구 행복주택 · 소재지: 서울특별시 마포구 ○○동" },
      {
        table: [
          ["주택형", "전용면적", "모집 호수", "임대보증금", "월 임대료"],
          ["26A", "26.3㎡", "64호", "24,000,000원", "180,000원"],
          ["36B", "36.8㎡", "40호", "33,000,000원", "250,000원"],
          ["44C", "44.1㎡", "16호", "40,000,000원", "300,000원"],
        ],
        widths: [0.14, 0.18, 0.18, 0.26, 0.24],
      },
      { p: "위 임대조건은 청년 계층 기준이며, 계층별 임대조건은 4쪽을 참고하시기 바랍니다." },
    ],
    [
      { h: "■ 신청 자격" },
      { li: "청년: 공고일 현재 만 19세 이상 39세 이하인 미혼 무주택자" },
      { li: "신혼부부: 혼인 기간이 7년 이내인 무주택세대구성원" },
      {
        li: "소득: 세대의 월평균 소득이 전년도 도시근로자 가구원수별 월평균 소득의 100% 이하 (1인 가구는 120% 이하)",
      },
      { li: "공고일 현재 세대구성원 전원이 무주택이어야 합니다." },
      { gap: 1 },
      { p: "자산 기준 (표 1)" },
      {
        table: [
          ["구분", "기준"],
          ["총자산", "2억 5,100만 원 이하"],
          ["자동차", "4,542만 원 이하"],
        ],
        widths: [0.3, 0.7],
      },
      {
        p: "총자산은 세대구성원 전원이 보유한 부동산, 금융자산, 자동차 등을 합산한 금액에서 부채를 빼지 않고 산정합니다.",
      },
    ],
    [
      { h: "■ 계층별 임대조건 (참고)" },
      {
        p: "신혼부부 계층은 청년 계층보다 임대보증금과 월 임대료가 높게 정해지며, 주택형별 금액은 청약 화면에서 안내합니다.",
      },
    ],
    [
      { h: "■ 모집 일정" },
      { p: "인터넷 청약 접수는 2026. 10. 14.(수)부터 10. 31.(토)까지입니다." },
      {
        table: [
          ["구분", "일정"],
          ["공고", "2026. 10. 7.(수)"],
          ["청약 접수", "10. 14.(수) ~ 10. 31.(토)"],
          ["서류 제출 (대상자)", "11. 18.(수) ~ 11. 24.(화)"],
          ["당첨자 발표", "12. 18.(금)"],
          ["계약", "2027. 1. 13.(수) ~ 1. 15.(금)"],
        ],
        widths: [0.4, 0.6],
      },
      { gap: 1 },
      { h: "■ 입주자 선정" },
      { li: "1순위: 해당 지역(마포구)에 거주하거나 소득이 있는 업무에 종사하는 사람" },
      { li: "2순위: 서울특별시에 거주하거나 소득이 있는 업무에 종사하는 사람" },
      { li: "3순위: 그 밖의 지역에 거주하는 사람" },
      { li: "동일 순위 내 경쟁이 있으면 추첨으로 입주자를 선정합니다." },
    ],
    [
      { h: "■ 신청 방법" },
      { p: "LH 청약플러스 누리집 또는 모바일 앱으로 인터넷 신청합니다." },
      { h: "■ 제출 서류" },
      { li: "주민등록표등본 (서류 제출 대상자에 한함)" },
      { li: "금융정보 등 제공 동의서 (세대구성원 전원 서명)" },
    ],
    [
      { h: "■ 거주 기간" },
      { p: "청년 계층은 최대 6년, 자녀가 있는 가구는 최대 10년까지 거주할 수 있습니다." },
    ],
    [{ h: "■ 문의처" }, { li: "LH 콜센터 1600-1004 (청약 신청 관련 문의)" }],
  ],
};

const youthPurchase = {
  file: "notice-n4.pdf",
  title: "2026년 2차 청년 매입임대주택 입주자 모집 공고",
  sub: "공고일 2026. 10. 10. · 시연용 예시 문서",
  pages: [
    [
      { box: demoBox("무주택자들") },
      { h: "■ 공급 개요" },
      {
        p: "마포구 소재 청년 매입임대주택 8호를 주변 시세의 40~50% 수준으로 공급합니다. 호별 주소와 임대조건은 첨부한 주택 목록(엑셀)을 확인하세요.",
      },
    ],
    [
      { h: "■ 신청 자격" },
      { li: "공고일 현재 만 19세 이상 39세 이하인 미혼 청년이어야 합니다." },
      { li: "신청자 본인이 무주택자이어야 합니다." },
      { li: "소득 기준은 순위별로 다르게 적용합니다." },
      { gap: 1 },
      { h: "■ 입주 순위" },
      { li: "1순위: 생계·의료급여 수급자, 차상위계층, 한부모가족" },
      { li: "2순위: 본인과 부모의 월평균 소득 합계가 도시근로자 월평균 소득 100% 이하" },
      { li: "3순위: 본인의 월평균 소득이 도시근로자 월평균 소득 100% 이하" },
      { li: "같은 순위 안에서는 배점이 높은 순서로 입주자를 선정합니다." },
    ],
    [
      { h: "■ 모집 일정" },
      { p: "신청 접수는 2026. 10. 20.(화)부터 10. 24.(토)까지 받습니다." },
      { li: "주택 공개: 11월 중 (일정 별도 안내)" },
      { li: "당첨자 발표: 2026. 12. 5.(토)" },
      { li: "계약: 12월 중 (당첨자에게 개별 안내)" },
      { gap: 1 },
      { h: "■ 신청 방법" },
      { p: "LH 청약플러스 누리집에서 인터넷으로 신청합니다." },
    ],
    [
      { h: "■ 거주 기간" },
      { p: "임대차계약 기간은 2년이며, 재계약을 거쳐 최대 6년까지 거주할 수 있습니다." },
      { gap: 1 },
      { h: "■ 문의처" },
      { li: "LH 콜센터 1600-1004 (매입임대 신청 문의)" },
    ],
  ],
};

// ---- 그리기 ----

async function build(spec, fontBytes) {
  const pdf = await PDFDocument.create();
  pdf.registerFontkit(fontkit);
  pdf.setTitle(`${spec.title} (시연용 예시 문서)`);
  pdf.setSubject("무주택자들 시연용 예시 문서 · 실제 기관 공고문이 아님");
  pdf.setProducer("무주택자들 시연 문서 생성");
  pdf.setCreator("무주택자들");
  // 이미 쓴 글자만 남긴 글꼴이라 그대로 넣어요
  const font = await pdf.embedFont(fontBytes, { subset: false });
  const width = A4[0] - MARGIN * 2;
  const total = spec.pages.length;

  /** 글자 폭에 맞춰 줄을 나눠요 (빈칸 기준, 긴 낱말은 글자 단위) */
  const wrap = (text, size, max) => {
    const lines = [];
    let line = "";
    for (const word of text.split(" ")) {
      const next = line ? `${line} ${word}` : word;
      if (font.widthOfTextAtSize(next, size) <= max) {
        line = next;
        continue;
      }
      if (line) lines.push(line);
      line = "";
      for (const ch of word) {
        if (font.widthOfTextAtSize(line + ch, size) > max) {
          lines.push(line);
          line = "";
        }
        line += ch;
      }
    }
    if (line) lines.push(line);
    return lines;
  };

  spec.pages.forEach((blocks, i) => {
    const page = pdf.addPage(A4);
    let y = A4[1] - MARGIN;
    const text = (s, x, size, color = INK) => page.drawText(s, { x, y, size, font, color });

    // 머리: 모든 쪽에 시연용 표시
    page.drawRectangle({ x: 0, y: A4[1] - 30, width: A4[0], height: 30, color: TINT });
    page.drawText(DEMO_HEAD, { x: MARGIN, y: A4[1] - 19, size: 8.5, font, color: BRAND });
    y -= 6;

    if (i === 0) {
      for (const l of wrap(spec.title, 19, width)) {
        y -= 19;
        text(l, MARGIN, 19);
        y -= 8;
      }
      y -= 2;
      text(spec.sub, MARGIN, 11, SUB);
      y -= 18;
    }

    for (const b of blocks) {
      if (b.gap) {
        y -= BODY * b.gap;
      } else if (b.h) {
        y -= 14 + 12;
        text(b.h, MARGIN, 14, BRAND);
        y -= 6;
      } else if (b.box) {
        const lines = wrap(b.box, 11, width - 24);
        const h = lines.length * 11 * LEAD + 16;
        page.drawRectangle({
          x: MARGIN,
          y: y - h,
          width,
          height: h,
          color: TINT,
          borderColor: BRAND,
          borderWidth: 0.6,
        });
        y -= 8;
        for (const l of lines) {
          y -= 11 * LEAD;
          page.drawText(l, { x: MARGIN + 12, y: y + 3, size: 11, font, color: INK });
        }
        y -= 12;
      } else if (b.p || b.li) {
        const indent = b.li ? 12 : 0;
        const lines = wrap(b.p ?? b.li, BODY, width - indent);
        lines.forEach((l, k) => {
          y -= BODY * LEAD;
          if (b.li && k === 0) text("-", MARGIN + 2, BODY, SUB);
          text(l, MARGIN + indent, BODY);
        });
        y -= 3;
      } else if (b.table) {
        const rowH = BODY * 2.1;
        const xs = [];
        let x = MARGIN;
        for (const w of b.widths) {
          xs.push(x);
          x += w * width;
        }
        y -= 6;
        b.table.forEach((row, r) => {
          if (r === 0) {
            page.drawRectangle({ x: MARGIN, y: y - rowH, width, height: rowH, color: TINT });
          }
          page.drawLine({
            start: { x: MARGIN, y },
            end: { x: MARGIN + width, y },
            thickness: 0.6,
            color: LINE,
          });
          const base = y - rowH + BODY * 0.75;
          row.forEach((cell, c) => {
            if (cell) {
              page.drawText(cell, {
                x: xs[c] + 6,
                y: base,
                size: BODY - 0.5,
                font,
                color: r === 0 ? SUB : INK,
              });
            }
          });
          y -= rowH;
        });
        page.drawLine({
          start: { x: MARGIN, y },
          end: { x: MARGIN + width, y },
          thickness: 0.6,
          color: LINE,
        });
        y -= 6;
      }
      if (y < MARGIN + 30) throw new Error(`${spec.file} ${i + 1}쪽이 넘쳐요`);
    }

    page.drawText(`- ${i + 1} / ${total} -`, {
      x: A4[0] / 2 - 16,
      y: 28,
      size: 8.5,
      font,
      color: SUB,
    });
  });
  return pdf.save();
}

/** 문서들에 쓴 글자만 남긴 글꼴 (머리·쪽 번호 글자 포함) */
function subsetFont(specs) {
  const chars = new Set(`${DEMO_HEAD}- /0123456789`);
  const add = (t) => [...t].forEach((c) => chars.add(c));
  for (const spec of specs) {
    add(spec.title + spec.sub + demoBox("무주택자들"));
    for (const b of spec.pages.flat()) {
      add([b.h, b.p, b.li, b.box].filter(Boolean).join(""));
      for (const row of b.table ?? []) add(row.join(""));
    }
  }
  const dir = mkdtempSync(path.join(os.tmpdir(), "demo-pdf-"));
  try {
    const textFile = path.join(dir, "chars.txt");
    const out = path.join(dir, "font.ttf");
    writeFileSync(textFile, [...chars].join(""), "utf8");
    execFileSync(
      "python",
      [
        "-m",
        "fontTools.subset",
        FONT,
        `--text-file=${textFile}`,
        `--output-file=${out}`,
        "--no-hinting",
        "--layout-features=",
        "--name-IDs=*",
        "--name-legacy",
      ],
      { env: { ...process.env, PYTHONPATH: path.resolve(pyDir) }, stdio: "inherit" },
    );
    return readFileSync(out);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const specs = [parkville, happyHousing, youthPurchase];
const fontBytes = subsetFont(specs);
mkdirSync(OUT, { recursive: true });
for (const spec of specs) {
  const bytes = await build(spec, fontBytes);
  writeFileSync(path.join(OUT, spec.file), bytes);
  console.log(`${spec.file}: ${spec.pages.length}쪽 · ${(bytes.length / 1024).toFixed(1)}KB`);
}
