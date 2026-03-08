# 어니스트서울 나석키 전환 요청 시스템

매장 직원이 스마트폰으로 거래를 등록하면 아지트에 자동 포스팅되고,
안은정 팀장이 관리자 대시보드에서 월별 조회 후 PDF를 출력하는 웹앱입니다.

---

## 디렉토리 구조

```
honest-seoul-app/
├── app.py                  # Flask 백엔드
├── requirements.txt        # Python 패키지
├── templates/
│   ├── store.html          # 매장 직원용 모바일 폼
│   ├── manager.html        # 안은정 팀장 관리자 대시보드
│   └── print_pdf.html      # PDF 출력 템플릿
├── uploads/                # 업로드된 이미지 저장 (자동 생성)
└── transactions.db         # SQLite DB (자동 생성)
```

---

## 배포 (Render.com 무료 플랜)

### 1단계 — GitHub 레포 만들기

1. [github.com](https://github.com) 에서 새 레포 생성 (예: `honest-seoul-app`)
2. 이 폴더 전체를 레포에 올리기:
   ```bash
   cd honest-seoul-app
   git init
   git add .
   git commit -m "init"
   git remote add origin https://github.com/YOUR_ID/honest-seoul-app.git
   git push -u origin main
   ```

### 2단계 — Render.com 배포

1. [render.com](https://render.com) 로그인 → **New → Web Service**
2. GitHub 레포 연결
3. 다음 설정 입력:

| 항목 | 값 |
|------|----|
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app` |
| **Instance Type** | Free |

4. **Environment Variables** 탭에서 환경변수 추가:

| 키 | 값 |
|----|----|
| `AGIT_WEBHOOK_URL` | 아지트 웹훅 URL (아래 참조) |

5. **Deploy** 클릭 → 완료 후 URL 발급 (예: `https://honest-seoul-app.onrender.com`)

> ⚠️ **주의:** Render 무료 플랜은 15분 비활성 시 서버가 슬립합니다.
> 첫 요청 시 30~60초 걸릴 수 있습니다.
> 업로드 파일(`uploads/`)과 DB(`transactions.db`)는 **서버 재시작 시 초기화**됩니다.
> 데이터 영속성이 필요하면 유료 플랜 또는 외부 스토리지(S3 등) 연동 필요.

---

## 아지트 웹훅 URL 얻는 방법

1. 아지트 그룹 페이지 접속
2. 우측 상단 **설정(⚙)** → **연동** 탭
3. **수신 웹훅(Incoming Webhook)** → **추가**
4. 이름 입력 후 **저장** → URL 복사
5. Render 환경변수 `AGIT_WEBHOOK_URL`에 붙여넣기

---

## 사용 방법

### 매장 직원 (스마트폰)

접속 URL: `https://honest-seoul-app.onrender.com/store`

1. 거래일자 선택 (캘린더 UI)
2. 점포 선택
3. 고객명·주문번호 입력 (선택)
4. 다이아나석 금액·세팅비 입력 → 합계 자동 계산
5. 감정원·등급 입력
6. 감정서 이미지(또는 PDF) 첨부 (귀걸이는 2개)
7. 영수증·주문서 이미지 첨부
8. 팀장에게 전달할 메모 입력 (선택, PDF에 미포함)
9. **거래 등록** 버튼 → 아지트 자동 포스팅 + 서버 저장

### 안은정 팀장 (PC)

접속 URL: `https://honest-seoul-app.onrender.com/manager`

1. 상단 월 필터로 원하는 월 선택
2. 거래 목록 확인 (썸네일, 메모 확인 가능)
3. 수정이 필요한 경우 ✏️ 버튼으로 값 편집
4. 인쇄할 거래 체크박스 선택 (전체선택 가능)
5. **선택 PDF 출력** 버튼 → 새 탭에서 문서 생성
6. 화면의 **🖨 PDF로 저장** 버튼 클릭
7. Chrome 인쇄 창: 대상 = "PDF로 저장", 용지 = A4, 여백 = 없음

---

## 로컬 개발 실행

```bash
# 패키지 설치
pip install -r requirements.txt

# 서버 실행 (http://localhost:5000)
python app.py
```

환경변수 없이도 실행 가능 (아지트 웹훅은 URL 없으면 자동 스킵).

---

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/transactions` | 거래 등록 (multipart/form-data) |
| `GET` | `/api/transactions?month=2026-03` | 거래 목록 조회 |
| `GET` | `/api/transactions/<id>` | 거래 단건 조회 |
| `PATCH` | `/api/transactions/<id>` | 거래 수정 (JSON) |
| `GET` | `/uploads/<filename>` | 업로드 파일 서빙 |

---

## 문의

어니스트서울 — 안은정 팀장 / 010-5543-2437
