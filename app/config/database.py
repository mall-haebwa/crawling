import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie

from app.config import settings
from app.models import Product, ProductSearchResponse

logger = logging.getLogger(__name__)


class Database:
    """MongoDB 데이터베이스 연결 관리"""

    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_db(cls) -> None:
        """데이터베이스 연결 초기화"""
        try:
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
            cls.database = cls.client[settings.MONGODB_DB_NAME]

            # Beanie 초기화
            await init_beanie(
                database=cls.database,
                document_models=[Product, ProductSearchResponse]
            )

            logger.info(f"Connected to MongoDB: {settings.MONGODB_DB_NAME}")

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise

    @classmethod
    async def close_db(cls) -> None:
        """데이터베이스 연결 종료"""
        if cls.client:
            cls.client.close()
            logger.info("Disconnected from MongoDB")


# 데이터베이스 인스턴스
db = Database()
