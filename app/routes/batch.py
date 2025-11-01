"""
일괄 수집 API 라우터

CSV 파일 업로드 및 배치 수집 관리 엔드포인트
"""

import csv
import io
import logging
from fastapi import APIRouter, HTTPException, File, UploadFile, BackgroundTasks
from typing import List
from datetime import datetime

from app.models.batch import BatchCollection, BatchKeyword
from app.services.batch_service import batch_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/upload")
async def upload_csv_batch(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV 파일 (첫 번째 열에 키워드)")
):
    """
    CSV 파일 업로드 및 일괄 수집 시작

    ## CSV 파일 형식
    ```csv
    keyword
    갤럭시 버즈
    아이폰 15
    맥북 프로
    ```

    ## 수집 조건
    - 각 키워드당 1000개 수집 (100개 × 10회)
    - 1분 간격으로 순차 수집
    - 중복 키워드 자동 건너뛰기 (시간 무관)

    ## 응답
    ```json
    {
        "batch_id": "uuid",
        "total_keywords": 10,
        "status": "pending",
        "message": "배치 수집이 시작되었습니다"
    }
    ```
    """
    try:
        # CSV 파일 검증
        if not file.filename.endswith('.csv'):
            raise HTTPException(
                status_code=400,
                detail="CSV 파일만 업로드 가능합니다"
            )

        # 파일 읽기
        contents = await file.read()
        decoded = contents.decode('utf-8-sig')  # BOM 처리
        csv_file = io.StringIO(decoded)

        # CSV 파싱
        reader = csv.DictReader(csv_file)

        # 키워드 추출
        keywords = []
        for row in reader:
            keyword = row.get('keyword', '').strip()

            # 빈 줄 건너뛰기
            if not keyword:
                continue

            # 주석 건너뛰기
            if keyword.startswith('#'):
                continue

            keywords.append(keyword)

        if not keywords:
            raise HTTPException(
                status_code=400,
                detail="CSV 파일에 유효한 키워드가 없습니다"
            )

        logger.info(f"CSV 파일 파싱 완료: {len(keywords)}개 키워드")

        # BatchCollection 생성
        batch = BatchCollection(
            csv_filename=file.filename,
            total_keywords=len(keywords)
        )
        await batch.insert()

        # BatchKeyword 생성
        for idx, keyword in enumerate(keywords):
            batch_keyword = BatchKeyword(
                batch_id=batch.batch_id,
                keyword=keyword,
                order=idx
            )
            await batch_keyword.insert()

        logger.info(f"배치 생성 완료: {batch.batch_id}")

        # 백그라운드에서 수집 시작
        background_tasks.add_task(
            batch_service.start_batch_collection,
            batch.batch_id
        )

        return {
            "batch_id": batch.batch_id,
            "total_keywords": batch.total_keywords,
            "status": batch.status,
            "message": "배치 수집이 시작되었습니다. /batch/{batch_id}/status 에서 진행 상황을 확인하세요."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV 업로드 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="CSV 업로드 중 오류가 발생했습니다. 관리자에게 문의하세요."
        )


@router.get("/{batch_id}/status")
async def get_batch_status(batch_id: str):
    """
    배치 수집 상태 조회

    ## 응답 예시
    ```json
    {
        "batch_id": "uuid",
        "status": "running",
        "progress": {
            "total": 10,
            "completed": 3,
            "failed": 0,
            "skipped": 1,
            "current_index": 3,
            "percentage": 30
        },
        "current_keyword": {
            "keyword": "갤럭시 버즈",
            "status": "running"
        },
        "stats": {
            "total_products": 3000,
            "new_products": 2500,
            "updated_products": 500
        },
        "created_at": "2025-01-11T10:00:00Z",
        "started_at": "2025-01-11T10:00:05Z"
    }
    ```
    """
    try:
        # 배치 조회
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )

        if not batch:
            raise HTTPException(
                status_code=404,
                detail=f"배치를 찾을 수 없습니다: {batch_id}"
            )

        # 키워드 목록 조회
        keywords = await BatchKeyword.find(
            BatchKeyword.batch_id == batch_id
        ).sort("order").to_list()

        # 현재 키워드 찾기
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

        return {
            "batch_id": batch.batch_id,
            "csv_filename": batch.csv_filename,
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
            },
            "created_at": batch.created_at.isoformat(),
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 상태 조회 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 상태 조회 중 오류가 발생했습니다."
        )


@router.get("/{batch_id}/keywords")
async def get_batch_keywords(batch_id: str):
    """
    배치의 키워드 목록 조회

    ## 응답 예시
    ```json
    {
        "batch_id": "uuid",
        "keywords": [
            {
                "keyword": "갤럭시 버즈",
                "status": "completed",
                "order": 0,
                "total_collected": 1000,
                "new_products": 800,
                "updated_products": 200,
                "started_at": "2025-01-11T10:00:05Z",
                "completed_at": "2025-01-11T10:02:30Z"
            }
        ]
    }
    ```
    """
    try:
        # 배치 존재 확인
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )

        if not batch:
            raise HTTPException(
                status_code=404,
                detail=f"배치를 찾을 수 없습니다: {batch_id}"
            )

        # 키워드 목록 조회
        keywords = await BatchKeyword.find(
            BatchKeyword.batch_id == batch_id
        ).sort("order").to_list()

        return {
            "batch_id": batch_id,
            "keywords": [
                {
                    "keyword": k.keyword,
                    "status": k.status,
                    "order": k.order,
                    "total_collected": k.total_collected,
                    "new_products": k.new_products,
                    "updated_products": k.updated_products,
                    "previously_collected": k.previously_collected,
                    "started_at": k.started_at.isoformat() if k.started_at else None,
                    "completed_at": k.completed_at.isoformat() if k.completed_at else None,
                    "error_message": k.error_message
                }
                for k in keywords
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 키워드 조회 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 키워드 조회 중 오류가 발생했습니다."
        )


@router.post("/{batch_id}/pause")
async def pause_batch(batch_id: str):
    """
    배치 수집 일시정지

    실행 중인 배치를 일시정지합니다.
    현재 처리 중인 키워드는 완료되고, 다음 키워드부터 중지됩니다.
    """
    try:
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )

        if not batch:
            raise HTTPException(
                status_code=404,
                detail=f"배치를 찾을 수 없습니다: {batch_id}"
            )

        if batch.status != "running":
            raise HTTPException(
                status_code=400,
                detail=f"실행 중인 배치만 일시정지할 수 있습니다. 현재 상태: {batch.status}"
            )

        batch.status = "paused"
        await batch.save()

        logger.info(f"배치 일시정지: {batch_id}")

        return {
            "batch_id": batch_id,
            "status": "paused",
            "message": "배치가 일시정지되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 일시정지 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 일시정지 중 오류가 발생했습니다."
        )


@router.post("/{batch_id}/resume")
async def resume_batch(batch_id: str, background_tasks: BackgroundTasks):
    """
    배치 수집 재개

    일시정지된 배치를 재개합니다.
    남은 키워드부터 다시 수집을 시작합니다.
    """
    try:
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )

        if not batch:
            raise HTTPException(
                status_code=404,
                detail=f"배치를 찾을 수 없습니다: {batch_id}"
            )

        if batch.status != "paused":
            raise HTTPException(
                status_code=400,
                detail=f"일시정지된 배치만 재개할 수 있습니다. 현재 상태: {batch.status}"
            )

        # 백그라운드에서 재개
        background_tasks.add_task(
            batch_service.start_batch_collection,
            batch_id
        )

        logger.info(f"배치 재개: {batch_id}")

        return {
            "batch_id": batch_id,
            "status": "running",
            "message": "배치가 재개되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 재개 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 재개 중 오류가 발생했습니다."
        )


@router.post("/{batch_id}/cancel")
async def cancel_batch(batch_id: str):
    """
    배치 수집 취소

    실행 중이거나 일시정지된 배치를 취소합니다.
    현재 처리 중인 키워드는 완료되고, 나머지는 취소됩니다.
    """
    try:
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )

        if not batch:
            raise HTTPException(
                status_code=404,
                detail=f"배치를 찾을 수 없습니다: {batch_id}"
            )

        if batch.status not in ["running", "paused", "pending"]:
            raise HTTPException(
                status_code=400,
                detail=f"실행 중이거나 일시정지된 배치만 취소할 수 있습니다. 현재 상태: {batch.status}"
            )

        batch.status = "cancelled"
        batch.completed_at = datetime.utcnow()
        await batch.save()

        logger.info(f"배치 취소: {batch_id}")

        return {
            "batch_id": batch_id,
            "status": "cancelled",
            "message": "배치가 취소되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 취소 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 취소 중 오류가 발생했습니다."
        )


@router.delete("/{batch_id}")
async def delete_batch(batch_id: str):
    """
    배치 삭제

    완료되었거나 취소된 배치와 관련 키워드 데이터를 삭제합니다.
    실행 중인 배치는 삭제할 수 없습니다.
    """
    try:
        batch = await BatchCollection.find_one(
            BatchCollection.batch_id == batch_id
        )

        if not batch:
            raise HTTPException(
                status_code=404,
                detail=f"배치를 찾을 수 없습니다: {batch_id}"
            )

        if batch.status in ["running", "pending"]:
            raise HTTPException(
                status_code=400,
                detail="실행 중인 배치는 삭제할 수 없습니다. 먼저 취소하세요."
            )

        # 관련 키워드 삭제
        await BatchKeyword.find(
            BatchKeyword.batch_id == batch_id
        ).delete()

        # 배치 삭제
        await batch.delete()

        logger.info(f"배치 삭제: {batch_id}")

        return {
            "batch_id": batch_id,
            "message": "배치가 삭제되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 삭제 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 삭제 중 오류가 발생했습니다."
        )


@router.get("/list")
async def list_batches(limit: int = 10):
    """
    최근 배치 목록 조회

    Args:
        limit: 조회할 배치 수 (기본 10개)
    """
    try:
        batches = await BatchCollection.find_all() \
            .sort(-BatchCollection.created_at) \
            .limit(limit) \
            .to_list()

        return {
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "csv_filename": b.csv_filename,
                    "status": b.status,
                    "total_keywords": b.total_keywords,
                    "completed_keywords": b.completed_keywords,
                    "created_at": b.created_at.isoformat()
                }
                for b in batches
            ]
        }

    except Exception as e:
        logger.error(f"배치 목록 조회 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="배치 목록 조회 중 오류가 발생했습니다."
        )
