# 보안 가이드 (Security Guidelines)

## 중요: 민감한 정보 관리

### .env 파일 보안

이 프로젝트는 민감한 API 키와 데이터베이스 접속 정보를 `.env` 파일에 저장합니다.

**절대로 .env 파일을 Git에 커밋하지 마세요!**

#### 현재 .env 파일 상태 확인
```bash
# .env 파일이 Git에 추가되었는지 확인
git ls-files | grep .env

# 만약 출력이 있다면 (파일이 추적되고 있다면):
git rm --cached .env
git commit -m "Remove .env from repository"
```

#### 안전한 환경 변수 관리

1. **로컬 개발 환경**
   - `.env.example` 파일을 복사하여 `.env` 생성
   - 실제 API 키로 값 채우기
   - `.gitignore`에 `.env` 포함 확인 (이미 포함됨)

2. **운영 환경**
   - 환경 변수 직접 설정 (Docker, Kubernetes Secrets 등)
   - AWS Secrets Manager, Azure Key Vault 등 사용
   - 절대 코드에 하드코딩하지 않기

### API 키 보안

#### 네이버 API 키
- `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`은 절대 공개하지 않기
- API 키가 노출되었다면 즉시 네이버 개발자 센터에서 재발급
- Rate Limiting 설정 확인 (일일 25,000회 제한)

#### MongoDB 접속 정보
- 운영 환경에서는 반드시 인증 활성화
- 강력한 비밀번호 사용
- IP 화이트리스트 설정
- SSL/TLS 연결 사용 권장

### 보안 체크리스트

#### 코드 레벨
- [x] API 키를 환경 변수로 관리
- [x] .env 파일이 .gitignore에 포함됨
- [x] 입력값 검증 (Pydantic 사용)
- [x] SQL Injection 방지 (Beanie ODM 사용)
- [x] 에러 메시지에 민감한 정보 미포함
- [x] HTTPS 사용 (운영 환경에서 필수)

#### 배포 레벨
- [ ] 방화벽 설정 (필요한 포트만 개방)
- [ ] CORS 정책 설정
- [ ] Rate Limiting 구현
- [ ] 로그 관리 (민감한 정보 로깅 금지)
- [ ] 정기적인 의존성 업데이트

### 알려진 보안 이슈

#### 1. MongoDB 공개 노출
**위험도: 높음**

현재 `.env` 파일의 MongoDB URL이 공개 IP를 사용하고 있습니다:
```
MONGODB_URL=mongodb://43.200.172.45:27017/ecommerce_ai
```

**조치사항:**
- MongoDB 인증 활성화 필수
  ```
  MONGODB_URL=mongodb://username:password@43.200.172.45:27017/ecommerce_ai
  ```
- 방화벽에서 신뢰할 수 있는 IP만 허용
- VPN 또는 프라이빗 네트워크 사용 권장
- MongoDB Atlas 같은 관리형 서비스 고려

#### 2. API 서버 공개 노출
**위험도: 중간**

```python
API_HOST=0.0.0.0  # 모든 네트워크 인터페이스에서 접근 가능
```

**조치사항:**
- 운영 환경에서는 리버스 프록시 사용 (Nginx, Caddy)
- HTTPS 강제 적용
- API 인증/인가 시스템 구현 고려

### 의존성 보안

#### 정기적인 업데이트
```bash
# 보안 취약점 확인
pip install safety
safety check

# 의존성 업데이트
pip list --outdated
pip install --upgrade <package-name>
```

#### 현재 의존성 버전 확인
```bash
pip freeze > requirements.txt
```

### 민감한 데이터 로깅 방지

#### 절대 로깅하면 안 되는 정보
- API 키 (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)
- 데이터베이스 비밀번호
- 사용자 개인정보
- 세션 토큰

#### 로깅 시 주의사항
```python
# 나쁜 예
logger.info(f"API Key: {settings.NAVER_CLIENT_SECRET}")

# 좋은 예
logger.info("API 호출 성공")
```

### 보안 사고 대응

#### API 키 노출 시
1. 즉시 API 키 비활성화/재발급
2. Git 히스토리에서 완전 제거
   ```bash
   git filter-branch --force --index-filter \
   "git rm --cached --ignore-unmatch .env" \
   --prune-empty --tag-name-filter cat -- --all
   ```
3. 변경 사항을 강제 푸시
4. 팀원들에게 알림

#### 데이터베이스 침해 시
1. 즉시 MongoDB 접속 차단
2. 로그 분석으로 침해 범위 파악
3. 데이터 백업 및 복구
4. 보안 패치 적용
5. 비밀번호 재설정

### 참고 자료

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [네이버 API 이용 가이드](https://developers.naver.com/docs/common/openapiguide/)
- [MongoDB 보안 체크리스트](https://docs.mongodb.com/manual/administration/security-checklist/)
- [FastAPI 보안 가이드](https://fastapi.tiangolo.com/tutorial/security/)

### 보안 문의

보안 취약점을 발견하셨다면:
- 공개 이슈로 등록하지 마세요
- 이메일로 비공개 보고: security@example.com
