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
from pydantic import field_validator, ValidationError
from typing import Optional
import logging

logger = logging.getLogger(__name__)


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

    # ==================== 데이터베이스 연결 풀 설정 ====================
    MONGODB_MIN_POOL_SIZE: int = 10
    """MongoDB 최소 연결 풀 크기 (기본값: 10)"""

    MONGODB_MAX_POOL_SIZE: int = 100
    """MongoDB 최대 연결 풀 크기 (기본값: 100)"""

    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    """MongoDB 서버 선택 타임아웃 (밀리초, 기본값: 5000ms)"""

    # ==================== HTTP 클라이언트 설정 ====================
    HTTP_MAX_CONNECTIONS: int = 100
    """HTTP 클라이언트 최대 연결 수 (기본값: 100)"""

    HTTP_MAX_KEEPALIVE_CONNECTIONS: int = 20
    """HTTP 클라이언트 최대 Keep-Alive 연결 수 (기본값: 20)"""

    HTTP_TIMEOUT: float = 30.0
    """HTTP 요청 타임아웃 (초, 기본값: 30.0)"""

    # ==================== 환경 구분 ====================
    ENVIRONMENT: str = "development"
    """환경 구분 (development, staging, production)"""

    # ==================== CORS 설정 ====================
    ALLOWED_ORIGINS: str = "*"
    """
    CORS에서 허용할 출처 목록 (쉼표로 구분)

    예시:
        - "*": 모든 출처 허용 (개발 환경에만 사용)
        - "http://localhost:3000,https://example.com": 특정 출처만 허용
    """

    @property
    def cors_origins_list(self) -> list:
        """CORS 허용 출처를 리스트로 반환"""
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @field_validator("API_RELOAD")
    @classmethod
    def validate_api_reload(cls, v: bool, info) -> bool:
        """
        운영 환경에서 API_RELOAD=True 경고
        """
        environment = info.data.get("ENVIRONMENT", "development")
        if environment == "production" and v is True:
            logger.warning(
                "⚠️  경고: 운영 환경에서 API_RELOAD=True는 권장되지 않습니다. "
                "성능 저하 및 메모리 누수가 발생할 수 있습니다."
            )
        return v

    @field_validator("MONGODB_URL")
    @classmethod
    def validate_mongodb_url(cls, v: str) -> str:
        """
        MongoDB URL 보안 검증
        """
        # localhost가 아닌 공개 IP/도메인 사용 시 인증 권장
        is_localhost = v.startswith("mongodb://localhost") or v.startswith("mongodb://127.0.0.1")

        if not is_localhost and "@" not in v:
            logger.warning(
                "⚠️  보안 경고: MongoDB URL에 인증 정보가 없습니다. "
                "공개 네트워크에서는 반드시 인증을 사용하세요."
            )
        return v

    @field_validator("API_HOST")
    @classmethod
    def validate_api_host(cls, v: str, info) -> str:
        """
        API 호스트 보안 검증
        """
        environment = info.data.get("ENVIRONMENT", "development")
        if environment == "production" and v == "0.0.0.0":
            logger.warning(
                "⚠️  보안 경고: API_HOST=0.0.0.0은 모든 인터페이스에서 접근 가능합니다. "
                "운영 환경에서는 특정 IP 또는 리버스 프록시 사용을 권장합니다."
            )
        return v

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
