# Naver Shopping API Collector

네이버 쇼핑 Open API를 활용한 상품 데이터 수집 및 관리 시스템입니다.
FastAPI + MongoDB 기반으로 구축되었으며, 자연어 기반 검색을 지원합니다.

## 주요 기능

### 데이터 수집
- 네이버 쇼핑 API를 통한 상품 데이터 수집 (키워드당 최대 1,000개)
- 중복 수집 방지 (키워드 기반 영구 방지, force 옵션으로 재수집 가능)
- 수집 이력 관리 및 조회

### 데이터 관리
- MongoDB를 활용한 데이터 저장 및 관리
- 상품 정보 자동 업데이트 (가격 정보 갱신)
- 상세한 상품 정보 및 메타데이터 수집

### 검색 및 필터링
- 자연어 기반 검색 지원 (제목, 브랜드, 제조사)
- 카테고리, 가격, 쇼핑몰별 필터링
- 페이지네이션 지원 (검색 조건 유지)
- 총 검색 결과 개수 표시

### API 및 UI
- FastAPI 기반 RESTful API 제공
- 직관적인 웹 UI (상품 수집, 검색, 통계 확인)
- 실시간 통계 및 분석 기능
- 최근 수집 이력 표시 (최대 10개)

## 시스템 요구사항

- Python 3.11+ (권장: 3.12.3)
  - Python 3.11, 3.12, 3.13 완전 지원
  - Python 3.14 실험적 지원
- MongoDB 4.4+
- Naver Open API 키 (Client ID, Client Secret)

## 프로젝트 구조

```
crawling/
├── app/                        # 애플리케이션 소스 코드
│   ├── config/                 # 설정 파일 (database, settings)
│   ├── models/                 # 데이터 모델 (Product, SearchResponse)
│   ├── routes/                 # API 라우터 (products)
│   └── services/               # 비즈니스 로직 (naver_api)
├── static/                     # 정적 파일 (CSS, JS)
├── templates/                  # HTML 템플릿
├── docs/                       # 문서
│   ├── PYTHON_313_COMPATIBILITY.md  # Python 3.13/3.14 호환성 분석
│   ├── SECURITY.md             # 보안 가이드라인
│   └── backups/                # 의존성 백업 파일
├── main.py                     # 애플리케이션 진입점
├── requirements.txt            # 의존성 목록
├── .env.example                # 환경 변수 템플릿
└── README.md                   # 프로젝트 문서 (현재 파일)
```

## 설치 방법

### 1. 저장소 클론 및 이동

```bash
git clone <repository-url>
cd crawling
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows
```

### 3. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 필요한 정보를 입력합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용:

```env
# Naver API Credentials (필수)
NAVER_CLIENT_ID=your_client_id_here
NAVER_CLIENT_SECRET=your_client_secret_here

# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=naver_shopping

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=True

# Search Configuration
DEFAULT_DISPLAY=100
MAX_DISPLAY=100
```

### 5. MongoDB 설치 및 실행

Ubuntu/Debian:
```bash
sudo apt-get install mongodb
sudo systemctl start mongodb
```

macOS:
```bash
brew install mongodb-community
brew services start mongodb-community
```

Docker:
```bash
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

## 네이버 API 키 발급 방법

1. [네이버 개발자 센터](https://developers.naver.com/main/) 접속
2. 로그인 후 '애플리케이션 등록' 선택
3. 애플리케이션 이름 입력
4. 사용 API에서 '검색' 선택
5. 비로그인 오픈 API 서비스 환경에서 'WEB 설정' 추가
6. 등록 후 발급된 Client ID와 Client Secret을 `.env` 파일에 입력

## 실행 방법

### 개발 모드로 실행

```bash
python main.py
```

또는

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 프로덕션 모드로 실행

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 사용 방법

서버 실행 후 다음 주소에서 서비스를 이용할 수 있습니다:

### 웹 UI
- **메인 페이지**: http://localhost:8000
  - 상품 수집 (키워드당 최대 1,000개 자동 수집)
  - 중복 수집 방지 (이미 수집한 키워드 자동 차단)
  - 최근 수집 이력 표시 (키워드, 개수, 수집 시간)
  - 상품 검색 (키워드, 가격 범위 - 총 개수 표시)
  - 페이지네이션 (검색 조건 유지)
  - 통계 정보 (총 상품 수, 상위 쇼핑몰)

### API 문서
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

## API 엔드포인트

### 상품 수집

#### POST /products/collect
네이버 쇼핑 API로 상품 검색 후 MongoDB에 저장

**Request:**
```bash
curl -X POST "http://localhost:8000/products/collect?query=갤럭시버즈&max_results=100&sort=sim"
```

**Parameters:**
- `query` (required): 검색 키워드
- `max_results` (optional, default=1000): 수집할 최대 상품 수 (1~1000)
- `sort` (optional, default=sim): 정렬 옵션
  - `sim`: 정확도순
  - `date`: 날짜순
  - `asc`: 가격 오름차순
  - `dsc`: 가격 내림차순
- `filter` (optional): 필터 옵션
  - `naverpay`: 네이버페이 연동 상품만
- `exclude` (optional): 제외 옵션
  - `used`: 중고 상품 제외
  - `rental`: 렌탈 상품 제외
  - `cbshop`: 해외직구/구매대행 상품 제외
  - 여러 개 조합 가능 (콜론으로 구분): `used:rental:cbshop`

**Response:**
```json
{
  "status": "success",
  "query": "갤럭시버즈",
  "total_collected": 100,
  "new_products": 95,
  "updated_products": 5,
  "timestamp": "2025-10-31T04:00:00.000000"
}
```

### 상품 검색

#### GET /products/search
저장된 상품을 다양한 조건으로 검색

**Request:**
```bash
curl -X GET "http://localhost:8000/products/search?keyword=삼성&min_price=100000&max_price=500000&limit=20"
```

**Parameters:**
- `keyword` (optional): 제목, 브랜드, 제조사에서 검색
- `category1` (optional): 카테고리 1단계 필터
- `mall_name` (optional): 쇼핑몰 이름 필터
- `min_price` (optional): 최소 가격
- `max_price` (optional): 최대 가격
- `limit` (optional, default=50): 조회할 최대 결과 수 (1~500)
- `skip` (optional, default=0): 건너뛸 결과 수 (페이지네이션)

### 상품 상세 조회

#### GET /products/{product_id}
특정 상품의 상세 정보 조회

**Request:**
```bash
curl -X GET "http://localhost:8000/products/12345678"
```

### 상품 목록 조회

#### GET /products/
저장된 모든 상품 조회 (페이지네이션)

**Request:**
```bash
curl -X GET "http://localhost:8000/products/?limit=50&skip=0"
```

### 통계 정보

#### GET /products/stats/summary
전체 상품 통계 정보 조회

**Request:**
```bash
curl -X GET "http://localhost:8000/products/stats/summary"
```

**Response:**
```json
{
  "total_products": 1500,
  "top_malls": [
    {"_id": "네이버", "count": 500},
    {"_id": "쿠팡", "count": 300}
  ],
  "top_categories": [
    {"_id": "디지털/가전", "count": 800},
    {"_id": "패션의류", "count": 400}
  ],
  "timestamp": "2025-10-31T04:00:00.000000"
}
```

### 상품 삭제

#### DELETE /products/{product_id}
특정 상품 삭제

**Request:**
```bash
curl -X DELETE "http://localhost:8000/products/12345678"
```

## 프로젝트 구조

```
crawling/
├── app/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py       # 환경 설정
│   │   └── database.py        # MongoDB 연결 관리
│   ├── models/
│   │   ├── __init__.py
│   │   └── product.py         # 상품 데이터 모델
│   ├── services/
│   │   ├── __init__.py
│   │   └── naver_api.py       # 네이버 API 클라이언트
│   └── routes/
│       ├── __init__.py
│       └── products.py        # 상품 관련 엔드포인트
├── templates/
│   └── index.html             # 웹 UI 템플릿
├── main.py                    # FastAPI 애플리케이션 진입점
├── requirements.txt           # 의존성 패키지
├── .env.example              # 환경 변수 예시
└── README.md                 # 프로젝트 문서
```

## 데이터 구조

### 📦 Product (상품 데이터)

수집되는 상품 데이터는 다음과 같은 구조를 가집니다:

#### 기본 필드 요약

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `product_id` | string | ✅ | 상품 고유 ID (네이버 상품 번호) |
| `title` | string | ✅ | 상품명 (HTML 태그 제거됨) |
| `link` | string | ✅ | 상품 상세 페이지 URL |
| `image` | string | ❌ | 상품 이미지 URL |
| `lprice` | int | ✅ | 최저가 (원) |
| `hprice` | int | ❌ | 최고가 (원) |
| `mallName` | string | ✅ | 쇼핑몰 이름 |
| `maker` | string | ❌ | 제조사 |
| `brand` | string | ❌ | 브랜드 |
| `category1~4` | string | ❌ | 카테고리 (4단계) |
| `search_keyword` | string | ✅ | 검색 키워드 |
| `tags` | array | ✅ | 자동 추출 태그 |
| `rank` | int | ❌ | 검색 결과 내 순위 |

<details>
<summary><b>📋 전체 스키마 보기</b></summary>

#### 기본 식별 정보
```json
{
  "product_id": "12345678",
  "title": "삼성전자 갤럭시 버즈2 프로",
  "link": "https://search.shopping.naver.com/gate.nhn?id=12345678",
  "image": "https://shopping-phinf.pstatic.net/main_1234567/12345678.jpg"
}
```

#### 가격 정보
```json
{
  "lprice": 189000,              // 최저가 (원)
  "hprice": 229000,              // 최고가 (원, 선택)
  "price_discount_rate": 17.47,  // 할인율 (%, 자동 계산)
  "price_range": 40000           // 가격 범위 (원, 자동 계산)
}
```

#### 판매자 정보
```json
{
  "mallName": "네이버",
  "maker": "삼성전자",
  "brand": "삼성"
}
```

#### 카테고리 정보 (최대 4단계)
```json
{
  "category1": "디지털/가전",      // 대분류
  "category2": "음향가전",         // 중분류
  "category3": "이어폰/헤드폰",    // 소분류
  "category4": "블루투스이어폰"    // 세분류
}
```

#### 상품 타입 분석 (자동)
```json
{
  "productType": 1,                    // 네이버 API 제공 (1~12)
  "product_group": "일반상품",         // 일반/중고/단종/판매예정
  "product_category_type": "가격비교상품",  // 가격비교/비매칭/매칭
  "is_used": false,                    // 중고 여부
  "is_discontinued": false,            // 단종 여부
  "is_presale": false                  // 판매예정 여부
}
```

#### 검색 및 분석
```json
{
  "search_keyword": "갤럭시 버즈",
  "tags": ["삼성", "갤럭시", "버즈2", "프로", "무선", "블루투스"],
  "rank": 1
}
```

#### 메타데이터
```json
{
  "created_at": "2025-10-31T04:00:00.000Z",  // 최초 수집 시각
  "updated_at": "2025-10-31T08:00:00.000Z",  // 최근 갱신 시각
  "last_build_date": "2025-10-31T03:55:00.000Z"  // API 응답 생성 시각
}
```

</details>

### 📊 ProductSearchResponse (검색 이력)

```json
{
  "search_keyword": "갤럭시 버즈",     // 검색 키워드
  "total_count": 100,                 // 수집된 상품 수
  "display": 100,                     // 한 번에 표시된 결과 수
  "start": 1,                         // 검색 시작 위치
  "sort": "sim",                      // 정렬 옵션 (sim/date/asc/dsc)
  "collected_at": "2025-10-31T..."    // 수집 시각
}
```

### 💡 데이터 수집 특징

#### 1. 자동 데이터 확장
네이버 API 기본 응답에 다음 정보를 자동으로 추가합니다:
- **가격 분석**: 할인율, 가격 범위 자동 계산
- **태그 추출**: 제목, 브랜드, 제조사에서 키워드 자동 추출 (최대 20개)
- **상품 타입 분석**: productType 값을 분석하여 중고/단종/판매예정 여부 자동 판별
- **검색 순위**: 검색 결과 내 순위 자동 저장

#### 2. MongoDB 인덱스
검색 성능 최적화를 위해 다음 필드에 인덱스를 생성합니다:
- `product_id` (고유 인덱스)
- `title`, `search_keyword`, `mallName`, `brand`, `category1`
- `created_at` (시계열 조회)
- 텍스트 인덱스: `title`, `brand`, `maker` (전문 검색)

#### 3. 데이터 갱신 정책
- **신규 상품**: 전체 데이터 저장
- **기존 상품**: `lprice`, `hprice`, `updated_at` 필드만 업데이트
- **중복 확인**: `product_id` 기준

## 사용 예시

### 1. 상품 데이터 수집

```bash
# "무선 이어폰" 키워드로 100개 상품 수집 (정확도순)
curl -X POST "http://localhost:8000/products/collect?query=무선이어폰&max_results=100&sort=sim"

# "노트북" 키워드로 200개 상품 수집 (가격 낮은순)
curl -X POST "http://localhost:8000/products/collect?query=노트북&max_results=200&sort=asc"
```

### 2. 자연어 검색

```bash
# "삼성" 키워드로 검색
curl -X GET "http://localhost:8000/products/search?keyword=삼성"

# 가격 범위로 필터링 (10만원~50만원)
curl -X GET "http://localhost:8000/products/search?keyword=이어폰&min_price=100000&max_price=500000"

# 특정 쇼핑몰의 상품만 검색
curl -X GET "http://localhost:8000/products/search?mall_name=쿠팡"

# 카테고리 필터링
curl -X GET "http://localhost:8000/products/search?category1=디지털/가전"
```

### 3. 페이지네이션

```bash
# 첫 번째 페이지 (0~49)
curl -X GET "http://localhost:8000/products/?limit=50&skip=0"

# 두 번째 페이지 (50~99)
curl -X GET "http://localhost:8000/products/?limit=50&skip=50"
```

## 주요 기술 스택

- **FastAPI**: 고성능 웹 프레임워크
- **MongoDB**: NoSQL 데이터베이스
- **Beanie**: MongoDB용 비동기 ODM
- **Motor**: 비동기 MongoDB 드라이버
- **httpx**: 비동기 HTTP 클라이언트
- **Pydantic**: 데이터 검증 및 설정 관리
- **Tenacity**: 재시도 로직

## 특징

### 1. 상세한 상품 정보 수집
- 네이버 쇼핑 API에서 제공하는 모든 필드 수집
- 카테고리 정보 (최대 4단계)
- 가격 정보 (최저가, 최고가)
- 판매자 정보 (쇼핑몰, 브랜드, 제조사)

### 2. 자연어 검색 지원
- 제목, 브랜드, 제조사에서 키워드 검색
- 자동 태그 추출 및 태그 기반 검색
- MongoDB 텍스트 인덱스 활용

### 3. 고급 필터링
- 가격 범위 필터
- 카테고리 필터
- 쇼핑몰 필터
- 조합 검색 지원

### 4. 중복 방지
- product_id 기반 중복 체크
- 기존 상품은 가격 정보만 업데이트

### 5. 에러 처리
- Tenacity를 활용한 자동 재시도
- 상세한 에러 로깅
- HTTP 상태 코드 기반 예외 처리

## 트러블슈팅

### MongoDB 연결 오류
**증상**: `pymongo.errors.ServerSelectionTimeoutError`

**해결방법**:
```bash
# MongoDB 실행 상태 확인
sudo systemctl status mongodb  # Linux
brew services list  # macOS

# MongoDB 재시작
sudo systemctl restart mongodb  # Linux
brew services restart mongodb-community  # macOS
```

### 네이버 API 오류
**증상**: `HTTP 401 Unauthorized`

**해결방법**:
1. `.env` 파일에 실제 API 키가 입력되었는지 확인
2. 네이버 개발자 센터에서 API 키 재확인
3. 서버 재시작

### 포트 이미 사용 중
**증상**: `Address already in use`

**해결방법**:
```bash
# 포트 8000 사용 프로세스 확인 및 종료
lsof -i :8000  # Linux/macOS
kill -9 <PID>
```

### 모듈을 찾을 수 없음
**증상**: `ModuleNotFoundError`

**해결방법**:
```bash
# 가상환경 활성화 확인
source .venv/bin/activate  # Linux/Mac

# 의존성 재설치
pip install -r requirements.txt
```

## 보안

민감한 정보 관리 및 보안 가이드는 [SECURITY.md](SECURITY.md)를 참고하세요.

**중요 사항**:
- `.env` 파일을 절대 Git에 커밋하지 마세요
- API 키가 노출되면 즉시 재발급하세요
- MongoDB는 인증을 활성화하고 방화벽을 설정하세요

## 기여하기

### 코드 스타일
- PEP 8 준수
- Type hints 사용
- Docstring 작성 (모든 함수/클래스)

### Pull Request
1. Fork 후 브랜치 생성
2. 변경사항 커밋
3. 테스트 실행
4. PR 생성

자세한 내용은 프로젝트 코드의 주석을 참고하세요.

## 라이선스

MIT License

## 주요 의존성 버전

- **FastAPI** 0.120.4 (Python 3.14 지원)
- **Pydantic** 2.12.3 (Python 3.13/3.14 지원)
- **Beanie** 2.0.0 (MongoDB ODM)
- **Motor** 3.7.1 (Async MongoDB Driver)
- **PyMongo** 4.15.3
- **httpx** 0.28.1
- **Uvicorn** 0.38.0

자세한 내용은 [PYTHON_313_COMPATIBILITY.md](./docs/PYTHON_313_COMPATIBILITY.md)를 참고하세요.

## 참고 자료

- [네이버 개발자 센터](https://developers.naver.com/)
- [네이버 검색 API 가이드](https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md)
- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [MongoDB 공식 문서](https://www.mongodb.com/docs/)
- [Beanie ODM 문서](https://beanie-odm.dev/)
