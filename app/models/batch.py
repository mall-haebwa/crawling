"""
일괄 수집 작업 모델

CSV 업로드를 통한 키워드 일괄 수집 기능의 데이터 모델
"""

from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
import uuid


class BatchCollection(Document):
    """
    CSV 업로드로 생성된 일괄 수집 작업

    하나의 CSV 파일 업로드가 하나의 BatchCollection을 생성
    """

    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """배치 고유 ID"""

    csv_filename: str
    """업로드된 CSV 파일명"""

    total_keywords: int
    """전체 키워드 수"""

    completed_keywords: int = 0
    """완료된 키워드 수"""

    failed_keywords: int = 0
    """실패한 키워드 수"""

    skipped_keywords: int = 0
    """중복으로 건너뛴 키워드 수"""

    status: str = "pending"
    """
    작업 상태
    - pending: 대기 중
    - running: 실행 중
    - completed: 완료
    - failed: 실패
    """

    created_at: datetime = Field(default_factory=datetime.utcnow)
    """생성 시간"""

    started_at: Optional[datetime] = None
    """시작 시간"""

    completed_at: Optional[datetime] = None
    """완료 시간"""

    current_keyword_index: int = 0
    """현재 처리 중인 키워드 인덱스 (0부터 시작)"""

    class Settings:
        name = "batch_collections"
        indexes = [
            "batch_id",
            "status",
            "created_at",
        ]


class BatchKeyword(Document):
    """
    배치 수집 작업의 개별 키워드

    BatchCollection에 속한 각 키워드의 수집 상태 추적
    """

    batch_id: str
    """부모 BatchCollection의 ID"""

    keyword: str
    """검색 키워드"""

    order: int
    """CSV 내 순서 (0부터 시작)"""

    status: str = "pending"
    """
    키워드 수집 상태
    - pending: 대기 중
    - running: 실행 중
    - completed: 완료
    - failed: 실패
    - skipped: 중복으로 건너뜀
    """

    # 수집 결과
    total_collected: int = 0
    """수집된 총 상품 수"""

    new_products: int = 0
    """신규 저장된 상품 수"""

    updated_products: int = 0
    """업데이트된 상품 수"""

    # 중복 체크
    previously_collected: bool = False
    """이전에 수집한 적 있는지 여부"""

    # 실행 정보
    started_at: Optional[datetime] = None
    """수집 시작 시간"""

    completed_at: Optional[datetime] = None
    """수집 완료 시간"""

    error_message: Optional[str] = None
    """에러 메시지 (실패 시)"""

    class Settings:
        name = "batch_keywords"
        indexes = [
            "batch_id",
            "status",
            "order",
            [("batch_id", 1), ("order", 1)],  # 복합 인덱스
        ]
