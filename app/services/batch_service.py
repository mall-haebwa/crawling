"""
일괄 수집 서비스

CSV 파일의 키워드 목록을 1분 간격으로 순차 수집
"""

import asyncio
import logging
from datetime import datetime
from typing import List
from app.models.batch import BatchCollection, BatchKeyword
from app.models import Product, ProductSearchResponse
from app.services.naver_api import naver_api

logger = logging.getLogger(__name__)


async def broadcast_batch_status(batch_id: str):
    """
    배치 상태를 WebSocket으로 브로드캐스트

    Args:
        batch_id: 배치 ID
    """
    try:
        # 순환 import 방지를 위해 함수 내부에서 import
        from app.routes.websocket import manager

        # 배치 상태 조회
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )
        if not batch:
            return

        # 키워드 목록 조회
        keywords = await BatchKeyword.find(
            BatchKeyword.batch_id == batch_id
        ).sort("order").to_list()

        # 현재 키워드
        current_keyword = None
        if batch.current_keyword_index < len(keywords):
            current_keyword = keywords[batch.current_keyword_index]

        # 통계 계산
        total_products = sum(k.total_collected for k in keywords)
        new_products = sum(k.new_products for k in keywords)
        updated_products = sum(k.updated_products for k in keywords)

        # 진행률 계산
        percentage = 0
        if batch.total_keywords > 0:
            completed = batch.completed_keywords + batch.failed_keywords + batch.skipped_keywords
            percentage = round((completed / batch.total_keywords) * 100, 1)

        # 메시지 구성
        message = {
            "batch_id": batch.batch_id,
            "status": batch.status,
            "progress": {
                "total": batch.total_keywords,
                "completed": batch.completed_keywords,
                "failed": batch.failed_keywords,
                "skipped": batch.skipped_keywords,
                "current_index": batch.current_keyword_index,
                "percentage": percentage
            },
            "current_keyword": {
                "keyword": current_keyword.keyword if current_keyword else None,
                "status": current_keyword.status if current_keyword else None
            } if current_keyword else None,
            "stats": {
                "total_products": total_products,
                "new_products": new_products,
                "updated_products": updated_products
            }
        }

        # WebSocket으로 브로드캐스트
        await manager.broadcast(batch_id, message)
        logger.debug(f"WebSocket 브로드캐스트: batch_id={batch_id}, status={batch.status}")

    except Exception as e:
        logger.error(f"WebSocket 브로드캐스트 실패: {e}", exc_info=True)


class BatchCollectionService:
    """일괄 수집 서비스"""

    def __init__(self):
        self.is_running = False
        """현재 배치 작업 실행 중 여부 (동시 실행 방지)"""

        self.current_batch_id: str | None = None
        """현재 실행 중인 배치 ID"""

        self._lock = asyncio.Lock()
        """Race condition 방지를 위한 비동기 락"""

    async def start_batch_collection(self, batch_id: str):
        """
        배치 수집 시작

        Args:
            batch_id: 배치 ID

        Note:
            백그라운드에서 비동기로 실행됨

        Raises:
            ValueError: 이미 실행 중인 배치가 있거나 배치를 찾을 수 없는 경우
        """
        # Race condition 방지: 락을 사용하여 동시 실행 체크
        async with self._lock:
            if self.is_running:
                error_msg = f"이미 실행 중인 배치 작업이 있습니다: {self.current_batch_id}"
                logger.warning(error_msg)
                raise ValueError(error_msg)
            self.is_running = True
            self.current_batch_id = batch_id

        try:
            batch = await BatchCollection.find_one(
                BatchCollection.batch_id == batch_id
            )
            if not batch:
                raise ValueError(f"배치를 찾을 수 없습니다: {batch_id}")

            # 상태 업데이트
            batch.status = "running"
            if not batch.started_at:  # 최초 시작인 경우만
                batch.started_at = datetime.utcnow()
            await batch.save()

            # WebSocket 브로드캐스트
            await broadcast_batch_status(batch_id)

            logger.info(f"배치 수집 시작: {batch_id} ({batch.total_keywords}개 키워드)")

            # 키워드 목록 조회 (순서대로)
            # pending 또는 failed 상태인 키워드만 수집 (재시도 지원)
            keywords = await BatchKeyword.find(
                BatchKeyword.batch_id == batch_id
            ).sort("order").to_list()

            # pending 또는 failed 상태만 필터링
            keywords = [k for k in keywords if k.status in ["pending", "failed"]]

            # 순차 실행
            for idx, keyword in enumerate(keywords):
                # 일시정지 체크
                batch = await BatchCollection.find_one(
                    BatchCollection.batch_id == batch_id
                )
                if batch.status == "paused":
                    logger.info(f"배치 일시정지됨: {batch_id}")
                    await broadcast_batch_status(batch_id)
                    return

                if batch.status == "cancelled":
                    logger.info(f"배치 취소됨: {batch_id}")
                    await broadcast_batch_status(batch_id)
                    return

                logger.info(
                    f"[{idx + 1}/{len(keywords)}] 키워드 수집 시작: '{keyword.keyword}'"
                )

                # 중복 체크
                is_duplicate = await self._check_duplicate(keyword.keyword)
                if is_duplicate:
                    keyword.status = "skipped"
                    keyword.previously_collected = True
                    keyword.completed_at = datetime.utcnow()
                    await keyword.save()

                    batch.skipped_keywords += 1
                    batch.current_keyword_index = idx + 1
                    await batch.save()

                    # WebSocket 브로드캐스트
                    await broadcast_batch_status(batch_id)

                    logger.info(f"중복 키워드 건너뜀: '{keyword.keyword}'")
                    continue

                # 수집 실행
                try:
                    result = await self._collect_keyword(batch, keyword)

                    if result["status"] == "success":
                        batch.completed_keywords += 1
                    else:
                        batch.failed_keywords += 1

                    batch.current_keyword_index = idx + 1
                    await batch.save()

                    # WebSocket 브로드캐스트
                    await broadcast_batch_status(batch_id)

                except Exception as e:
                    logger.error(f"키워드 수집 실패: '{keyword.keyword}' - {e}")
                    keyword.status = "failed"
                    keyword.error_message = str(e)
                    keyword.completed_at = datetime.utcnow()
                    await keyword.save()

                    batch.failed_keywords += 1
                    batch.current_keyword_index = idx + 1
                    await batch.save()

                    # WebSocket 브로드캐스트
                    await broadcast_batch_status(batch_id)

                # Rate Limiting: 사용자 지정 시간 대기 (마지막 키워드는 제외)
                if idx < len(keywords) - 1:
                    wait_seconds = batch.rate_limit_seconds
                    logger.info(f"다음 키워드까지 {wait_seconds}초 대기...")
                    # 1초씩 체크하면서 대기 (일시정지/취소 즉시 반응)
                    for _ in range(wait_seconds):
                        batch = await BatchCollection.find_one(
                            BatchCollection.batch_id == batch_id
                        )
                        if batch.status in ["paused", "cancelled"]:
                            logger.info(f"대기 중 배치 상태 변경: {batch.status}")
                            return
                        await asyncio.sleep(1)

            # 배치 완료
            batch.status = "completed"
            batch.completed_at = datetime.utcnow()
            await batch.save()

            # WebSocket 브로드캐스트
            await broadcast_batch_status(batch_id)

            logger.info(
                f"배치 수집 완료: {batch_id} "
                f"(완료: {batch.completed_keywords}, "
                f"실패: {batch.failed_keywords}, "
                f"건너뜀: {batch.skipped_keywords})"
            )

        except Exception as e:
            logger.error(f"배치 수집 오류: {batch_id} - {e}", exc_info=True)
            # 배치 상태를 실패로 안전하게 업데이트
            try:
                batch = await BatchCollection.find_one(
                    BatchCollection.batch_id == batch_id
                )
                if batch:
                    batch.status = "failed"
                    batch.completed_at = datetime.utcnow()
                    await batch.save()

                    # WebSocket 브로드캐스트
                    await broadcast_batch_status(batch_id)
            except Exception as save_error:
                logger.error(f"배치 상태 저장 실패: {save_error}", exc_info=True)
            raise

        finally:
            # 락을 사용하여 안전하게 상태 초기화
            async with self._lock:
                self.is_running = False
                self.current_batch_id = None

    async def _check_duplicate(self, keyword: str) -> bool:
        """
        중복 키워드 체크 (시간 무관)

        Args:
            keyword: 검색 키워드

        Returns:
            bool: 이전에 수집한 적 있으면 True
        """
        # ProductSearchResponse에서 수집 이력 확인
        existing = await ProductSearchResponse.find_one(
            ProductSearchResponse.search_keyword == keyword
        )

        return existing is not None

    async def _collect_keyword(
        self, batch: BatchCollection, keyword: BatchKeyword
    ) -> dict:
        """
        개별 키워드 수집

        Args:
            batch: 배치 객체
            keyword: 키워드 객체

        Returns:
            dict: 수집 결과
        """
        # 상태 업데이트
        keyword.status = "running"
        keyword.started_at = datetime.utcnow()
        await keyword.save()

        # 네이버 API로 상품 검색 (1000개 = 100 × 10)
        # 타임아웃 설정: 최대 10분 (네트워크 지연 고려)
        try:
            products = await asyncio.wait_for(
                naver_api.search_and_collect(
                    query=keyword.keyword,
                    max_results=1000,
                    sort="sim",
                    filter_options=None
                ),
                timeout=600.0  # 10분 타임아웃 (1000개 수집 시 충분한 시간)
            )
        except asyncio.TimeoutError:
            logger.error(f"키워드 수집 타임아웃: '{keyword.keyword}' (10분 초과)")
            keyword.status = "failed"
            keyword.error_message = "수집 타임아웃 (10분 초과)"
            keyword.completed_at = datetime.utcnow()
            await keyword.save()
            return {"status": "failed", "error": "timeout"}
        except Exception as e:
            # 기타 예외 처리 (네트워크 오류, API 오류 등)
            logger.error(f"키워드 수집 중 오류: '{keyword.keyword}' - {str(e)}", exc_info=True)
            keyword.status = "failed"
            keyword.error_message = f"수집 오류: {str(e)}"
            keyword.completed_at = datetime.utcnow()
            await keyword.save()
            return {"status": "failed", "error": str(e)}

        if not products:
            keyword.status = "completed"
            keyword.completed_at = datetime.utcnow()
            await keyword.save()
            return {"status": "success", "collected": 0}

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
            search_keyword=keyword.keyword,
            total_count=len(products),
            display=100,
            start=1,
            sort="sim",
            collected_at=datetime.utcnow()
        )
        await search_history.insert()

        # 키워드 결과 업데이트
        keyword.status = "completed"
        keyword.total_collected = len(products)
        keyword.new_products = saved_count
        keyword.updated_products = updated_count
        keyword.completed_at = datetime.utcnow()
        await keyword.save()

        logger.info(
            f"키워드 수집 완료: '{keyword.keyword}' "
            f"(총 {len(products)}개, 신규 {saved_count}, 업데이트 {updated_count})"
        )

        return {
            "status": "success",
            "collected": len(products),
            "new": saved_count,
            "updated": updated_count
        }


# 싱글톤 인스턴스
batch_service = BatchCollectionService()
