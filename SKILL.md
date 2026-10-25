---
name: rhino-phase-plan
description: Rhino 8 모델에서 Yellow-Red(Gelb-Rot) 평면을 뽑는다 — 검정 = 기존(전도면·현도면), 노랑 = 철거, 빨강 = 신축. 책 형식 4칸(as found | demolition / as built | addition), 층마다 한 장(A1 1:200 등), 네 칸·모든 층 같은 자리, 글자는 위 머리 줄에만. 보이는 선은 숨은선 처리한 벡터(HiddenLineDrawing)라 PDF 도 벡터, 일러스트레이터용 .ai 를 칸·종류별 레이어로 나눠 만듦. "Yellow-Red 평면", "철거·신축 평면", "전도면 현도면", "as found as built demolition addition", "Gelb-Rot", "일러로 레이어 나눠 보내" 같은 요청에 쓴다. rhino-section-layout 스킬과 Rhino MCP(run_python) 필요.
---

# Rhino Yellow-Red 평면 (철거·신축)

스크립트: 이 스킬 폴더의 `scripts/phase_plan.py`. **rhino-section-layout 스킬의 `scripts/section_layout.py` 를 먼저 exec** 한다
(재질 판정 `kind`, 블록 속 `_leaves`, 표시 모드, 레이어, `remove_page`, 출력색 `plot_style` 을 그대로 씀).

## 쓰는 법

```python
exec(open(r'<rhino-section-layout>\scripts\section_layout.py', encoding='utf-8').read())
exec(open(r'<SKILL_DIR>\scripts\phase_plan.py', encoding='utf-8').read())
CFG = dict(page='YR', paper=(841.0, 594.0), scale=200, project='Project name',
           pdf=r'D:\...\plans.pdf',
           hide=['CAD', 'Site'],                                    # 잘림·선에서 뺄 레이어(하위 포함)
           floors=[dict(name='1F', label='1F plan', level=0, cut=1200, depth=1900),
                   dict(name='2F', label='2F plan', level=4060, cut=6000)])
phase_report()       # 단계별 객체 수 — 철거·신축이 제대로 잡혔는지 먼저 확인
build_phase(CFG)     # 층마다 페이지 'YR 1F', 'YR 2F' (같은 이름 있으면 지우고 다시) — 실제 모델 4만 개에 약 15초
export_phase(CFG)    # PDF 한 파일(층 = 쪽, Idle 출력 → pdf 옆 _export_log.txt) + 층마다 '<pdf>_<층>.jsx'
```
일러스트레이터 .ai (Windows, COM): `powershell -File <SKILL_DIR>\scripts\run_jsx.ps1 <jsx> illustrator`
→ `ok ….ai paths N fills N texts N layers 5`. COM 이 없으면 일러 **파일 > 스크립트 > 기타 스크립트**로 .jsx 실행.

## 단계 표시 (모델에서)
`phase(ob)` 순서: 객체 UserText **`phase` = old / demo / new** → 레이어 경로에 **'철거'·demo** = 철거, **'신축'·new** = 신축 → 나머지 = 기존.
- 신축: 레이어 이름에 '신축'(예 `계획::신축::E2 사무::외벽`). 재질 낱말은 rhino-section-layout `kind()` 표를 따름 (벽·콘크리트·강재 = 채움, 유리 = 선)
- 철거: 기존 부재에 `set_phase(objs, 'demo')` 또는 Rhino 속성 패널 UserText. 벽 일부만 철거면 부재를 나눠서 표시
- 판(슬래브·지붕·덧지붕·캐노피) 레이어 이름이면 자른 높이 위 3.5 m 안에서 머리 위 파선 (`PH_SLAB`, `PH_STYLE['over_up']`)

## 도면 규칙 (책 형식 = Gelb-Rot / SIA 400 관례)
- 위 줄 = **as found**(전도면: 기존 + 철거될 것, 검정) | **demolition**(철거 부분 노랑 채움, 나머지 회색 점선 윤곽)
- 아래 줄 = **as built**(현도면: 남는 기존 + 신축, 검정) | **addition**(신축 빨강, 나머지 회색 점선)
- 네 칸·모든 층이 같은 자리 (카메라 x 하나, 위 줄 = 전 상태 범위 가운데, 아래 줄 = 후 상태 범위 가운데) → 겹쳐 비교
- 잘린 면 = 꽉 채움(해치·외곽선 없음, 1:200 관례). 창틀·목재·재료 모름 = 가는 선. 450 mm 미만 강재 단면 = 외곽 사각형 채움
- 보이는 선 = 자른 높이 ~ 그 층 바닥 −30 사이를 **HiddenLineDrawing** 으로 숨은선 처리한 벡터 회색 선 (전도면·현도면 칸)
- 점선 바탕 = 잘린 벽 윤곽 합집합 + 그 층 바닥 위에서 시작하는 2 m² 넘는 기존 부재(옥상 난간·지붕판) 윤곽 — 위 판에 가린 것은 뺌
- 글자는 위 여백 머리 줄에만: 제목(굵게) · 층, 축척 · 방위(+Y = 북 가정) · `as found ↑ as built ↓` / `demolition ↑ addition ↓`
- 검정 (25,25,25) · 노랑 (242,178,0) · 빨강 (226,34,40) — `PH_COL`. 선 굵기·파선 = `PH_STYLE`, 점선 바탕 = `PH_GHOST`, 머리 줄 글 = `PH_LABEL`

## 일러스트레이터 레이어
대지 = 페이지 크기(mm). 위 → 아래: `0 head` / `4 addition` / `3 as built` / `2 demolition` / `1 as found`,
칸마다 하위 `over`(머리 위 파선) · `thin`(창틀 등 가는 선) · `cut`(채움) · `seen`(보이는 선) · `ghost`(점선 바탕).
채움 = 복합 경로(홀짝, 구멍 유지), 파선·점선 = 선 대시, 글자 = 점 글자(Arial, Rhino 글 상자 왼쪽·세로 가운데에 맞춤).

## CFG
- `page` 페이지 이름 앞부분, `paper` (841, 594) = A1 가로, `scale` 200, `project` 머리 줄 제목, `pdf` 출력 경로
- `floors`: `name`(페이지·파일 꼬리), `label`(머리 줄), `level` 그 층 바닥 mm, `cut` 자를 높이 mm (보통 바닥 + 1,200),
  `depth` 깊이판까지 거리 (기본 = cut − level + 30 → 바닥 밑 장선·보 숨김. 1층 마당·외부 계단을 보이려면 더 크게)
- `hide` 레이어 목록, `vector` 기본 True (False = Technical 디테일 + 래스터 PDF), `raster`·`dpi` PDF 방식, `row_gap` 줄 사이 25 mm, `head`·`head_y`·`head_h`·`margin` 머리 줄 자리
- 레이아웃은 `PH_PANELS` (칸 이름·단·줄), 칸 안 레이어 순서는 `PH_KINDS`

## 함정 (겪은 것)
- **벡터 PDF + Technical 디테일 = 숨은선이 비침** (지붕판 밑 벽·벽머리 링이 위에서 보임). 그래서 기본 = 디테일 비우고 HLD 벡터 선
- HLD: 디테일 뷰포트 그대로 쓰면 **near 가 수백 m 라 전부 잘려 0개** → `SetFrustumNearFar(1, 1e8)`
- HLD `Flatten` 출력 = **카메라 표적이 원점인 좌표** → `PlaneToPlane(WorldXY, 카메라 평면)` 으로 되돌림
- HLD 자르기 평면 법선 = **지워지는 쪽** (Rhino 자르기 평면 객체와 반대)
- 실루엣(`Silhouette.Compute`)엔 숨은선 처리가 없음 → 윗면 안쪽 점에서 위로 선을 쏴 더 높은 판에 막히면 뺌 (상자 중심·꼭짓점으로 하면 오판)
- Rhino 기본 `.ai` 내보내기는 **해치(채움)가 빠지고 축척이 틀리고(1 mm → 12.9 pt) 유니코드 글자가 깨짐** → JSX 로 일러에서 직접 만듦
- 페이지의 디테일 목록 순서 ≠ 만든 순서 → 위치로 찾음. 같은 이름 페이지는 `build_phase` 가 먼저 지움
- 출력 PDF 는 Idle 핸들러 (MCP 300초 제한). 문서는 저장 안 해도 됨 (출력색은 쓰는 동안만 바뀜)
