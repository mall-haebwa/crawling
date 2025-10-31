import re
import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.models import Product

logger = logging.getLogger(__name__)


class NaverShoppingAPI:
    """
    네이버 쇼핑 검색 API 클라이언트
    """

    def __init__(self):
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET
        self.api_url = settings.NAVER_SHOPPING_API_URL
        self.headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def search_products(
        self,
        query: str,
        display: int = 100,
        start: int = 1,
        sort: str = "sim",
        filter_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        네이버 쇼핑 API로 상품 검색

        Args:
            query: 검색 키워드
            display: 한 번에 표시할 검색 결과 개수 (1~100, 기본값 100)
            start: 검색 시작 위치 (1~1000, 기본값 1)
            sort: 정렬 옵션 (sim: 정확도순, date: 날짜순, asc: 가격오름차순, dsc: 가격내림차순)
            filter_options: 추가 필터 옵션

        Returns:
            검색 결과 딕셔너리
        """
        params = {
            "query": query,
            "display": min(display, settings.MAX_DISPLAY),
            "start": start,
            "sort": sort,
        }

        if filter_options:
            params.update(filter_options)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.api_url,
                    headers=self.headers,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error occurred: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error occurred: {str(e)}")
                raise

    async def search_and_collect(
        self,
        query: str,
        max_results: int = 100,
        sort: str = "sim",
        filter_options: Optional[Dict[str, Any]] = None
    ) -> List[Product]:
        """
        검색 결과를 Product 모델 리스트로 변환

        Args:
            query: 검색 키워드
            max_results: 수집할 최대 결과 수
            sort: 정렬 옵션
            filter_options: 필터 옵션 (filter, exclude 등)

        Returns:
            Product 객체 리스트
        """
        products = []
        display = min(max_results, settings.MAX_DISPLAY)

        # 여러 페이지 수집이 필요한 경우
        for start in range(1, max_results + 1, display):
            current_display = min(display, max_results - start + 1)

            result = await self.search_products(
                query=query,
                display=current_display,
                start=start,
                sort=sort,
                filter_options=filter_options
            )

            items = result.get("items", [])
            if not items:
                break

            for idx, item in enumerate(items):
                product = self._convert_to_product(item, query, start + idx)
                products.append(product)

            # 더 이상 결과가 없으면 중단
            if len(items) < current_display:
                break

        logger.info(f"Collected {len(products)} products for query: {query}")
        return products

    def _convert_to_product(self, item: Dict[str, Any], search_keyword: str, rank: int) -> Product:
        """
        네이버 API 응답을 Product 모델로 변환

        Args:
            item: 네이버 API 응답 아이템
            search_keyword: 검색 키워드
            rank: 검색 결과 순위

        Returns:
            Product 객체
        """
        # HTML 태그 제거
        title = self._strip_html_tags(item.get("title", ""))

        # 카테고리 정보 파싱
        categories = self._parse_category(item.get("category1", ""), item.get("category2", ""),
                                         item.get("category3", ""), item.get("category4", ""))

        # 태그 자동 추출 (제목, 브랜드, 제조사에서)
        tags = self._extract_tags(title, item.get("brand", ""), item.get("maker", ""))

        # 가격 정보
        lprice = int(item.get("lprice", 0))
        hprice = int(item.get("hprice", 0)) if item.get("hprice") else None

        # 가격 분석 계산
        price_discount_rate = None
        price_range = None
        if hprice and hprice > 0 and lprice > 0:
            price_discount_rate = round(((hprice - lprice) / hprice) * 100, 2)
            price_range = hprice - lprice

        # productType 분석
        product_type = int(item.get("productType", 0)) if item.get("productType") else None
        product_group, product_category_type, is_used, is_discontinued, is_presale = self._parse_product_type(product_type)

        return Product(
            product_id=item.get("productId", ""),
            title=title,
            link=item.get("link", ""),
            image=item.get("image"),
            lprice=lprice,
            hprice=hprice,
            mallName=item.get("mallName", ""),
            maker=item.get("maker"),
            brand=item.get("brand"),
            category1=categories.get("category1"),
            category2=categories.get("category2"),
            category3=categories.get("category3"),
            category4=categories.get("category4"),
            productId=item.get("productId"),
            productType=product_type,
            product_group=product_group,
            product_category_type=product_category_type,
            is_used=is_used,
            is_discontinued=is_discontinued,
            is_presale=is_presale,
            search_keyword=search_keyword,
            tags=tags,
            rank=rank,
            price_discount_rate=price_discount_rate,
            price_range=price_range,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    @staticmethod
    def _strip_html_tags(text: str) -> str:
        """HTML 태그 제거"""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)

    @staticmethod
    def _parse_category(cat1: str = "", cat2: str = "", cat3: str = "", cat4: str = "") -> Dict[str, Optional[str]]:
        """카테고리 정보 파싱"""
        return {
            "category1": cat1 if cat1 else None,
            "category2": cat2 if cat2 else None,
            "category3": cat3 if cat3 else None,
            "category4": cat4 if cat4 else None,
        }

    @staticmethod
    def _extract_tags(title: str, brand: str = "", maker: str = "") -> List[str]:
        """
        제목, 브랜드, 제조사에서 태그 자동 추출
        공백으로 구분된 단어들을 태그로 변환
        """
        tags = set()

        # 제목에서 추출
        if title:
            words = title.split()
            tags.update([word.strip() for word in words if len(word.strip()) > 1])

        # 브랜드 추가
        if brand:
            tags.add(brand.strip())

        # 제조사 추가
        if maker:
            tags.add(maker.strip())

        return list(tags)[:20]  # 최대 20개 태그로 제한

    @staticmethod
    def _parse_product_type(product_type: Optional[int]) -> tuple:
        """
        productType 값을 기반으로 상품 정보 파싱

        productType 매핑:
        1-3: 일반상품
        4-6: 중고상품
        7-9: 단종상품
        10-12: 판매예정상품

        각 범위 내:
        x1: 가격비교 상품
        x2: 가격비교 비매칭 일반상품
        x3: 가격비교 매칭 일반상품

        Returns:
            (상품군, 상품종류, 중고여부, 단종여부, 판매예정여부)
        """
        if not product_type or product_type < 1 or product_type > 12:
            return (None, None, False, False, False)

        # 상품군 판별
        if 1 <= product_type <= 3:
            product_group = "일반상품"
            is_used, is_discontinued, is_presale = False, False, False
        elif 4 <= product_type <= 6:
            product_group = "중고상품"
            is_used, is_discontinued, is_presale = True, False, False
        elif 7 <= product_type <= 9:
            product_group = "단종상품"
            is_used, is_discontinued, is_presale = False, True, False
        else:  # 10-12
            product_group = "판매예정상품"
            is_used, is_discontinued, is_presale = False, False, True

        # 상품 종류 판별
        remainder = product_type % 3
        if remainder == 1:
            product_category_type = "가격비교상품"
        elif remainder == 2:
            product_category_type = "가격비교비매칭"
        else:  # remainder == 0 (3, 6, 9, 12)
            product_category_type = "가격비교매칭"

        return (product_group, product_category_type, is_used, is_discontinued, is_presale)


# 싱글톤 인스턴스
naver_api = NaverShoppingAPI()
