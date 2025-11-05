"""
상품 관련 API 라우터

네이버 쇼핑 API를 통한 상품 수집, 검색, 조회, 통계 기능을 제공합니다.

주요 엔드포인트:
- POST /products/collect: 상품 수집
- GET /products/search: 상품 검색
- GET /products/{product_id}: 상품 상세 조회
- DELETE /products/{product_id}: 상품 삭제
- GET /products/stats/summary: 통계 조회
- GET /products/history/recent: 수집 이력 조회
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.models import Product, ProductSearchResponse
from app.services import naver_api
from datetime import datetime
import logging
import re
import asyncio

logger = logging.getLogger(__name__)

# 상품 관련 API 라우터
# prefix: /products
# tags: OpenAPI 문서에서 그룹화에 사용
router = APIRouter(prefix="/products", tags=["products"])


def sanitize_mongodb_input(value: str) -> str:
    """
    MongoDB operator injection 방어를 위한 입력 sanitization

    $ 및 . 문자를 제거하여 MongoDB 쿼리 연산자 삽입 공격을 방지합니다.

    Args:
        value: 사용자 입력 문자열

    Returns:
        안전하게 처리된 문자열
    """
    if not value:
        return value

    # MongoDB 쿼리 연산자에 사용되는 특수 문자 제거
    sanitized = value.replace("$", "").replace(".", "")

    return sanitized


@router.post("/collect", response_model=dict)
async def collect_products(
    query: str = Query(..., description="검색 키워드"),
    max_results: int = Query(100, ge=1, le=1000, description="수집할 최대 결과 수"),
    sort: str = Query("sim", regex="^(sim|date|asc|dsc)$", description="정렬 옵션 (sim: 정확도, date: 날짜, asc: 가격↑, dsc: 가격↓)"),
    filter: Optional[str] = Query(None, regex="^(naverpay)$", description="필터 옵션 (naverpay: 네이버페이 연동 상품만)"),
    exclude: Optional[str] = Query(None, description="제외 옵션 (used:중고, rental:렌탈, cbshop:해외직구/구매대행, 콜론으로 구분)"),
    force: bool = Query(False, description="중복 수집 강제 실행 (true: 최근 수집 무시)")
):
    """
    네이버 쇼핑 API로 상품 검색 후 MongoDB에 저장

    ## 주요 기능
    - 네이버 쇼핑 API 호출하여 상품 데이터 수집
    - 중복 수집 방지 (force=false 시)
    - 신규 상품은 저장, 기존 상품은 가격 정보 업데이트
    - 검색 이력 자동 저장

    ## 파라미터
    - **query** (필수): 검색 키워드 (예: "갤럭시 버즈")
    - **max_results**: 수집할 최대 상품 수 (1~1000, 기본 100)
    - **sort**: 정렬 옵션
        - sim: 정확도순 (기본값)
        - date: 최신순
        - asc: 가격 낮은 순
        - dsc: 가격 높은 순
    - **filter**: 네이버페이 연동 상품만 검색 (naverpay)
    - **exclude**: 제외할 상품 유형 (콜론으로 구분)
        - used: 중고 상품
        - rental: 렌탈 상품
        - cbshop: 해외직구/구매대행 상품
        - 예: "used:rental:cbshop"
    - **force**: 중복 수집 강제 실행 (기본값: false)

    ## 응답
    - status: "success" 또는 "skipped"
    - total_collected: 수집된 총 상품 수
    - new_products: 신규 저장된 상품 수
    - updated_products: 업데이트된 상품 수
    - hint: force=true 사용 안내 (중복 수집 스킵 시)

    ## 에러
    - 404: 검색 결과가 없음
    - 500: 서버 오류 또는 API 호출 실패

    ## 사용 예시
    ```
    POST /products/collect?query=갤럭시 버즈&max_results=100&sort=sim
    ```
    """
    try:
        # 중복 수집 방지: 이미 수집한 키워드인지 확인
        if not force:
            existing_collection = await ProductSearchResponse.find_one(
                ProductSearchResponse.search_keyword == query
            )

            if existing_collection:
                time_diff = datetime.utcnow() - existing_collection.collected_at
                days = time_diff.days
                hours = int((time_diff.total_seconds() % 86400) / 3600)
                minutes = int((time_diff.total_seconds() % 3600) / 60)

                # 경과 시간 메시지 구성
                if days > 0:
                    time_message = f"{days}일 {hours}시간"
                elif hours > 0:
                    time_message = f"{hours}시간 {minutes}분"
                else:
                    time_message = f"{minutes}분"

                return {
                    "status": "skipped",
                    "query": query,
                    "message": f"'{query}' 키워드는 {time_message} 전에 이미 수집되었습니다.",
                    "last_collected": existing_collection.collected_at.isoformat(),
                    "total_collected": 0,
                    "new_products": 0,
                    "updated_products": 0,
                    "hint": "force=true 파라미터로 강제 수집 가능"
                }
        # 필터 옵션 구성
        filter_options = {}
        if filter:
            filter_options["filter"] = filter
        if exclude:
            filter_options["exclude"] = exclude

        # 네이버 API로 상품 검색 및 수집
        products = await naver_api.search_and_collect(
            query=query,
            max_results=max_results,
            sort=sort,
            filter_options=filter_options if filter_options else None
        )

        if not products:
            raise HTTPException(status_code=404, detail="검색 결과가 없습니다.")

        # MongoDB에 저장 (N+1 쿼리 최적화: 벌크 작업)
        saved_count = 0
        updated_count = 0

        # 1. 모든 product_id를 한 번에 조회 (1 쿼리)
        product_ids = [p.product_id for p in products]
        existing_products = await Product.find(
            {"product_id": {"$in": product_ids}}
        ).to_list()

        # 2. 기존 상품을 딕셔너리로 매핑 (O(1) 조회)
        existing_map = {p.product_id: p for p in existing_products}

        # 3. 신규/업데이트 분류
        products_to_insert = []
        products_to_update = []

        for product in products:
            if product.product_id in existing_map:
                # 업데이트 대상
                existing = existing_map[product.product_id]
                existing.lprice = product.lprice
                existing.hprice = product.hprice
                existing.updated_at = datetime.utcnow()
                products_to_update.append(existing)
                updated_count += 1
            else:
                # 신규 삽입 대상
                products_to_insert.append(product)
                saved_count += 1

        # 4. 벌크 작업 실행 (병렬 처리로 성능 최적화)
        tasks = []
        if products_to_insert:
            tasks.append(Product.insert_many(products_to_insert))

        if products_to_update:
            # 업데이트는 배치 크기로 나눠서 처리 (너무 많은 동시 작업 방지)
            batch_size = 50
            for i in range(0, len(products_to_update), batch_size):
                batch = products_to_update[i:i + batch_size]
                tasks.append(asyncio.gather(*[p.save() for p in batch]))

        # 모든 작업 병렬 실행
        if tasks:
            await asyncio.gather(*tasks)

        # 검색 이력 저장
        search_history = ProductSearchResponse(
            search_keyword=query,
            total_count=len(products),
            display=max_results,
            start=1,
            sort=sort,
            collected_at=datetime.utcnow()
        )
        await search_history.insert()

        return {
            "status": "success",
            "query": query,
            "total_collected": len(products),
            "new_products": saved_count,
            "updated_products": updated_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"입력값 검증 오류 (query={query}): {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"상품 수집 오류 (query={query}): {str(e)}", exc_info=True)
        # 보안: 내부 에러 상세 정보 노출 방지
        raise HTTPException(status_code=500, detail="상품 수집 중 오류가 발생했습니다. 관리자에게 문의하세요.")


@router.get("/search", response_model=dict)
async def search_products(
    keyword: Optional[str] = Query(None, description="검색 키워드 (제목, 브랜드, 제조사)"),
    product_id: Optional[str] = Query(None, description="상품 ID로 검색"),
    category1: Optional[str] = Query(None, description="카테고리 1단계"),
    mall_name: Optional[str] = Query(None, description="쇼핑몰 이름"),
    min_price: Optional[int] = Query(None, ge=0, description="최소 가격"),
    max_price: Optional[int] = Query(None, ge=0, description="최대 가격"),
    limit: int = Query(50, ge=1, le=500, description="조회할 최대 결과 수"),
    skip: int = Query(0, ge=0, description="건너뛸 결과 수 (페이지네이션)")
):
    """
    MongoDB에 저장된 상품 검색

    인덱스를 활용한 최적화된 검색을 제공합니다.

    ## 파라미터
    - **keyword**: 제목, 브랜드, 제조사에서 검색
    - **product_id**: 상품 ID로 검색
    - **category1**: 카테고리 필터 (인덱스 활용)
    - **mall_name**: 쇼핑몰 필터 (인덱스 활용)
    - **min_price**: 최소 가격
    - **max_price**: 최대 가격
    - **limit**: 조회할 최대 결과 수
    - **skip**: 건너뛸 결과 수 (페이지네이션용)

    ## 응답
    - total: 전체 결과 수
    - count: 현재 페이지 결과 수
    - skip: 건너뛴 결과 수
    - limit: 최대 조회 수
    - products: 상품 목록
    """
    try:
        # 쿼리 빌더 - 인덱스 활용을 위해 순서 최적화
        query_conditions = []

        # 상품 ID 검색 (우선순위 최상위)
        if product_id:
            sanitized_id = sanitize_mongodb_input(product_id)
            query_conditions.append({"product_id": sanitized_id})

        # 인덱스가 있는 필드 우선 처리
        if category1:
            query_conditions.append({"category1": category1})

        if mall_name:
            # NoSQL Injection 방지: MongoDB 연산자 제거 + 정규식 특수문자 이스케이프
            sanitized_mall = sanitize_mongodb_input(mall_name)
            escaped_mall = re.escape(sanitized_mall)
            query_conditions.append({"mallName": {"$regex": escaped_mall, "$options": "i"}})

        if keyword:
            # 텍스트 검색 (제목, 브랜드, 제조사)
            # MongoDB 텍스트 인덱스 우선 사용, 실패 시 regex 사용
            # text 인덱스: [("title", "text"), ("brand", "text"), ("maker", "text")]
            # NoSQL Injection 방지: MongoDB 연산자 제거 + 정규식 특수문자 이스케이프
            sanitized_keyword = sanitize_mongodb_input(keyword)
            escaped_keyword = re.escape(sanitized_keyword)
            query_conditions.append({
                "$or": [
                    {"title": {"$regex": escaped_keyword, "$options": "i"}},
                    {"brand": {"$regex": escaped_keyword, "$options": "i"}},
                    {"maker": {"$regex": escaped_keyword, "$options": "i"}},
                    {"tags": keyword}  # 배열 검색 최적화
                ]
            })

        if min_price is not None or max_price is not None:
            price_condition = {}
            if min_price is not None:
                price_condition["$gte"] = min_price
            if max_price is not None:
                price_condition["$lte"] = max_price
            query_conditions.append({"lprice": price_condition})

        # 최종 쿼리 구성
        if query_conditions:
            final_query = {"$and": query_conditions} if len(query_conditions) > 1 else query_conditions[0]
            # 병렬로 count와 데이터 조회 (성능 최적화)
            total_count, products = await asyncio.gather(
                Product.find(final_query).count(),
                Product.find(final_query).skip(skip).limit(limit).to_list()
            )
        else:
            # 병렬로 count와 데이터 조회 (성능 최적화)
            total_count, products = await asyncio.gather(
                Product.count(),
                Product.find_all().skip(skip).limit(limit).to_list()
            )

        return {
            "total": total_count,
            "count": len(products),
            "skip": skip,
            "limit": limit,
            "products": products
        }

    except Exception as e:
        logger.error(f"상품 검색 오류: {str(e)}", exc_info=True)
        # 보안: 내부 에러 상세 정보 노출 방지
        raise HTTPException(status_code=500, detail="상품 검색 중 오류가 발생했습니다. 관리자에게 문의하세요.")


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    """
    특정 상품 상세 정보 조회

    - **product_id**: 상품 고유 ID
    """
    product = await Product.find_one(Product.product_id == product_id)

    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    return product


@router.get("/", response_model=List[Product])
async def list_products(
    limit: int = Query(50, ge=1, le=500, description="조회할 최대 결과 수"),
    skip: int = Query(0, ge=0, description="건너뛸 결과 수")
):
    """
    저장된 모든 상품 조회 (페이지네이션)

    - **limit**: 조회할 최대 결과 수
    - **skip**: 건너뛸 결과 수
    """
    try:
        products = await Product.find_all().skip(skip).limit(limit).to_list()
        return products
    except Exception as e:
        logger.error(f"상품 목록 조회 오류: {str(e)}", exc_info=True)
        # 보안: 내부 에러 상세 정보 노출 방지
        raise HTTPException(status_code=500, detail="상품 조회 중 오류가 발생했습니다. 관리자에게 문의하세요.")


@router.delete("/{product_id}")
async def delete_product(product_id: str):
    """
    특정 상품 삭제

    - **product_id**: 상품 고유 ID
    """
    product = await Product.find_one(Product.product_id == product_id)

    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    await product.delete()

    return {"status": "success", "message": f"상품 {product_id}가 삭제되었습니다."}


@router.get("/stats/summary", response_model=dict)
async def get_stats():
    """
    전체 상품 통계 정보
    """
    try:
        total_products = await Product.count()

        # Beanie 2.0에서는 aggregate를 직접 사용하지 않고 get_pymongo_collection()을 통해 접근
        collection = Product.get_pymongo_collection()

        # 쇼핑몰별 집계
        pipeline = [
            {"$group": {"_id": "$mallName", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        mall_stats = await collection.aggregate(pipeline).to_list(length=10)

        # 카테고리별 집계
        pipeline = [
            {"$group": {"_id": "$category1", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        category_stats = await collection.aggregate(pipeline).to_list(length=10)

        return {
            "total_products": total_products,
            "top_malls": mall_stats,
            "top_categories": category_stats,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"통계 조회 오류: {str(e)}", exc_info=True)
        # 보안: 내부 에러 상세 정보 노출 방지
        raise HTTPException(status_code=500, detail="통계 조회 중 오류가 발생했습니다. 관리자에게 문의하세요.")


@router.get("/history/recent", response_model=List[dict])
async def get_recent_collection_history(
    limit: int = Query(10, ge=1, le=100, description="조회할 이력 수")
):
    """
    최근 수집 이력 조회

    - **limit**: 조회할 이력 수 (기본값: 10)
    """
    try:
        # 최근 수집 이력 조회 (최신순)
        history = await ProductSearchResponse.find_all() \
            .sort(-ProductSearchResponse.collected_at) \
            .limit(limit) \
            .to_list()

        result = []
        for item in history:
            result.append({
                "keyword": item.search_keyword,
                "total_count": item.total_count,
                "sort": item.sort,
                "collected_at": item.collected_at.isoformat(),
            })

        return result

    except Exception as e:
        logger.error(f"수집 이력 조회 오류: {str(e)}", exc_info=True)
        # 보안: 내부 에러 상세 정보 노출 방지
        raise HTTPException(status_code=500, detail="수집 이력 조회 중 오류가 발생했습니다. 관리자에게 문의하세요.")


@router.get("/history/keyword/{keyword}", response_model=List[dict])
async def get_keyword_collection_history(
    keyword: str,
    limit: int = Query(10, ge=1, le=100, description="조회할 이력 수")
):
    """
    특정 키워드의 수집 이력 조회

    - **keyword**: 검색 키워드
    - **limit**: 조회할 이력 수 (기본값: 10)
    """
    try:
        # 특정 키워드의 수집 이력 조회 (최신순)
        history = await ProductSearchResponse.find(
            ProductSearchResponse.search_keyword == keyword
        ).sort(-ProductSearchResponse.collected_at).limit(limit).to_list()

        result = []
        for item in history:
            result.append({
                "keyword": item.search_keyword,
                "total_count": item.total_count,
                "sort": item.sort,
                "collected_at": item.collected_at.isoformat(),
            })

        return result

    except Exception as e:
        logger.error(f"키워드 이력 조회 오류 (keyword={keyword}): {str(e)}", exc_info=True)
        # 보안: 내부 에러 상세 정보 노출 방지
        raise HTTPException(status_code=500, detail="키워드 이력 조회 중 오류가 발생했습니다. 관리자에게 문의하세요.")
