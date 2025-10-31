from datetime import datetime
from typing import Optional, List
from beanie import Document
from pydantic import Field, HttpUrl


class Product(Document):
    """
    네이버 쇼핑 상품 정보 모델
    자연어 검색 및 상세 분석을 위한 확장 필드 포함
    """

    # 기본 식별 정보
    product_id: str = Field(..., description="상품 고유 ID")
    title: str = Field(..., description="상품명")
    link: HttpUrl = Field(..., description="상품 상세 페이지 URL")
    image: Optional[HttpUrl] = Field(None, description="상품 이미지 URL")

    # 가격 정보
    lprice: int = Field(..., description="최저가")
    hprice: Optional[int] = Field(None, description="최고가")

    # 판매자 정보
    mallName: str = Field(..., description="쇼핑몰 이름")
    maker: Optional[str] = Field(None, description="제조사")
    brand: Optional[str] = Field(None, description="브랜드")

    # 카테고리 정보
    category1: Optional[str] = Field(None, description="카테고리 1단계")
    category2: Optional[str] = Field(None, description="카테고리 2단계")
    category3: Optional[str] = Field(None, description="카테고리 3단계")
    category4: Optional[str] = Field(None, description="카테고리 4단계")

    # 상품 유형 및 상태
    productId: Optional[str] = Field(None, description="네이버 상품 번호")
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
