# 일괄 수집 기능 가이드

**작성일**: 2025-01-11
**버전**: MVP v1.0

## 개요

CSV 파일에 키워드 목록을 작성하여 자동으로 일괄 수집하는 기능입니다.

### 주요 특징
- 📄 CSV 파일 업로드로 간편하게 키워드 등록
- 🔢 각 키워드당 1000개 자동 수집 (100개 × 10회)
- ⏱️ 1분 간격 Rate Limiting (네이버 API 보호)
- 🚫 중복 키워드 자동 건너뛰기 (시간 무관)
- 📊 실시간 진행 상황 조회

---

## CSV 파일 형식

### 기본 형식
```csv
keyword
갤럭시 버즈
아이폰 15
맥북 프로
에어팟
닌텐도 스위치
```

### 규칙
1. **첫 번째 행**: 반드시 `keyword` (헤더)
2. **두 번째 행부터**: 각 줄에 키워드 하나씩
3. **주석**: `#`로 시작하는 줄은 무시됨
4. **빈 줄**: 자동으로 건너뜀

### 예시 (주석 포함)
```csv
keyword
# 우선순위 높은 제품
갤럭시 버즈
아이폰 15

# 일반 제품
맥북 프로
에어팟

# 테스트용
# 닌텐도 스위치
```

---

## 사용 방법

### 1. CSV 파일 준비
- Excel, 메모장, VS Code 등으로 CSV 파일 작성
- 파일명: `keywords.csv` (또는 원하는 이름)
- 인코딩: UTF-8 (한글 깨짐 방지)

### 2. API로 업로드

#### cURL 사용
```bash
curl -X POST "http://localhost:8000/batch/upload" \
  -F "file=@keywords.csv"
```

#### Python 사용
```python
import requests

with open('keywords.csv', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/batch/upload',
        files={'file': f}
    )

result = response.json()
print(f"Batch ID: {result['batch_id']}")
```

#### 응답 예시
```json
{
  "batch_id": "123e4567-e89b-12d3-a456-426614174000",
  "total_keywords": 5,
  "status": "pending",
  "message": "배치 수집이 시작되었습니다. /batch/{batch_id}/status 에서 진행 상황을 확인하세요."
}
```

### 3. 진행 상황 확인

```bash
# 전체 진행 상황
curl "http://localhost:8000/batch/{batch_id}/status"

# 키워드별 상세 현황
curl "http://localhost:8000/batch/{batch_id}/keywords"
```

#### 진행 상황 응답 예시
```json
{
  "batch_id": "123e4567-e89b-12d3-a456-426614174000",
  "csv_filename": "keywords.csv",
  "status": "running",
  "progress": {
    "total": 5,
    "completed": 2,
    "failed": 0,
    "skipped": 1,
    "current_index": 2,
    "percentage": 40.0
  },
  "current_keyword": {
    "keyword": "아이폰 15",
    "status": "running"
  },
  "stats": {
    "total_products": 2000,
    "new_products": 1800,
    "updated_products": 200
  },
  "created_at": "2025-01-11T10:00:00Z",
  "started_at": "2025-01-11T10:00:05Z"
}
```

### 4. 최근 배치 목록 조회

```bash
curl "http://localhost:8000/batch/list?limit=10"
```

---

## 동작 방식

### 수집 프로세스

```
1. CSV 업로드
   ↓
2. 키워드 파싱 (주석/빈 줄 제거)
   ↓
3. BatchCollection 생성
   ↓
4. 각 키워드별 BatchKeyword 생성
   ↓
5. 백그라운드에서 순차 수집 시작
   ↓
6. 키워드 1: 중복 체크
   - 중복 → 건너뛰기 (skipped)
   - 신규 → 1000개 수집 (100×10회)
   ↓
7. 1분 대기 (Rate Limiting)
   ↓
8. 키워드 2: 반복...
   ↓
9. 모든 키워드 완료
   ↓
10. 배치 상태 = "completed"
```

### 중복 처리 로직

```python
# 이전에 수집한 적 있는 키워드인지 확인
existing = ProductSearchResponse.find_one(keyword == "갤럭시 버즈")

if existing:
    # 시간에 관계없이 무조건 건너뛰기
    status = "skipped"
else:
    # 1000개 수집
    status = "completed"
```

### Rate Limiting

```
키워드 1 수집 (2분 소요)
  ↓
[60초 대기]
  ↓
키워드 2 수집 (2분 소요)
  ↓
[60초 대기]
  ↓
키워드 3 수집...
```

- **간격**: 1분 (60초)
- **목적**: 네이버 API 과부하 방지, 서버 안정성
- **적용**: 마지막 키워드 제외 모든 키워드 사이

---

## 상태 코드

### 배치 상태 (BatchCollection.status)
- `pending`: 수집 대기 중
- `running`: 수집 진행 중
- `completed`: 모든 키워드 수집 완료
- `failed`: 오류로 인한 실패

### 키워드 상태 (BatchKeyword.status)
- `pending`: 수집 대기 중
- `running`: 현재 수집 중
- `completed`: 수집 완료
- `failed`: 수집 실패 (에러 발생)
- `skipped`: 중복으로 건너뜀

---

## 시간 계산

### 예상 소요 시간

```
키워드 개수: N개
각 키워드 수집 시간: 약 2분
키워드 간 대기 시간: 1분

총 소요 시간 = N × (2분 + 1분) = N × 3분
(마지막 키워드는 대기 시간 없음)

예시:
- 5개 키워드 = 약 15분
- 10개 키워드 = 약 30분
- 20개 키워드 = 약 1시간
```

---

## 주의사항

### 1. CSV 파일 인코딩
- ⚠️ **UTF-8 사용 필수**
- Excel에서 저장 시: "CSV UTF-8(쉼표로 분리)" 선택
- 메모장에서 저장 시: 인코딩을 UTF-8로 선택

### 2. 중복 키워드
- ⚠️ **한 번 수집한 키워드는 다시 수집되지 않음**
- 재수집이 필요하면 기존 `/products/collect` API 사용 (force=true)

### 3. 동시 실행
- ⚠️ **한 번에 하나의 배치만 실행 가능**
- 진행 중인 배치가 있으면 대기 필요

### 4. 키워드 개수 제한
- 💡 실용적인 개수: 10~50개
- 너무 많으면: 완료까지 시간 오래 소요

---

## 트러블슈팅

### 문제: CSV 업로드 실패 (400 에러)

**원인**:
- CSV 파일 형식 오류
- 헤더가 `keyword`가 아님
- 파일 확장자가 `.csv`가 아님

**해결**:
1. 파일 확장자 확인 (.csv)
2. 첫 줄에 `keyword` 헤더 확인
3. 인코딩을 UTF-8로 변경

### 문제: 한글 깨짐

**원인**: 인코딩 문제

**해결**:
```bash
# 파일 인코딩 확인
file -i keywords.csv

# UTF-8이 아니면 변환
iconv -f EUC-KR -t UTF-8 keywords.csv > keywords_utf8.csv
```

### 문제: 배치가 시작되지 않음

**원인**:
- 다른 배치가 실행 중
- 서버 오류

**해결**:
1. 진행 중인 배치 확인: `GET /batch/list`
2. 로그 확인: `logs/app.log`

### 문제: 특정 키워드만 실패

**원인**:
- 네이버 API에서 해당 키워드 결과 없음
- 일시적인 네트워크 오류

**해결**:
1. 키워드 상태 확인: `GET /batch/{batch_id}/keywords`
2. `error_message` 필드 확인
3. 해당 키워드만 별도로 `/products/collect`로 재수집

---

## API 문서

상세한 API 스펙은 Swagger 문서 참조:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

---

## 예시 시나리오

### 시나리오 1: 신상품 모니터링

```csv
keyword
갤럭시 S24
아이폰 16
맥북 M3
```

**목적**: 신제품 출시 시 가격 정보 수집
**예상 시간**: 약 9분

### 시나리오 2: 카테고리별 수집

```csv
keyword
# 스마트폰
갤럭시 S24
아이폰 15 프로
샤오미 14

# 노트북
맥북 프로
LG 그램
삼성 갤럭시북

# 이어폰
에어팟 프로
갤럭시 버즈
소니 WF-1000XM5
```

**목적**: 여러 카테고리 제품 일괄 수집
**예상 시간**: 약 27분

---

## MVP 버전 제한사항

현재 MVP 버전에서는 다음 기능이 제외되어 있습니다:

- ❌ 일시중지/재개 기능
- ❌ WebSocket 실시간 업데이트
- ❌ 배치 삭제/취소 기능
- ❌ 프론트엔드 UI (API만 제공)
- ❌ 수집 개수 커스터마이징 (1000개 고정)

이러한 기능은 v2에서 추가될 예정입니다.

---

**문서 버전**: 1.0
**최종 수정일**: 2025-01-11
**작성자**: Claude Code
