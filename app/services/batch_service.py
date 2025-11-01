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


class BatchCollectionService:
    """일괄 수집 서비스"""

    def __init__(self):
        self.is_running = False
        """현재 배치 작업 실행 중 여부 (동시 실행 방지)"""

    async def start_batch_collection(self, batch_id: str):
        """
        배치 수집 시작

        Args:
            batch_id: 배치 ID

        Note:
            백그라운드에서 비동기로 실행됨
        """
        if self.is_running:
            raise ValueError("이미 실행 중인 배치 작업이 있습니다.")

        self.is_running = True

        try:
            batch = await BatchCollection.find_one(
                BatchCollection.batch_id == batch_id
            )
            if not batch:
                raise ValueError(f"배치를 찾을 수 없습니다: {batch_id}")

            # 상태 업데이트
            batch.status = "running"
            batch.started_at = datetime.utcnow()
            await batch.save()

            logger.info(f"배치 수집 시작: {batch_id} ({batch.total_keywords}개 키워드)")

            # 키워드 목록 조회 (순서대로)
            keywords = await BatchKeyword.find(
                BatchKeyword.batch_id == batch_id,
                BatchKeyword.status.in_(["pending", "failed"])
            ).sort("order").to_list()

            # 순차 실행
            for idx, keyword in enumerate(keywords):
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

                except Exception as e:
                    logger.error(f"키워드 수집 실패: '{keyword.keyword}' - {e}")
                    keyword.status = "failed"
                    keyword.error_message = str(e)
                    keyword.completed_at = datetime.utcnow()
                    await keyword.save()

                    batch.failed_keywords += 1
                    batch.current_keyword_index = idx + 1
                    await batch.save()

                # Rate Limiting: 1분 대기 (마지막 키워드는 제외)
                if idx < len(keywords) - 1:
                    logger.info("다음 키워드까지 60초 대기...")
                    await asyncio.sleep(60)

            # 배치 완료
            batch.status = "completed"
            batch.completed_at = datetime.utcnow()
            await batch.save()

            logger.info(
                f"배치 수집 완료: {batch_id} "
                f"(완료: {batch.completed_keywords}, "
                f"실패: {batch.failed_keywords}, "
                f"건너뜀: {batch.skipped_keywords})"
            )

        except Exception as e:
            logger.error(f"배치 수집 오류: {batch_id} - {e}", exc_info=True)
            if batch:
                batch.status = "failed"
                batch.completed_at = datetime.utcnow()
                await batch.save()
            raise

        finally:
            self.is_running = False

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
        products = await naver_api.search_and_collect(
            query=keyword.keyword,
            max_results=1000,
            sort="sim",
            filter_options=None
        )

        if not products:
            keyword.status = "completed"
            keyword.completed_at = datetime.utcnow()
            await keyword.save()
            return {"status": "success", "collected": 0}

        # MongoDB에 저장
        saved_count = 0
        updated_count = 0

        for product in products:
            existing = await Product.find_one(
                Product.product_id == product.product_id
            )

            if existing:
                # 업데이트
                existing.lprice = product.lprice
                existing.hprice = product.hprice
                existing.updated_at = datetime.utcnow()
                await existing.save()
                updated_count += 1
            else:
                # 신규 저장
                await product.insert()
                saved_count += 1

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
