// 원문 PDF 글자 층에서 근거 인용 문장을 찾아 강조할 자리를 정해요 (pdf.js getTextContent의 글자 조각 기준)

/** 글자 조각: pdf.js TextItem 중 쓰는 칸 */
export type PdfTextPiece = { str: string; transform: number[]; width: number };

/** 화면(뷰포트) 좌표의 강조 상자 (px) */
export type QuoteBox = { left: number; top: number; width: number; height: number };

/** 이보다 짧은 인용은 같은 글이 여기저기 있어 강조하지 않아요 */
const MIN_CHARS = 4;

/**
 * 비교용 글자: 호환 문자를 펴고(NFKC) 빈칸과 표 칸 구분자(|)를 빼요. 추출 원문의 표 행은 「| a | b |」, PDF 글자 층은 칸마다 조각이라
 * 이렇게 맞춰야 같은 글이 돼요
 */
export function squash(text: string) {
  return text.normalize("NFKC").replace(/[\s|]/g, "");
}

/**
 * 인용 문장의 강조 상자들. 그 쪽 글자에서 인용이 꼭 한 번 나올 때만 돌려줘요. 없거나 두 번 이상 나오거나(어느 쪽인지 모름), 너무 짧거나, 기울거나
 * 세로로 쓴 글자에 걸치면(자리를 확실히 못 정함) null이라 화면은 강조 없이 그 쪽만 열어요 — 틀린 곳을 가리키지 않게.
 *
 * @param toViewport 글자 조각의 transform을 화면 좌표로 바꾸는 함수 (pdf.js Util.transform(viewport.transform, ·))
 * @param scale 뷰포트 배율 (조각 너비 × scale = 화면 너비)
 */
export function quoteBoxes(
  pieces: PdfTextPiece[],
  quote: string,
  toViewport: (transform: number[]) => number[],
  scale: number,
): QuoteBox[] | null {
  const needle = squash(quote);
  if (needle.length < MIN_CHARS) return null;
  let joined = "";
  const owner: number[] = [];
  const offset: number[] = [];
  pieces.forEach((piece, i) => {
    const text = squash(piece.str);
    for (let k = 0; k < text.length; k++) {
      owner.push(i);
      offset.push(k);
    }
    joined += text;
  });
  const at = joined.indexOf(needle);
  if (at < 0 || joined.indexOf(needle, at + 1) >= 0) return null;

  // 조각마다 인용이 걸친 글자 범위 [처음, 끝)
  const spans = new Map<number, [number, number]>();
  for (let c = at; c < at + needle.length; c++) {
    const span = spans.get(owner[c]);
    spans.set(owner[c], span ? [span[0], offset[c] + 1] : [offset[c], offset[c] + 1]);
  }
  const boxes: QuoteBox[] = [];
  for (const [i, [start, end]] of spans) {
    const piece = pieces[i];
    const tx = toViewport(piece.transform);
    if (Math.abs(tx[1]) > 0.01 || Math.abs(tx[2]) > 0.01) return null;
    const height = Math.abs(tx[3]);
    const width = piece.width * scale;
    const length = squash(piece.str).length || 1;
    if (!(height > 0) || !(width > 0)) continue;
    boxes.push({
      left: tx[4] + (width * start) / length,
      top: tx[5] - height,
      width: (width * (end - start)) / length,
      height: height * 1.2,
    });
  }
  return boxes.length ? boxes : null;
}
