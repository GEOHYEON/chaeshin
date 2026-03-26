# Contributing to Chaeshin

채신(Chaeshin) 프로젝트에 기여해주셔서 감사합니다!

## 시작하기

### 개발 환경 설정

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # 권장
# 또는: pip install -e ".[dev]"
```

### 테스트 실행

```bash
make test          # 전체 테스트
make test-unit     # 유닛 테스트만
make lint          # 린팅
```

## 기여 방법

### 이슈 생성

- **버그 리포트**: 재현 단계를 포함해주세요
- **기능 제안**: 유스케이스와 기대 동작을 설명해주세요
- **질문**: Discussion 탭을 이용해주세요

### Pull Request

1. 이슈를 먼저 생성하거나, 기존 이슈에 댓글로 작업 의사를 알려주세요
2. Fork 후 브랜치를 생성하세요:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. 변경사항을 커밋하세요:
   ```bash
   git commit -m "feat: add new tool type support"
   ```
4. 테스트를 추가하고 통과하는지 확인하세요:
   ```bash
   make test
   ```
5. PR을 생성하세요

### 커밋 메시지 규칙

[Conventional Commits](https://www.conventionalcommits.org/) 형식을 따릅니다:

- `feat:` 새 기능
- `fix:` 버그 수정
- `docs:` 문서 변경
- `test:` 테스트 추가/수정
- `refactor:` 코드 리팩토링
- `chore:` 빌드/설정 변경

### 예시

```
feat: add VectorDB adapter for CaseStore
fix: prevent infinite loop in graph executor
docs: add health detective example
test: add edge condition evaluation tests
```

## 코드 스타일

- Python 3.10+
- Type hints 사용
- Docstring은 한국어 또는 영어 (혼용 가능)
- 함수/클래스명은 영어, 주석/문서는 한국어 OK

## 기여하기 좋은 영역

### 초보자 환영 (good first issue)

- 새 도메인 예제 추가 (건강, 교육, 코딩 등)
- 문서 번역 (한국어 ↔ 영어)
- 테스트 커버리지 확대

### 중급

- CaseStore VectorDB 어댑터 (Weaviate, Pinecone, ChromaDB)
- 새로운 condition 평가 연산자 추가
- 환자 TODO UI 컴포넌트 (React)

### 고급

- LLM 기반 그래프 리플래닝 최적화
- 분산 그래프 실행 (여러 노드 병렬 실행)
- 벤치마크 프레임워크 구축

## 행동 강령

모든 참여자는 서로를 존중하고 건설적인 대화를 유지해주세요.
차별, 괴롭힘, 비하 발언은 허용되지 않습니다.

## 질문이 있으시면

- GitHub Issues
- GitHub Discussions
- contact@geohyeon.com
