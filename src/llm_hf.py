import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

# 환경 변수 로드
load_dotenv()

# Hugging Face Inference API 설정
HF_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_MODEL = "moonshotai/Kimi-K2-Instruct-0905"


def _get_client() -> OpenAI:
    """Hugging Face API 토큰을 사용하여 OpenAI 클라이언트 초기화"""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        # .env 파일에 HF_TOKEN이 누락된 경우 에러 발생
        raise RuntimeError("HF_TOKEN이 설정되어 있지 않습니다. (.env 확인)")
    return OpenAI(base_url=HF_BASE_URL, api_key=hf_token)


def generate_commentary(text: str, model: Optional[str] = None) -> str:
    """
    광고 지표 변동 텍스트를 분석하여 AI 코멘트 생성
    분석 내용: 이상 징후 요약, 원인 가설, 실행 조치 제안
    """
    client = _get_client()
    model = model or os.getenv("HF_MODEL") or DEFAULT_MODEL # 인자 -> 환경변수 -> 코드 기본값 순으로 모델 결정

    # AI 페르소나 및 분석 원칙 설정
    system = (
        "너는 전문적인 퍼포먼스 마케팅 및 애드테크 분석가다. "
        "주어진 광고 지표의 수치 변화를 객관적으로 분석하여, "
        "이상 징후를 명확히 짚어내고 데이터에 근거한 실행 가능한 전략을 제안한다. "
        "모든 분석은 과장 없이 숫자에 기반해야 한다."
    )

    # 분석 대상 데이터 및 요구사항 정의
    user = f"""
아래는 광고 성과 데이터의 '전일 대비 변화 요약'이다.

{text}

위 데이터를 바탕으로 다음 요구사항에 맞춰 분석 리포트를 작성해라:
1) 이상 징후 TOP 1 (한 줄 요약)
2) 발생 원인에 대한 가설 2가지 (간결하게)
3) 실행해 볼 조치 3가지 제안 (키워드, CPC, 소재, 디바이스, 예산 관점 활용)

요구사항:
- 출력 형식 : 한국어, 불릿 포인트 사용
- **중요** : 슬랙(Slack) 전송용이므로, 강조하고 싶은 단어는 양옆에 별표 하나만 붙여라 (예: *강조*). 별표 두 개(**)는 절대 사용하지 마라
- 답변은 핵심 위주로 짧고 명확하게 작성
"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3, # 답변의 일관성을 위해 낮은 창의성 유지
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # API 오류 발생 시 전체 프로세스가 중단되지 않도록 폴백 메시지 반환
        return f"(AI 코멘트 생성 실패: {type(e).__name__}) 오늘은 지표 요약만 전송합니다."
