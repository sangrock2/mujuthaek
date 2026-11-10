import type { NoticeUnit } from "@/mocks/notice";

const price = "text-[14px] font-bold";

/** 집 하나의 보증금·월세. 가격 대상이 여럿이면 대상마다 한 줄 (금액은 중간에서 끊지 않아요) */
export function UnitPrices({ unit }: { unit: NoticeUnit }) {
  if (!unit.prices) {
    return (
      <span className="flex flex-wrap gap-x-[4px]">
        <span className={price}>보증금 {unit.deposit} ·</span>
        <span className={price}>{unit.rent}</span>
      </span>
    );
  }
  return (
    <span className="flex flex-col gap-[2px]">
      {unit.prices.map((p) => (
        <span key={p.target} className="flex flex-wrap items-baseline gap-x-[6px]">
          <span className="text-text-sub text-[13px] font-semibold">{p.target}</span>
          <span className={`${price} whitespace-nowrap`}>보증금 {p.deposit}</span>
          <span className={`${price} whitespace-nowrap`}>{p.rent}</span>
        </span>
      ))}
    </span>
  );
}
