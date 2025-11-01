"""
네이버 쇼핑 API 서비스 모듈

이 모듈은 네이버 쇼핑 검색 API와의 통신을 담당합니다.
주요 기능:
- API 호출 및 재시도 로직
- 응답 데이터를 내부 Product 모델로 변환
- HTML 태그 제거 및 데이터 정제
- 상품 타입 분석 및 카테고리 파싱
"""

import re
import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.models import Product

logger = logging.getLogger(__name__)


class NaverShoppingAPI:
    """
    네이버 쇼핑 검색 API 클라이언트

    재사용 가능한 HTTP 클라이언트를 사용하여 성능 최적화
    자동 재시도 로직으로 일시적인 네트워크 오류 대응

    Attributes:
        client_id (str): 네이버 API 클라이언트 ID
        client_secret (str): 네이버 API 클라이언트 시크릿
        api_url (str): 네이버 쇼핑 API 엔드포인트 URL
        headers (dict): API 요청에 사용할 공통 헤더
        _client (httpx.AsyncClient): 재사용 가능한 비동기 HTTP 클라이언트
    """

    def __init__(self):
        """
        API 클라이언트 초기화

        환경 변수에서 API 인증 정보를 로드하고
        재사용 가능한 HTTP 클라이언트를 생성합니다.
        """
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET
        self.api_url = settings.NAVER_SHOPPING_API_URL
        self.headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        # HTTP 연결 재사용을 위한 클라이언트 인스턴스 (성능 최적화)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """
        HTTP 클라이언트 인스턴스 반환 (지연 초기화)

        Returns:
            httpx.AsyncClient: 재사용 가능한 HTTP 클라이언트

        Note:
            연결 풀을 재사용하여 성능을 향상시킵니다.
            limits 설정으로 동시 연결 수를 제어합니다.
        """
        if self._client is None:
            # 연결 풀 설정: 최대 100개 연결, 호스트당 최대 20개 연결
            limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=limits,
                follow_redirects=True
            )
        return self._client

    async def close(self) -> None:
        """
        HTTP 클라이언트 연결 종료

        Note:
            애플리케이션 종료 시 명시적으로 호출해야 합니다.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True
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
            query (str): 검색 키워드 (필수)
            display (int): 한 번에 표시할 검색 결과 개수 (1~100, 기본값 100)
            start (int): 검색 시작 위치 (1~1000, 기본값 1)
            sort (str): 정렬 옵션
                - "sim": 정확도순 (기본값)
                - "date": 날짜순
                - "asc": 가격 오름차순
                - "dsc": 가격 내림차순
            filter_options (dict, optional): 추가 필터 옵션
                - "filter": "naverpay" (네이버페이 상품만)
                - "exclude": "used:rental:cbshop" (중고/렌탈/해외직구 제외)

        Returns:
            Dict[str, Any]: 네이버 API 응답 JSON
                {
                    "lastBuildDate": "검색 결과 생성 시간",
                    "total": 전체 검색 결과 수,
                    "start": 검색 시작 위치,
                    "display": 반환된 결과 수,
                    "items": [상품 목록]
                }

        Raises:
            httpx.HTTPStatusError: HTTP 오류 발생 시
            httpx.RequestError: 네트워크 오류 발생 시

        Note:
            - 최대 3회 자동 재시도 (지수 백오프 전략)
            - 429 Too Many Requests 발생 시 대기 후 재시도
            - API 호출 제한: 초당 10회, 일일 25,000회
        """
        # 입력값 검증
        if not query or not query.strip():
            raise ValueError("검색 키워드는 필수입니다.")

        # 파라미터 검증 및 제한
        display = max(1, min(display, settings.MAX_DISPLAY))
        start = max(1, min(start, 1000))

        params = {
            "query": query.strip(),
            "display": display,
            "start": start,
            "sort": sort,
        }

        # 필터 옵션 추가
        if filter_options:
            params.update(filter_options)

        # HTTP 클라이언트 재사용 (성능 최적화)
        client = await self._get_client()

        try:
            logger.debug(f"API 요청: query={query}, display={display}, start={start}, sort={sort}")

            response = await client.get(
                self.api_url,
                headers=self.headers,
                params=params
            )
            response.raise_for_status()

            logger.info(f"API 응답 성공: query={query}, status={response.status_code}")
            return response.json()

        except httpx.HTTPStatusError as e:
            # HTTP 상태 코드별 처리
            status_code = e.response.status_code
            error_detail = e.response.text

            if status_code == 400:
                logger.error(f"잘못된 요청: {error_detail}")
            elif status_code == 401:
                logger.error(f"인증 실패: API 키를 확인하세요")
            elif status_code == 429:
                logger.warning(f"API 호출 한도 초과: 재시도 대기 중")
            elif status_code >= 500:
                logger.error(f"서버 오류: {status_code} - {error_detail}")

            logger.error(f"HTTP 오류 발생: {status_code} - {error_detail}")
            raise

        except httpx.RequestError as e:
            logger.error(f"네트워크 요청 오류: {str(e)}")
            raise

        except Exception as e:
            logger.error(f"예상치 못한 오류 발생: {str(e)}", exc_info=True)
            raise

    async def search_and_collect(
        self,
        query: str,
        max_results: int = 100,
        sort: str = "sim",
        filter_options: Optional[Dict[str, Any]] = None
    ) -> List[Product]:
        """
        네이버 쇼핑 API에서 상품을 검색하고 Product 모델 리스트로 변환

        여러 페이지에 걸쳐 검색 결과를 수집하며,
        각 상품 데이터를 정제하고 확장 정보를 추가합니다.

        Args:
            query (str): 검색 키워드
            max_results (int): 수집할 최대 상품 수 (기본값: 100)
            sort (str): 정렬 옵션 (sim/date/asc/dsc)
            filter_options (dict, optional): 필터 옵션
                - filter: "naverpay"
                - exclude: "used:rental:cbshop"

        Returns:
            List[Product]: 정제된 Product 객체 리스트

        Raises:
            ValueError: 검색 키워드가 없거나 max_results가 유효하지 않은 경우
            httpx.HTTPStatusError: API 호출 실패

        Note:
            - API 제한으로 한 번에 최대 100개까지만 조회 가능
            - 더 많은 결과가 필요하면 페이지네이션 사용
            - 각 상품에 순위(rank), 태그, 가격 분석 등의 메타데이터 추가
        """
        if not query or not query.strip():
            raise ValueError("검색 키워드는 필수입니다.")

        if max_results < 1:
            raise ValueError("max_results는 1 이상이어야 합니다.")

        products = []
        display = min(max_results, settings.MAX_DISPLAY)

        logger.info(f"상품 수집 시작: query='{query}', max_results={max_results}, sort={sort}")

        # 여러 페이지 수집이 필요한 경우 (페이지네이션)
        for start in range(1, max_results + 1, display):
            # 남은 결과 수 계산
            current_display = min(display, max_results - start + 1)

            try:
                result = await self.search_products(
                    query=query,
                    display=current_display,
                    start=start,
                    sort=sort,
                    filter_options=filter_options
                )

                items = result.get("items", [])
                if not items:
                    logger.info(f"더 이상 검색 결과가 없습니다. (start={start})")
                    break

                # 각 상품을 Product 모델로 변환
                for idx, item in enumerate(items):
                    try:
                        # 검색 결과 내 절대 순위 계산
                        rank = start + idx
                        product = self._convert_to_product(item, query, rank)
                        products.append(product)
                    except Exception as e:
                        # 개별 상품 변환 실패 시 로그만 남기고 계속 진행
                        logger.warning(f"상품 변환 실패 (rank={start + idx}): {str(e)}")
                        continue

                logger.debug(f"페이지 수집 완료: start={start}, collected={len(items)}")

                # 더 이상 결과가 없으면 중단 (마지막 페이지)
                if len(items) < current_display:
                    logger.info(f"마지막 페이지 도달: 총 {len(products)}개 수집")
                    break

            except Exception as e:
                logger.error(f"페이지 수집 중 오류 발생 (start={start}): {str(e)}")
                # 이미 수집한 데이터라도 반환
                break

        logger.info(f"상품 수집 완료: query='{query}', total={len(products)}개")
        return products

    def _convert_to_product(self, item: Dict[str, Any], search_keyword: str, rank: int) -> Product:
        """
        네이버 API 응답 아이템을 내부 Product 모델로 변환

        API 응답 데이터를 정제하고 추가 메타데이터를 계산합니다:
        - HTML 태그 제거
        - 카테고리 파싱
        - 자동 태그 추출
        - 가격 분석 (할인율, 가격 범위)
        - 상품 타입 분석 (중고/단종/판매예정 여부)

        Args:
            item (dict): 네이버 API 응답의 개별 상품 데이터
            search_keyword (str): 검색에 사용된 키워드
            rank (int): 검색 결과 내 순위 (1부터 시작)

        Returns:
            Product: 정제되고 확장된 상품 객체

        Note:
            - title에서 HTML 태그 제거 (예: <b>, </b>)
            - productType 값으로 상품 특성 자동 분류
            - 가격 정보가 없는 경우 0 또는 None 처리
        """
        # HTML 태그 제거 (네이버 API는 검색어 강조를 위해 <b> 태그 사용)
        title = self._strip_html_tags(item.get("title", ""))

        # 카테고리 정보 파싱 (최대 4단계)
        categories = self._parse_category(
            item.get("category1", ""),
            item.get("category2", ""),
            item.get("category3", ""),
            item.get("category4", "")
        )

        # 태그 자동 추출 (검색 및 필터링 최적화)
        tags = self._extract_tags(title, item.get("brand", ""), item.get("maker", ""))

        # 가격 정보 추출 및 검증
        try:
            lprice = int(item.get("lprice", 0))
        except (ValueError, TypeError):
            lprice = 0
            logger.warning(f"잘못된 lprice 값: {item.get('lprice')}")

        try:
            hprice = int(item.get("hprice", 0)) if item.get("hprice") else None
        except (ValueError, TypeError):
            hprice = None
            logger.warning(f"잘못된 hprice 값: {item.get('hprice')}")

        # 가격 분석 계산 (할인율 및 가격 범위)
        price_discount_rate = None
        price_range = None
        if hprice and hprice > 0 and lprice > 0:
            # 할인율 = (최고가 - 최저가) / 최고가 * 100
            price_discount_rate = round(((hprice - lprice) / hprice) * 100, 2)
            # 가격 범위 = 최고가 - 최저가
            price_range = hprice - lprice

        # productType 분석 (1~12 사이 값으로 상품 특성 구분)
        try:
            product_type = int(item.get("productType", 0)) if item.get("productType") else None
        except (ValueError, TypeError):
            product_type = None
            logger.warning(f"잘못된 productType 값: {item.get('productType')}")

        # productType을 기반으로 상품 특성 분류
        product_group, product_category_type, is_used, is_discontinued, is_presale = \
            self._parse_product_type(product_type)

        # Product 모델 생성 및 반환
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
        """
        HTML 태그 제거

        네이버 API는 검색어 강조를 위해 <b>, </b> 태그를 사용합니다.
        정규식을 사용하여 모든 HTML 태그를 제거합니다.

        Args:
            text (str): HTML 태그가 포함된 텍스트

        Returns:
            str: HTML 태그가 제거된 순수 텍스트

        Example:
            >>> _strip_html_tags("<b>갤럭시</b> 버즈2")
            "갤럭시 버즈2"
        """
        if not text:
            return ""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)

    @staticmethod
    def _parse_category(cat1: str = "", cat2: str = "", cat3: str = "", cat4: str = "") -> Dict[str, Optional[str]]:
        """
        카테고리 정보 파싱 및 정제

        네이버 API는 최대 4단계 카테고리를 제공합니다.
        빈 문자열을 None으로 변환하여 일관성을 유지합니다.

        Args:
            cat1 (str): 카테고리 1단계 (대분류)
            cat2 (str): 카테고리 2단계 (중분류)
            cat3 (str): 카테고리 3단계 (소분류)
            cat4 (str): 카테고리 4단계 (세분류)

        Returns:
            dict: 카테고리 딕셔너리
                {
                    "category1": "디지털/가전",
                    "category2": "음향가전",
                    "category3": "이어폰/헤드폰",
                    "category4": "블루투스이어폰"
                }
        """
        return {
            "category1": cat1.strip() if cat1 and cat1.strip() else None,
            "category2": cat2.strip() if cat2 and cat2.strip() else None,
            "category3": cat3.strip() if cat3 and cat3.strip() else None,
            "category4": cat4.strip() if cat4 and cat4.strip() else None,
        }

    @staticmethod
    def _extract_tags(title: str, brand: str = "", maker: str = "") -> List[str]:
        """
        상품 제목, 브랜드, 제조사에서 태그 자동 추출

        검색 최적화를 위해 상품의 주요 키워드를 태그로 추출합니다.
        - 제목: 공백으로 구분된 단어들
        - 브랜드: 전체 브랜드명
        - 제조사: 전체 제조사명

        Args:
            title (str): 상품 제목
            brand (str): 브랜드명
            maker (str): 제조사명

        Returns:
            List[str]: 추출된 태그 리스트 (최대 20개)

        Note:
            - 2글자 이상 단어만 태그로 추출
            - 중복 제거 (set 사용)
            - 최대 20개로 제한하여 DB 크기 최적화

        Example:
            >>> _extract_tags("삼성 갤럭시 버즈2 프로", "삼성", "삼성전자")
            ["삼성", "갤럭시", "버즈2", "프로", "삼성전자"]
        """
        tags = set()

        # 제목에서 단어 추출 (2글자 이상)
        if title:
            words = title.split()
            # 의미 있는 단어만 추출 (1글자 제외)
            tags.update([word.strip() for word in words if len(word.strip()) > 1])

        # 브랜드 추가
        if brand and brand.strip():
            tags.add(brand.strip())

        # 제조사 추가
        if maker and maker.strip():
            tags.add(maker.strip())

        # 최대 20개 태그로 제한 (DB 크기 최적화)
        return list(tags)[:20]

    @staticmethod
    def _parse_product_type(product_type: Optional[int]) -> tuple:
        """
        네이버 productType 값을 기반으로 상품 특성 분석

        네이버 쇼핑 API의 productType은 1~12 사이의 값으로
        상품의 유형과 가격비교 상태를 나타냅니다.

        productType 매핑 규칙:
        ┌─────────────┬──────────────────────────────────┐
        │ 값 범위     │ 상품군                           │
        ├─────────────┼──────────────────────────────────┤
        │ 1-3         │ 일반상품                         │
        │ 4-6         │ 중고상품                         │
        │ 7-9         │ 단종상품                         │
        │ 10-12       │ 판매예정상품                     │
        └─────────────┴──────────────────────────────────┘

        각 범위 내 세부 분류 (나머지 연산):
        - x % 3 == 1: 가격비교 상품
        - x % 3 == 2: 가격비교 비매칭 일반상품
        - x % 3 == 0: 가격비교 매칭 일반상품

        Args:
            product_type (int, optional): 상품 타입 (1~12)

        Returns:
            tuple: (상품군, 상품종류, 중고여부, 단종여부, 판매예정여부)
                - 상품군 (str or None): "일반상품", "중고상품", "단종상품", "판매예정상품"
                - 상품종류 (str or None): "가격비교상품", "가격비교비매칭", "가격비교매칭"
                - 중고여부 (bool): True/False
                - 단종여부 (bool): True/False
                - 판매예정여부 (bool): True/False

        Example:
            >>> _parse_product_type(1)
            ("일반상품", "가격비교상품", False, False, False)
            >>> _parse_product_type(5)
            ("중고상품", "가격비교비매칭", True, False, False)
            >>> _parse_product_type(12)
            ("판매예정상품", "가격비교매칭", False, False, True)
        """
        # 유효하지 않은 값 처리
        if not product_type or product_type < 1 or product_type > 12:
            return (None, None, False, False, False)

        # 상품군 판별 (범위 기반)
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

        # 상품 종류 판별 (나머지 연산 기반)
        remainder = product_type % 3
        if remainder == 1:
            product_category_type = "가격비교상품"
        elif remainder == 2:
            product_category_type = "가격비교비매칭"
        else:  # remainder == 0 (3, 6, 9, 12)
            product_category_type = "가격비교매칭"

        return (product_group, product_category_type, is_used, is_discontinued, is_presale)


# 싱글톤 인스턴스 생성
# 애플리케이션 전체에서 하나의 인스턴스를 재사용하여
# HTTP 연결 풀 및 설정을 공유합니다.
naver_api = NaverShoppingAPI()
