"""
MongoDB 데이터베이스 연결 관리 모듈

이 모듈은 MongoDB와의 비동기 연결을 관리합니다.
주요 기능:
- Motor (비동기 MongoDB 드라이버) 연결 관리
- Beanie ODM 초기화
- 연결 풀 설정 및 최적화
- 헬스체크 및 연결 상태 모니터링
"""

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie

from app.config import settings
from app.models import Product, ProductSearchResponse
from app.models.batch import BatchCollection, BatchKeyword

logger = logging.getLogger(__name__)


class Database:
    """
    MongoDB 데이터베이스 연결 관리 클래스

    클래스 변수로 싱글톤 패턴을 구현하여
    애플리케이션 전체에서 하나의 DB 연결을 공유합니다.

    Attributes:
        client (AsyncIOMotorClient): Motor 비동기 클라이언트
        database (AsyncIOMotorDatabase): MongoDB 데이터베이스 인스턴스
    """

    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_db(cls) -> None:
        """
        MongoDB 데이터베이스 연결 초기화

        애플리케이션 시작 시 한 번 호출되며,
        Motor 클라이언트를 생성하고 Beanie ODM을 초기화합니다.

        Raises:
            Exception: 연결 실패 시 예외 발생

        Note:
            - serverSelectionTimeoutMS: 서버 선택 타임아웃 (기본 30초)
            - maxPoolSize: 최대 연결 풀 크기 (기본 100)
            - minPoolSize: 최소 연결 풀 크기 (기본 10)
            - Beanie: MongoDB ODM으로 Pydantic 모델 사용
        """
        try:
            logger.info(f"MongoDB 연결 시도: {settings.MONGODB_URL}")

            # Motor 비동기 클라이언트 생성
            # 연결 풀 설정으로 성능 최적화 (환경 변수로 제어)
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                retryWrites=True,  # 쓰기 재시도 활성화 (안정성 향상)
                retryReads=True,   # 읽기 재시도 활성화 (안정성 향상)
                w="majority",      # 쓰기 승인 수준 (과반수 확인)
            )

            # 데이터베이스 선택
            cls.database = cls.client[settings.MONGODB_DB_NAME]

            # 연결 테스트 (ping)
            await cls.database.command("ping")
            logger.info("MongoDB 연결 테스트 성공")

            # Beanie ODM 초기화
            # Product, ProductSearchResponse, Batch 모델을 MongoDB 컬렉션과 매핑
            await init_beanie(
                database=cls.database,
                document_models=[Product, ProductSearchResponse, BatchCollection, BatchKeyword]
            )

            logger.info(f"MongoDB 연결 성공: {settings.MONGODB_DB_NAME}")
            logger.info("Beanie ODM 초기화 완료")

        except Exception as e:
            logger.error(f"MongoDB 연결 실패: {str(e)}", exc_info=True)
            # 연결 실패 시 클라이언트 정리
            if cls.client:
                cls.client.close()
                cls.client = None
            raise

    @classmethod
    async def close_db(cls) -> None:
        """
        MongoDB 데이터베이스 연결 종료

        애플리케이션 종료 시 호출되어 모든 연결을 정리합니다.

        Note:
            - 열려있는 모든 커넥션을 닫습니다
            - 리소스 누수 방지
        """
        if cls.client:
            cls.client.close()
            logger.info("MongoDB 연결 종료")
            cls.client = None
            cls.database = None

    @classmethod
    async def health_check(cls) -> bool:
        """
        데이터베이스 연결 상태 확인

        Returns:
            bool: 연결 상태 (True: 정상, False: 비정상)

        Note:
            헬스체크 엔드포인트에서 사용됩니다.
        """
        try:
            if cls.database is None:
                return False

            # ping 명령으로 연결 확인
            await cls.database.command("ping")
            return True
        except Exception as e:
            logger.error(f"DB 헬스체크 실패: {str(e)}")
            return False


# 데이터베이스 싱글톤 인스턴스
# 애플리케이션 전체에서 이 인스턴스를 사용하여 DB에 접근합니다.
db = Database()
