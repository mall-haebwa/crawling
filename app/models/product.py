"""
상품 데이터 모델 정의

Beanie ODM을 사용한 MongoDB 문서 모델입니다.
네이버 쇼핑 API 응답 데이터를 저장하고 관리합니다.

주요 기능:
- Pydantic 기반 데이터 검증
- MongoDB 인덱스 자동 생성
- 타입 안정성 보장
- 자동 타임스탬프 관리
"""

from datetime import datetime
from typing import Optional, List
from beanie import Document
from pydantic import Field, HttpUrl


class Product(Document):
    """
    네이버 쇼핑 상품 정보 모델

    네이버 쇼핑 검색 API의 응답 데이터를 확장하여
    검색, 분석, 통계에 필요한 추가 필드를 포함합니다.

    주요 특징:
    - 기본 상품 정보 (제목, 가격, 이미지 등)
    - 카테고리 정보 (최대 4단계)
    - 상품 타입 분석 (중고/단종/판매예정)
    - 가격 분석 (할인율, 가격 범위)
    - 자동 태그 추출
    - 검색 이력 추적

    MongoDB 컬렉션: products
    """

    # ==================== 기본 식별 정보 ====================
    product_id: str = Field(..., description="상품 고유 ID (네이버 상품 번호)")
    """
    네이버 쇼핑 상품의 고유 식별자
    중복 확인 및 업데이트 시 사용
    """

    title: str = Field(..., description="상품명")
    """
    상품 제목 (HTML 태그 제거됨)
    검색 키워드 강조를 위한 <b> 태그는 제거 후 저장
    """

    link: HttpUrl = Field(..., description="상품 상세 페이지 URL")
    """네이버 쇼핑 상품 상세 페이지 링크"""

    image: Optional[HttpUrl] = Field(None, description="상품 이미지 URL")
    """
    상품 대표 이미지 URL
    썸네일 이미지로 사용 가능
    """

    # ==================== 가격 정보 ====================
    lprice: int = Field(..., description="최저가 (원)")
    """상품의 최저 판매가격 (원 단위)"""

    hprice: Optional[int] = Field(None, description="최고가 (원)")
    """
    상품의 최고 판매가격 (원 단위)
    가격비교 매칭 상품의 경우 제공됨
    """

    # ==================== 판매자 정보 ====================
    mallName: str = Field(..., description="쇼핑몰 이름")
    """
    판매하는 쇼핑몰 이름
    예: 네이버, 11번가, G마켓 등
    """

    maker: Optional[str] = Field(None, description="제조사")
    """상품 제조사"""

    brand: Optional[str] = Field(None, description="브랜드")
    """상품 브랜드명"""

    # ==================== 카테고리 정보 ====================
    category1: Optional[str] = Field(None, description="카테고리 1단계 (대분류)")
    """대분류 카테고리 (예: 디지털/가전)"""

    category2: Optional[str] = Field(None, description="카테고리 2단계 (중분류)")
    """중분류 카테고리 (예: 음향가전)"""

    category3: Optional[str] = Field(None, description="카테고리 3단계 (소분류)")
    """소분류 카테고리 (예: 이어폰/헤드폰)"""

    category4: Optional[str] = Field(None, description="카테고리 4단계 (세분류)")
    """세분류 카테고리 (예: 블루투스이어폰)"""

    # 상품 유형 및 상태
    # 참고: productId는 product_id와 동일 (네이버 API 응답 구조 유지)
    productType: Optional[int] = Field(None, description="상품 타입 (1~12, 상품군과 상품 종류 조합)")

    # 상품 타입 상세 정보 (productType 기반 자동 계산)
    product_group: Optional[str] = Field(None, description="상품군 (일반/중고/단종/판매예정)")
    product_category_type: Optional[str] = Field(None, description="상품 종류 (가격비교/비매칭/매칭)")
    is_used: bool = Field(default=False, description="중고 상품 여부")
    is_discontinued: bool = Field(default=False, description="단종 상품 여부")
    is_presale: bool = Field(default=False, description="판매예정 상품 여부")

    # 검색 및 분석용 추가 필드
    search_keyword: str = Field(..., description="검색에 사용된 키워드")
    tags: List[str] = Field(default_factory=list, description="상품 태그 (자동 추출)")

    # 메타데이터
    created_at: datetime = Field(default_factory=datetime.utcnow, description="데이터 수집 시각")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="데이터 갱신 시각")
    last_build_date: Optional[datetime] = Field(None, description="검색 결과 생성 시각 (API 응답)")

    # 통계 정보
    rank: Optional[int] = Field(None, description="검색 결과 내 순위")

    # 가격 분석
    price_discount_rate: Optional[float] = Field(None, description="할인율 (hprice 대비 lprice, %)")
    price_range: Optional[int] = Field(None, description="가격 범위 (hprice - lprice)")

    class Settings:
        name = "products"
        indexes = [
            "product_id",
            "title",
            "search_keyword",
            "mallName",
            "brand",
            "category1",
            "created_at",
            [("title", "text"), ("brand", "text"), ("maker", "text")],  # 텍스트 검색 인덱스
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "12345678",
                "title": "삼성전자 갤럭시 버즈2 프로 SM-R510",
                "link": "https://search.shopping.naver.com/gate.nhn?id=12345678",
                "image": "https://shopping-phinf.pstatic.net/main_1234567/12345678.jpg",
                "lprice": 189000,
                "hprice": 229000,
                "mallName": "네이버",
                "maker": "삼성전자",
                "brand": "삼성",
                "category1": "디지털/가전",
                "category2": "음향가전",
                "category3": "이어폰/헤드폰",
                "category4": "블루투스이어폰",
                "search_keyword": "갤럭시 버즈",
                "tags": ["무선", "블루투스", "노이즈캔슬링"],
                "rank": 1
            }
        }


class ProductSearchResponse(Document):
    """
    검색 결과 메타데이터
    """
    search_keyword: str = Field(..., description="검색 키워드")
    total_count: int = Field(..., description="전체 검색 결과 수")
    display: int = Field(..., description="한 번에 표시되는 결과 수")
    start: int = Field(..., description="검색 시작 위치")
    sort: str = Field(default="sim", description="정렬 옵션")
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="수집 시각")

    class Settings:
        name = "search_history"
        indexes = [
            "search_keyword",
            "collected_at",
            [("search_keyword", 1), ("collected_at", -1)],  # 복합 인덱스
        ]
