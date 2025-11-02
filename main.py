"""
네이버 쇼핑 API 수집기 메인 애플리케이션

FastAPI 기반의 웹 애플리케이션으로 다음 기능을 제공합니다:
- 네이버 쇼핑 API를 통한 상품 데이터 수집
- MongoDB를 사용한 데이터 저장 및 관리
- RESTful API 엔드포인트 제공
- 웹 UI를 통한 상품 검색 및 관리

주요 구성 요소:
- FastAPI: 웹 프레임워크
- Motor: 비동기 MongoDB 드라이버
- Beanie: MongoDB ODM
- Jinja2: 템플릿 엔진
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config.database import db
from app.routes import products_router
from app.routes.batch import router as batch_router
from app.config import settings
from app.services.naver_api import naver_api
import logging
from logging.handlers import RotatingFileHandler
import os

# 로깅 디렉토리 생성
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 로깅 설정
# 파일 로테이션: 최대 10MB, 최대 5개 백업 파일
handlers = [
    logging.StreamHandler(),  # 콘솔 출력
]

# 운영 환경에서는 파일 로그 활성화 권장
if not settings.API_RELOAD:  # 운영 환경 (reload=False)
    file_handler = RotatingFileHandler(
        f"{log_dir}/app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    handlers.append(file_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=handlers
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 라이프사이클 관리

    FastAPI의 lifespan context manager를 사용하여
    앱 시작과 종료 시 필요한 초기화 및 정리 작업을 수행합니다.

    시작 시:
        - MongoDB 연결 초기화
        - 인덱스 생성 (Beanie ODM)
        - HTTP 클라이언트 초기화

    종료 시:
        - MongoDB 연결 종료
        - HTTP 클라이언트 종료
        - 리소스 정리

    Args:
        app (FastAPI): FastAPI 애플리케이션 인스턴스

    Yields:
        None: 애플리케이션 실행 중
    """
    # ============ 시작 이벤트 ============
    logger.info("=" * 50)
    logger.info("애플리케이션 시작 중...")
    logger.info("=" * 50)

    try:
        # MongoDB 연결
        await db.connect_db()
        logger.info("✓ MongoDB 연결 성공")

        # 연결 상태 확인
        is_healthy = await db.health_check()
        if not is_healthy:
            logger.warning("⚠ MongoDB 헬스체크 실패")
        else:
            logger.info("✓ MongoDB 헬스체크 성공")

        logger.info("=" * 50)
        logger.info("애플리케이션 시작 완료")
        logger.info(f"API 문서: http://{settings.API_HOST}:{settings.API_PORT}/api/docs")
        logger.info(f"웹 UI: http://{settings.API_HOST}:{settings.API_PORT}/")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"❌ 애플리케이션 시작 실패: {str(e)}", exc_info=True)
        raise

    # 애플리케이션 실행 (yield)
    yield

    # ============ 종료 이벤트 ============
    logger.info("=" * 50)
    logger.info("애플리케이션 종료 중...")
    logger.info("=" * 50)

    try:
        # HTTP 클라이언트 종료
        await naver_api.close()
        logger.info("✓ HTTP 클라이언트 종료")

        # MongoDB 연결 종료
        await db.close_db()
        logger.info("✓ MongoDB 연결 종료")

        logger.info("=" * 50)
        logger.info("애플리케이션 종료 완료")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"❌ 종료 중 오류 발생: {str(e)}", exc_info=True)


# FastAPI 애플리케이션 생성
# OpenAPI 문서 자동 생성 및 Swagger UI 제공
app = FastAPI(
    title="Naver Shopping API Collector",
    description="""
    # 네이버 쇼핑 API 수집기

    네이버 쇼핑 검색 API를 활용한 상품 데이터 수집 및 관리 시스템

    ## 주요 기능
    - 🔍 네이버 쇼핑 API 상품 검색 및 수집
    - 💾 MongoDB를 통한 상품 데이터 저장
    - 📊 상품 검색, 필터링, 통계 조회
    - 📈 가격 분석 및 카테고리 분류
    - 🔄 중복 방지 및 자동 업데이트

    ## 기술 스택
    - FastAPI (웹 프레임워크)
    - MongoDB + Beanie (데이터베이스)
    - httpx (HTTP 클라이언트)
    - Jinja2 (템플릿 엔진)
    """,
    version="1.2.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    contact={
        "name": "API Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT License",
    }
)

# ==================== 미들웨어 설정 ====================

# CORS 미들웨어 추가 (보안 강화)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # 허용할 출처
    allow_credentials=True,  # 쿠키 포함 요청 허용
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # 허용할 HTTP 메서드
    allow_headers=["*"],  # 허용할 헤더
    max_age=3600,  # Preflight 요청 캐시 시간 (초)
)

logger.info(f"CORS 설정: 허용된 출처 = {settings.cors_origins_list}")

# ==================== 정적 파일 및 템플릿 ====================

# 정적 파일 마운트 (CSS, JS, 이미지 등)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 템플릿 엔진 설정
templates = Jinja2Templates(directory="templates")

# ==================== 라우터 등록 ====================

# 라우터 등록
app.include_router(products_router)  # 상품 관련 API
app.include_router(batch_router)  # 일괄 수집 API

# WebSocket 라우터
from app.routes.websocket import router as websocket_router
app.include_router(websocket_router)  # WebSocket API


@app.get("/", response_class=HTMLResponse, tags=["web"])
async def index(request: Request):
    """
    웹 UI 메인 페이지

    사용자 친화적인 웹 인터페이스를 제공합니다:
    - 상품 검색 및 수집
    - 검색 이력 조회
    - 상품 목록 표시

    Args:
        request (Request): FastAPI Request 객체

    Returns:
        HTMLResponse: 렌더링된 HTML 템플릿
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api", tags=["root"])
async def api_root():
    """
    API 루트 엔드포인트

    API 정보 및 주요 엔드포인트 링크를 제공합니다.

    Returns:
        dict: API 메타데이터
            - message: API 이름
            - version: 현재 버전
            - docs: API 문서 URL
            - redoc: ReDoc 문서 URL
            - web_ui: 웹 UI URL
    """
    return {
        "message": "Naver Shopping API Collector",
        "version": "1.2.0",
        "docs": "/api/docs",
        "redoc": "/api/redoc",
        "web_ui": "/",
        "endpoints": {
            "products": "/products",
            "collect": "/products/collect",
            "search": "/products/search",
            "stats": "/products/stats/summary"
        }
    }


@app.get("/health", tags=["health"])
async def health_check():
    """
    헬스 체크 엔드포인트

    애플리케이션 및 데이터베이스 상태를 확인합니다.
    로드 밸런서, 모니터링 도구에서 사용됩니다.

    Returns:
        dict: 헬스 체크 결과
            - status: 전체 상태 (healthy/unhealthy)
            - database: DB 연결 상태 (connected/disconnected)
            - database_healthy: DB 헬스체크 결과 (true/false)

    Example:
        ```json
        {
            "status": "healthy",
            "database": "connected",
            "database_healthy": true
        }
        ```
    """
    # DB 연결 상태 확인
    db_connected = db.client is not None

    # DB 헬스체크 수행
    db_healthy = await db.health_check() if db_connected else False

    # 전체 상태 결정
    overall_status = "healthy" if db_connected and db_healthy else "unhealthy"

    return {
        "status": overall_status,
        "database": "connected" if db_connected else "disconnected",
        "database_healthy": db_healthy
    }


if __name__ == "__main__":
    """
    애플리케이션 직접 실행

    개발 환경에서 직접 실행 시 사용됩니다.
    운영 환경에서는 Gunicorn + Uvicorn을 권장합니다.

    실행 방법:
        python main.py

    운영 환경 실행 예시:
        gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
    """
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level="info",
        access_log=True
    )
