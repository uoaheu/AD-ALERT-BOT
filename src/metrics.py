from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from io_csv import load_csv


def safe_div(n: float, d: float) -> float:
    """0으로 나누기 에러를 방지하는 안전한 나눗셈 함수"""
    return (n / d) if d != 0 else 0.0


def calc_roas(revenue: float, cost: float) -> float:
    # ROAS(%) = (매출 / 비용) * 100
    return safe_div(revenue, cost) * 100.0


@dataclass
class ProductDelta:
    """상품별 전일 대비 지표 변화를 저장하는 데이터 클래스"""
    product_name: str
    cost_today: float
    cost_prev: float
    revenue_today: float
    revenue_prev: float
    conv_today: float
    conv_prev: float
    roas_today: float
    roas_prev: float

    @property
    def cost_diff(self) -> float:
        return self.cost_today - self.cost_prev

    @property
    def rev_diff(self) -> float:
        return self.revenue_today - self.revenue_prev

    @property
    def roas_diff(self) -> float:
        # %p 변화
        return self.roas_today - self.roas_prev


def _agg_by_product(df: pd.DataFrame) -> pd.DataFrame:
    """상품명을 기준으로 지표를 합산하고 ROAS 재계산"""
    if df.empty:
        return pd.DataFrame(columns=["product_name", "cost", "revenue", "conversions", "roas"])

    g = (
        df.groupby("product_name", as_index=False)
        .agg(
            cost=("cost", "sum"),
            revenue=("revenue", "sum"),
            conversions=("conversions", "sum"),
        )
        .copy()
    )
    g["roas"] = g.apply(lambda r: calc_roas(float(r["revenue"]), float(r["cost"])), axis=1)
    return g


def _pick_prev_date(all_dates: list[Date], today_date: Date) -> Optional[Date]:
    """
    today_date보다 작은 날짜 중 가장 가까운 날짜를 반환
    (주말/공휴일로 결측이 있어도 안전)
    """
    prevs = [d for d in all_dates if d < today_date]
    return max(prevs) if prevs else None


def compute_latest_daily_deltas(history_csv: str | Path, today_csv: str | Path) -> tuple[str, Date, Date, list[ProductDelta]]:
    """
    today.csv의 최신 날짜(max_date) 1개만 대상으로 리포트 생성
    - today_date = max(today.date)
    - prev_date = history에서 today_date보다 작은 날짜 중 가장 가까운 날짜
    """
    hist = load_csv(history_csv)
    today = load_csv(today_csv)

    if today.empty:
        raise ValueError("today.csv가 비어있습니다.")
    if hist.empty:
        raise ValueError("history.csv가 비어있습니다. upsert 이후에 호출되어야 합니다.")

    today_date = max(today["date"])
    all_dates = sorted(hist["date"].unique().tolist())

    prev_date = _pick_prev_date(all_dates, today_date)
    if prev_date is None:
        raise ValueError(f"비교할 이전 날짜가 없습니다. today_date={today_date}")

    # 날짜별 필터
    df_today = hist[hist["date"] == today_date].copy()
    df_prev = hist[hist["date"] == prev_date].copy()

    t = _agg_by_product(df_today)
    p = _agg_by_product(df_prev)

    merged = t.merge(p, on="product_name", how="outer", suffixes=("_today", "_prev")).fillna(0.0)

    deltas: list[ProductDelta] = []
    for _, r in merged.iterrows():
        deltas.append(
            ProductDelta(
                product_name=str(r["product_name"]),
                cost_today=float(r["cost_today"]),
                cost_prev=float(r["cost_prev"]),
                revenue_today=float(r["revenue_today"]),
                revenue_prev=float(r["revenue_prev"]),
                conv_today=float(r["conversions_today"]),
                conv_prev=float(r["conversions_prev"]),
                roas_today=float(r["roas_today"]),
                roas_prev=float(r["roas_prev"]),
            )
        )

    # ROAS 변동폭이 큰 순서대로 정렬 (중요 지표 우선 노출)
    deltas.sort(key=lambda d: abs(d.roas_diff), reverse=True)
    title = f"광고 전일 대비 리포트 ({prev_date} → {today_date})"
    return title, today_date, prev_date, deltas


def format_daily_lines(deltas: list[ProductDelta], top_n: int = 10) -> tuple[str, str]:
    """
    슬랙 메시지용 리포트 텍스트 & LLM 분석용 데이터 생성
    """
    lines = []
    summary = []

    if not deltas:
        return "- 변화 데이터가 없습니다.", ""

    for d in deltas[:top_n]:
        cost_diff = int(round(d.cost_diff))
        rev_diff = int(round(d.rev_diff))
        roas_diff = d.roas_diff

        # 슬랙 가시성을 위해 상품명 볼드 처리
        lines.append(f"- *{d.product_name}*: 전날 대비 총비용 {cost_diff:+,}원, 전환매출액 {rev_diff:+,}원 → ROAS {roas_diff:+.1f}%p")
        summary.append(f"{d.product_name} | cost {cost_diff:+,} | revenue {rev_diff:+,} | roas {roas_diff:+.1f}%p")

    return "\n".join(lines), "\n".join(summary)


@dataclass
class WeeklyDelta:
    """주간 성과 비교 데이터를 담는 클래스"""
    week1_start: Date
    week1_end: Date
    week2_start: Date
    week2_end: Date
    # product별 비교 결과
    by_product: pd.DataFrame  # columns: product_name, cost_w1, revenue_w1, roas_w1, cost_w2, revenue_w2, roas_w2, roas_diff


def compute_weekly_deltas_for_monday(history_csv: str | Path, today_date: Date) -> Optional[WeeklyDelta]:
    """
    일요일 데이터 업로드 시(월요일 리포트용) 주간 성과 변화 계산
    - today_date가 '일요일'이면 그 주(월~일)가 끝난 상태 → 주간 비교 가능
      (월요일에 금토일 업로드하면 max_date가 일요일인 경우가 흔함)

    주간 비교는 '최근 2주' 비교(Week-1 vs Week-2)만 수행
    - Week-1 : (today_date - 6) ~ today_date
    - Week-2 : (today_date - 13) ~ (today_date - 7)
    """
    # 일요일(weekday=6)일 때만 주간 비교
    if today_date.weekday() != 6:
        return None

    hist = load_csv(history_csv)
    if hist.empty:
        return None

    w1_end = today_date
    w1_start = w1_end - timedelta(days=6)

    w2_end = w1_start - timedelta(days=1)
    w2_start = w2_end - timedelta(days=6)

    df_w1 = hist[(hist["date"] >= w1_start) & (hist["date"] <= w1_end)].copy()
    df_w2 = hist[(hist["date"] >= w2_start) & (hist["date"] <= w2_end)].copy()

    if df_w1.empty or df_w2.empty:
        return None

    a = _agg_by_product(df_w1).rename(columns={"cost": "cost_w1", "revenue": "revenue_w1", "roas": "roas_w1", "conversions": "conv_w1"})
    b = _agg_by_product(df_w2).rename(columns={"cost": "cost_w2", "revenue": "revenue_w2", "roas": "roas_w2", "conversions": "conv_w2"})

    m = a.merge(b, on="product_name", how="outer").fillna(0.0)
    m["roas_diff"] = m["roas_w1"] - m["roas_w2"]

    # 주간 ROAS 변동 큰 순
    m["abs_roas_diff"] = m["roas_diff"].abs()
    m = m.sort_values("abs_roas_diff", ascending=False).drop(columns=["abs_roas_diff"]).reset_index(drop=True)

    return WeeklyDelta(
        week1_start=w1_start,
        week1_end=w1_end,
        week2_start=w2_start,
        week2_end=w2_end,
        by_product=m,
    )


def format_weekly_lines(w: WeeklyDelta, top_n: int = 5) -> str:
    """
    주간 리포트를 슬랙 메시지 형식으로 변환
    """
    df = w.by_product.head(top_n)

    lines = [f"📊 주간 비교(최근 2주) ({w.week2_start}~{w.week2_end} → {w.week1_start}~{w.week1_end})"]
    if df.empty:
        lines.append("- 주간 비교 데이터가 없습니다.")
        return "\n".join(lines)

    for _, r in df.iterrows():
        product = r["product_name"]
        cost_diff = int(round(float(r["cost_w1"]) - float(r["cost_w2"])))
        rev_diff = int(round(float(r["revenue_w1"]) - float(r["revenue_w2"])))
        roas_diff = float(r["roas_diff"])

        lines.append(
            f"- {product} : 주간 비용 {cost_diff:+,}원, 주간 매출 {rev_diff:+,}원 → 주간 ROAS {roas_diff:+.1f}%p"
        )

    return "\n".join(lines)
