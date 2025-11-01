"""
애플리케이션 설정 모듈

Pydantic Settings를 사용하여 환경 변수와 .env 파일에서
설정을 로드하고 검증합니다.

주요 기능:
- 환경 변수 기반 설정 관리
- 타입 검증 및 자동 변환
- .env 파일 지원
- 기본값 제공
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    애플리케이션 설정 클래스

    환경 변수 또는 .env 파일에서 설정을 로드합니다.
    Pydantic을 사용하여 타입 검증 및 자동 변환을 수행합니다.

    설정 우선순위:
        1. 환경 변수 (가장 높음)
        2. .env 파일
        3. 기본값 (가장 낮음)

    사용 예시:
        ```python
        from app.config import settings

        print(settings.NAVER_CLIENT_ID)
        print(settings.MONGODB_URL)
        ```
    """

    # ==================== Naver API 설정 ====================
    NAVER_CLIENT_ID: str
    """네이버 API 클라이언트 ID (필수)"""

    NAVER_CLIENT_SECRET: str
    """네이버 API 클라이언트 시크릿 (필수)"""

    NAVER_SHOPPING_API_URL: str = "https://openapi.naver.com/v1/search/shop.json"
    """네이버 쇼핑 검색 API 엔드포인트 URL"""

    # ==================== MongoDB 설정 ====================
    MONGODB_URL: str = "mongodb://localhost:27017"
    """
    MongoDB 연결 URL

    형식: mongodb://[username:password@]host[:port][/database]

    예시:
        - 로컬: mongodb://localhost:27017
        - 인증: mongodb://user:pass@host:27017/dbname
        - 레플리카셋: mongodb://host1:27017,host2:27017/?replicaSet=rs0
    """

    MONGODB_DB_NAME: str = "naver_shopping"
    """
    사용할 MongoDB 데이터베이스 이름

    컬렉션:
        - products: 상품 데이터
        - search_history: 검색 이력
    """

    # ==================== API 서버 설정 ====================
    API_HOST: str = "0.0.0.0"
    """
    API 서버 호스트 주소

    - 0.0.0.0: 모든 네트워크 인터페이스에서 접근 가능
    - 127.0.0.1: 로컬호스트만 접근 가능
    """

    API_PORT: int = 8000
    """API 서버 포트 번호"""

    API_RELOAD: bool = True
    """
    핫 리로드 활성화 여부

    개발 환경: True
    운영 환경: False (성능 최적화)
    """

    # ==================== 검색 설정 ====================
    DEFAULT_DISPLAY: int = 100
    """한 번에 조회할 기본 상품 수"""

    MAX_DISPLAY: int = 100
    """
    한 번에 조회 가능한 최대 상품 수

    네이버 API 제한: 최대 100개
    """

    class Config:
        """Pydantic 설정 클래스"""

        env_file = ".env"
        """환경 변수 파일 경로"""

        env_file_encoding = "utf-8"
        """환경 변수 파일 인코딩"""

        case_sensitive = True
        """
        환경 변수 대소문자 구분 여부

        True: NAVER_CLIENT_ID와 naver_client_id를 다르게 처리
        """

        extra = "ignore"
        """
        정의되지 않은 환경 변수 처리 방식

        - ignore: 무시
        - forbid: 예외 발생
        - allow: 허용
        """


# 싱글톤 설정 인스턴스
# 애플리케이션 전체에서 이 인스턴스를 사용하여 설정에 접근합니다.
settings = Settings()
