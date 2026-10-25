# rhino-phase-plan

Rhino 8 모델에서 **Yellow-Red(Gelb-Rot) 철거·신축 평면**을 책 형식으로 자동으로 뽑는 Claude Code 스킬.
(Claude Code skill that draws Yellow-Red renovation plans from a Rhino 8 model: black = existing, yellow = demolition, red = new;
book layout as found | demolition / as built | addition, vector PDF and layered Illustrator .ai.)

- 층마다 한 장, 네 칸: **as found**(전도면, 검정) · **demolition**(철거 노랑) / **as built**(현도면, 검정) · **addition**(신축 빨강)
- 네 칸·모든 층이 같은 자리 → 겹쳐 비교. 글자는 위 머리 줄에만 (그림 칸에 글자 없음)
- 잘린 면 꽉 채움, 보이는 선은 HiddenLineDrawing 으로 숨은선 처리한 **벡터** → PDF 도 벡터
- 노랑·빨강 칸 바탕 = 기존 벽 회색 점선 윤곽 (옥상 난간 같은 보이는 큰 부재 포함, 위에 가린 것 제외)
- **일러스트레이터 .ai**: 칸 › 종류(over·thin·cut·seen·ghost) 레이어, 채움 = 복합 경로, 파선·점선 유지
- 단계 표시는 모델에서: UserText `phase` = old/demo/new, 또는 레이어 이름에 '철거'·'신축'

## 필요한 것
- Windows + **Rhino 8** (Python 3), Rhino MCP(`run_python`) 또는 ScriptEditor
- **rhino-section-layout** 스킬 (`scripts/section_layout.py` 를 먼저 exec — 재질 판정·블록·출력색을 함께 씀):
  https://github.com/khjjude030609-beep/rhino-section-layout
- (선택) Adobe Illustrator — .jsx 를 COM 으로 돌려 .ai 저장 (`scripts/run_jsx.ps1`), 없으면 일러 스크립트 메뉴로 실행

## 설치
이 폴더를 `~/.claude/skills/rhino-phase-plan` 에, rhino-section-layout 을 `~/.claude/skills/rhino-section-layout` 에 둔다.
사용법·도면 규칙·CFG·함정은 [SKILL.md](SKILL.md).

## 빠른 예
```python
SK = r'C:\Users\<you>\.claude\skills'
exec(open(SK + r'\rhino-section-layout\scripts\section_layout.py', encoding='utf-8').read())
exec(open(SK + r'\rhino-phase-plan\scripts\phase_plan.py', encoding='utf-8').read())
CFG = dict(page='YR', scale=200, project='My building', pdf=r'D:\out\plans.pdf',
           floors=[dict(name='1F', label='1F plan', level=0, cut=1200),
                   dict(name='2F', label='2F plan', level=4060, cut=6000)])
phase_report(); build_phase(CFG); export_phase(CFG)
```
```powershell
powershell -File scripts\run_jsx.ps1 D:\out\plans_1F.jsx illustrator
```
