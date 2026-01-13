from __future__ import annotations

import argparse
from datetime import date as Date
from pathlib import Path

from io_csv import get_max_date, upsert_history
from llm_hf import generate_commentary
from metrics import (
    compute_latest_daily_deltas,
    compute_weekly_deltas_for_monday,
    format_daily_lines,
    format_weekly_lines,
)
from slack import send_slack

# 경로 설정
DATA_DIR = Path("data")
HISTORY_CSV = DATA_DIR / "history.csv"
TODAY_CSV = DATA_DIR / "today.csv"


def _notify_missing(today_max, history_max):
    """데이터 업데이트가 누락되었을 때 슬랙 알림 전송"""
    if today_max is None:
        send_slack("⚠️ today.csv가 없거나 비어 있습니다. 오늘 데이터를 업로드해주세요.")
        return

    # today.csv는 있는데 history 기준으로 새 데이터가 아니면 (업로드 안 됐거나, 아직 갱신 전)
    send_slack(
        "⚠️ 아직 오늘 데이터가 업데이트되지 않았습니다.\n"
        f"- today.csv 최신 날짜 : {today_max}\n"
        f"- history.csv 최신 날짜 : {history_max if history_max else '기록 없음'}\n"
        "데이터 업로드 후 다시 실행하면 분석이 시작됩니다."
    )


def main():
    # 실행 옵션 설정
    parser = argparse.ArgumentParser(description="광고 성과 분석 및 AI 코멘트 자동화 봇")
    parser.add_argument(
        "--notify-missing",
        action="store_true",
        help="데이터 미업로드 시 Slack 알림을 보냅니다(12시 정기 실행용).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="새 데이터가 아니어도 강제로 분석/전송합니다(재업로드/수정 검증용).",
    )
    args = parser.parse_args()

    # 데이터 폴더가 없으면 생성
    DATA_DIR.mkdir(exist_ok=True)

    # 1. 최신 날짜 체크를 통한 업데이트 감지
    today_max = get_max_date(TODAY_CSV)
    history_max = get_max_date(HISTORY_CSV)

    # today.csv 자체가 없거나 비었으면
    if today_max is None:
        if args.notify_missing:
            _notify_missing(today_max, history_max)
        return

    # 신규 데이터 유무 판단 : today_max가 history_max보다 큰지
    is_new_data = (history_max is None) or (today_max > history_max)

    # 실행 조건 분기
    if (not is_new_data) and (not args.force):
        # 12시에는 "미업로드" 알림, 평소엔 조용히 종료
        if args.notify_missing:
            _notify_missing(today_max, history_max)
        return

    # 2. 데이터 병합 (Upsert)
    upsert_history(HISTORY_CSV, TODAY_CSV)

    # 3. 전일 대비 변동성 리포트 생성
    title, today_date, prev_date, deltas = compute_latest_daily_deltas(HISTORY_CSV, TODAY_CSV)
    daily_lines, llm_input = format_daily_lines(deltas, top_n=10)

    # 4. 주간 분석 리포트 생성 (대상 날짜가 월요일 리포트 시점일 경우)
    weekly_block = ""
    w = compute_weekly_deltas_for_monday(HISTORY_CSV, today_date)
    if w is not None:
        weekly_block = "\n\n" + format_weekly_lines(w, top_n=5)

    # 5. AI 컨설턴트 코멘트 생성 (프롬프트 전달)
    ai_comment = generate_commentary(llm_input) if llm_input.strip() else "(AI 분석을 위한 충분한 지표 데이터가 부족합니다.)"

    # 6. 최종 리포트 구성 및 Slack 전송
    text = (
        f"📌 {title}\n"
        f"{daily_lines}"
        f"{weekly_block}\n\n"
        f"🤖 AI 코멘트\n{ai_comment}"
    )

    send_slack(text)


if __name__ == "__main__":
    main()
