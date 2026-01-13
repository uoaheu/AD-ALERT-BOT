from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError

# 설정 : 필수 컬럼 및 데이터 타입별 분류
REQUIRED_COLUMNS = [
    "date", "product_name", "campaign_name", "device", "keyword",
    "impressions", "clicks", "avg_cpc", "cost", "conversions", "revenue",
]
# 수치형 데이터 컬럼 (NaN 발생 시 0으로 치환될 대상)
NUMERIC_COLUMNS = ["impressions", "clicks", "avg_cpc", "cost", "conversions", "revenue"]
# 문자열 데이터 컬럼 (공백 제거 대상)
STRING_COLUMNS = ["product_name", "campaign_name", "device", "keyword"]


def load_csv(path: str | Path) -> pd.DataFrame:
    """
    CSV를 읽어 광고 지표 분석에 적합한 형태로 정제
    - date : datetime.date 타입으로 변환
    - 숫자 컬럼 : float (NaN -> 0)
    - 문자열 컬럼 : strip

    추가 처리
    - 파일은 존재하지만 0바이트(완전 빈 파일)인 경우 pandas가 EmptyDataError를 내므로,
      REQUIRED_COLUMNS만 가진 빈 DataFrame으로 처리
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV 파일이 없습니다 : {p}")

    # 0바이트 파일(내용 없음) 방어
    try:
        df = pd.read_csv(p)
    except EmptyDataError:
        # 파일은 있지만 완전히 비어있는 경우
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    # 스키마 체크 - 필수 컬럼 존재 여부 검증
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV에 필요한 컬럼이 없습니다 : {missing}")

    if df.empty:
        return df

    # 날짜 데이터 정제
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df[df["date"].notna()].copy()  # 날짜 파싱 실패 행 제거

    # 수치 데이터 정제 (문자열 섞임 방지 및 결측치 처리)
    for c in NUMERIC_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # 문자열 데이터 정제
    for c in STRING_COLUMNS:
        df[c] = df[c].astype(str).str.strip()

    return df


def get_max_date(path: str | Path):
    """
    CSV 내 데이터 중 가장 최신 날짜(max date) 반환 (없으면 None)
    """
    p = Path(path)
    if not p.exists():
        return None

    df = load_csv(p)
    if df.empty:
        return None

    return max(df["date"])


def get_unique_dates(path: str | Path) -> list:
    """
    CSV 안에 들어있는 date 목록(중복 제거, 정렬)을 반환
    """
    df = load_csv(path)
    if df.empty:
        return []
    return sorted(df["date"].unique().tolist())


def upsert_history(history_path: str | Path, today_path: str | Path) -> tuple[Path, list]:
    """
    today.csv(여러 날짜가 섞여 있어도 OK)를 history.csv에 날짜 단위로 upsert(덮어쓰기/추가)하고,
    결과를 date 기준으로 정렬하여 저장

    동작
    1) today에 포함된 date 목록 추출
    2) history에서 해당 date 행 제거
    3) today를 append
    4) date/product/campaign/device/keyword 기준 정렬 후 저장

    return: (history_path, today_dates_sorted)
    """
    history_path = Path(history_path)
    today_path = Path(today_path)

    today_df = load_csv(today_path)
    if today_df.empty:
        raise ValueError("업데이트할 당일 데이터(today.csv)가 비어있습니다.")

    today_dates = sorted(today_df["date"].unique().tolist())

    if history_path.exists():
        hist_df = load_csv(history_path)
        # today에 포함된 날짜는 기존 history에서 제거 후 재삽입(=업데이트)
        hist_df = hist_df[~hist_df["date"].isin(today_dates)].copy()
        merged = pd.concat([hist_df, today_df], ignore_index=True)
    else:
        merged = today_df.copy()

    # 지표 분석 가독성을 위한 정렬 기준 적용
    merged = merged.sort_values(
        by=["date", "product_name", "campaign_name", "device", "keyword"]
    ).reset_index(drop=True)

    merged.to_csv(history_path, index=False)
    return history_path, today_dates
