import os
import requests


def send_slack(text: str) -> None:
    """
    설정된 슬랙 웹훅 URL로 메시지 전송
    """
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        # 환경변수가 없을 경우 에러를 발생시켜 알림 누락 방지
        raise RuntimeError("SLACK_WEBHOOK_URL이 설정되지 않았습니다. .env 파일을 확인해주세요.")

    response = requests.post(
        url,
        json={"text": text},
        timeout=10,
    )
    response.raise_for_status()
