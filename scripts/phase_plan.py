# -*- coding: utf-8 -*-
r"""
Yellow-Red 평면 (Gelb-Rot / SIA 400 관례): 검정 = 기존 · 노랑 = 철거 · 빨강 = 신축 — 책 형식 4칸, 층마다 한 장.
  위 줄  = as found (전도면, 검정)   | demolition (전도면의 철거 부분 노랑, 나머지 회색 점선)
  아래 줄 = as built (현도면, 검정)  | addition   (현도면의 신축 부분 빨강, 나머지 회색 점선)
  네 칸·모든 층 같은 자리(겹쳐 보기). 글자는 위 여백 머리 줄에만 (그림 칸에 글자 없음).
rhino-section-layout 스킬의 section_layout.py 를 먼저 exec 한 뒤 exec (kind·_leaves·_mode·_layer·_model_view·remove_page 재사용).
    exec(open(r'<rhino-section-layout>\scripts\section_layout.py', encoding='utf-8').read())
    exec(open(r'<이 스킬>\scripts\phase_plan.py', encoding='utf-8').read())
    CFG = dict(page='YR', paper=(841.0, 594.0), scale=200, project='Project', pdf=r'D:\...\plans.pdf',
               floors=[dict(name='1F', label='1F plan', level=0, cut=1200),
                       dict(name='2F', label='2F plan', level=4060, cut=6000)],
               hide=['CAD', 'Site'])
    phase_report()          # 단계별 객체 수 확인
    build_phase(CFG)        # 층마다 페이지 'YR 1F' … (기존 같은 이름 페이지는 지우고 다시)
    export_phase(CFG)       # PDF 한 파일(층 = 쪽) + 층마다 일러스트레이터용 .jsx (run_jsx.ps1 로 .ai 만들기)
단계 phase(ob): UserText 'phase' = old/demo/new → 레이어 경로에 '철거'·'demo' = DEMO, '신축'·'new' = NEW → 나머지 OLD
"""
import Rhino, System, math, collections, re, os, time, json
import scriptcontext as sc
from Rhino.Geometry import Point3d, Point2d, Vector3d, Plane, BoundingBox, Transform
if 'kind' not in globals() or '_leaves' not in globals():
    raise RuntimeError('먼저 rhino-section-layout 의 scripts/section_layout.py 를 exec 하세요 (kind·_leaves 사용)')

PH_COL = dict(OLD=(25, 25, 25), DEMO=(242, 178, 0), NEW=(226, 34, 40))      # 검정은 (0,0,0) 대신 25 — 순수 검정 면이 래스터에서 뒤집히는 일 피함
PH_STYLE = dict(thin_w=0.09, line_w=0.25, seen_w=0.13, over_w=0.18, seen_rgb=(70, 70, 70),
                over_up=3500.0, dash=(1.2, 0.8), box_under=450.0)
PH_FILL = {'BRICK', 'CONC', 'STONE', 'MORTAR', 'SOLID', 'INSUL'}            # 꽉 채움. WOOD·WHITE = 가는 외곽선, EARTH = 안 그림
PH_SLAB = ('슬래브', '바닥판', '지붕', '캐노피', 'slab', 'roof', 'canopy')    # 머리 위 파선으로 그릴 판 레이어 낱말
PH_GHOST = dict(rgb=(150, 150, 150), w=0.13, dash=(0.35, 0.45))            # 노랑·빨강 칸 바탕 점선
PH_SEEN = dict(start=200.0, area=2.0e6)                                     # 점선 바탕 '보임' 기존 부재: 그 층 바닥 +100 위에서 시작, 평면 범위 2 m² 이상
PH_LABEL = dict(found='as found', built='as built', demo='demolition', add='addition')
PH_PANELS = (('found', 0, 0, '1 as found'), ('demo', 1, 0, '2 demolition'), ('built', 0, 1, '3 as built'), ('add', 1, 1, '4 addition'))  # (칸, 단, 줄, 레이어)
PH_KINDS = ('ghost', 'seen', 'cut', 'thin', 'over')                         # 칸 안 레이어 순서 (아래 → 위)

# ---------------- 단계 ----------------
def phase(ob):
    a = ob.Attributes; v = (a.GetUserString('phase') or '').strip().lower()
    if v in ('old', 'demo', 'new'): return v.upper()
    p = d.Layers[a.LayerIndex].FullPath
    if '철거' in p or re.search(r'(?i)(?<![a-z])demo', p): return 'DEMO'
    if '신축' in p or re.search(r'(?i)(?<![a-z])new(?![a-z])', p): return 'NEW'
    return 'OLD'

def set_phase(obs, ph):
    """객체(또는 Guid) 목록에 UserText phase 달기. ph = 'old'|'demo'|'new'|None(지움)"""
    n = 0
    for ob in obs:
        ob = d.Objects.FindId(ob) if isinstance(ob, System.Guid) else ob
        if ob is None: continue
        a = ob.Attributes.Duplicate(); a.SetUserString('phase', ph.lower() if ph else None); d.Objects.ModifyAttributes(ob, a, True); n += 1
    return n

def phase_report():
    c = collections.Counter(phase(ob) for ob in d.Objects if ob.Attributes.Space == Rhino.DocObjects.ActiveSpace.ModelSpace)
    print('phase', dict(c)); return dict(c)

# ---------------- 자르기·윤곽 ----------------
def _hidden_layers(names):
    out = set()
    for i in range(d.Layers.Count):
        L_ = d.Layers[i]
        if L_.IsDeleted: continue
        if any(L_.FullPath == n or L_.FullPath.startswith(n + '::') for n in names) or L_.FullPath.startswith(TAG): out.add(i)
    return out

def _brep(g):
    if isinstance(g, (Rhino.Geometry.Extrusion, Rhino.Geometry.SubD)): return g.ToBrep()
    return g if isinstance(g, Rhino.Geometry.Brep) else None

def _leaf_geoms(top):
    for g, X, lp, el in _leaves(top):
        if X is not None: g = g.Duplicate(); g.Transform(X)
        yield g, lp, el

def _is_glass(lp): return '유리' in lp or 'glass' in lp.lower()

def _cut_phase(z, skip):
    """z 높이 수평 절단 → {(단계, 'fill'|'thin'|'line'): [객체마다 곡선 목록]} (모델 좌표)"""
    tol = d.ModelAbsoluteTolerance; cut = Plane(Point3d(0, 0, z), Vector3d.ZAxis)
    out = collections.defaultdict(list)
    for top in list(d.Objects):
        a = top.Attributes
        if a.Space != Rhino.DocObjects.ActiveSpace.ModelSpace or a.LayerIndex in skip: continue
        try: b0 = top.Geometry.GetBoundingBox(False)
        except: continue
        if not (b0.Min.Z < z < b0.Max.Z): continue
        ph = phase(top)
        for g, lp, el in _leaf_geoms(top):
            try: b = g.GetBoundingBox(True)
            except: continue
            if not (b.Min.Z < z < b.Max.Z): continue
            k = kind(lp, el); glass = k is None and _is_glass(lp)
            if k == 'EARTH' or (k is None and not (glass and ph != 'OLD')): continue
            br = _brep(g); cs = []
            if br is not None:
                ok, crv, pts = Rhino.Geometry.Intersect.Intersection.BrepPlane(br, cut, tol)
                if ok and crv: cs = list(Rhino.Geometry.Curve.JoinCurves(crv, tol * 10))
                closed = br.IsSolid
            elif isinstance(g, Rhino.Geometry.Mesh):
                pl = Rhino.Geometry.Intersect.Intersection.MeshPlane(g, cut)
                if pl: cs = [p.ToNurbsCurve() for p in pl]
                closed = g.IsClosed
            else: continue
            if not cs: continue
            if not closed:                                    # 열린 면(커튼월 유리 등): 철거·신축만 선으로
                if ph != 'OLD': out[(ph, 'line')].append(cs)
                continue
            cs = [c for c in cs if c.IsClosed]
            if not cs: continue
            mode = 'fill' if (k in PH_FILL and not glass) else 'thin'
            if k == 'SOLID' and mode == 'fill':               # 작은 강재 단면(H형강 등): 플랜지가 종이에서 머리카락 → 외곽 사각형 채움 (1:200 관례)
                cb = BoundingBox.Empty
                for c in cs: cb.Union(c.GetBoundingBox(True))
                if max(cb.Max.X - cb.Min.X, cb.Max.Y - cb.Min.Y) < PH_STYLE['box_under']:
                    cs = [Rhino.Geometry.PolylineCurve([Point3d(cb.Min.X, cb.Min.Y, z), Point3d(cb.Max.X, cb.Min.Y, z), Point3d(cb.Max.X, cb.Max.Y, z),
                                                        Point3d(cb.Min.X, cb.Max.Y, z), Point3d(cb.Min.X, cb.Min.Y, z)])]
            out[(ph, mode)].append(cs)
    return out

def _sil(g):
    """위에서 본 바깥 윤곽 (모델 좌표, 3D 곡선)"""
    gg = _brep(g) or g
    try:
        S = Rhino.Geometry.Silhouette.Compute(gg, Rhino.Geometry.SilhouetteType.Boundary, Vector3d(0, 0, -1), d.ModelAbsoluteTolerance, math.radians(1))
        return [s.Curve for s in S or [] if s.Curve is not None]
    except Exception:
        return []

def _seen_over(z, depth, skip):
    """철거·신축: 아래 보임(z−depth ~ z) · 머리 위(판 레이어, over_up 안) 윤곽 / 기존: 점선 바탕용 큰 '보임' 부재 → {(단계,'seen'|'over'): [곡선]}"""
    out = collections.defaultdict(list); up = PH_STYLE['over_up']; cand, cover = [], []
    for top in list(d.Objects):
        a = top.Attributes
        if a.Space != Rhino.DocObjects.ActiveSpace.ModelSpace or a.LayerIndex in skip: continue
        ph = phase(top)
        try: b = top.Geometry.GetBoundingBox(True)
        except: continue
        if ph == 'OLD':
            big = (b.Max.X - b.Min.X) * (b.Max.Y - b.Min.Y) >= PH_SEEN['area']
            if big and b.Max.Z < z: cover.append((b, top))
            if big and b.Min.Z >= z - depth + PH_SEEN['start'] and b.Max.Z < z: cand.append((top, b))
            continue
        lp = d.Layers[a.LayerIndex].FullPath.split('::')[-1].lower()
        if z - depth < b.Max.Z < z: what = 'seen'
        elif z < b.Min.Z <= z + up and any(w in lp for w in PH_SLAB): what = 'over'
        else: continue
        for g, lp2, el in _leaf_geoms(top):
            if kind(lp2, el) == 'EARTH': continue
            out[(ph, what)] += _sil(g)
    tol = d.ModelAbsoluteTolerance
    def covered(top, b):
        """윗면 안쪽 점들에서 자른 높이까지 수직선 → 더 높은 큰 판에 다 막히면 안 보임 (지붕판 밑 부재가 비치지 않게).
        꼭짓점은 옆 부재 면과 맞닿아 빗나가고, 상자 중심은 곡선 캐노피처럼 속 빈 모양에서 틀림"""
        qs = [(q, ob) for q, ob in cover if ob.Id != top.Id and q.Min.Z >= b.Max.Z - 10]
        if not qs: return False
        br = _brep(top.Geometry); vs = []
        if br is not None:
            ups = []
            for f in br.Faces:
                ok, fr = f.FrameAt(f.Domain(0).Mid, f.Domain(1).Mid)
                if ok and (fr.ZAxis.Z if not f.OrientationIsReversed else -fr.ZAxis.Z) > 0.9:
                    am = Rhino.Geometry.AreaMassProperties.Compute(f.DuplicateFace(False)); ups.append((am.Area if am else 0, f))
            for _, f in sorted(ups, key=lambda t: -t[0])[:3]:
                du, dv = f.Domain(0), f.Domain(1)
                for su, sv in ((0.5, 0.5), (0.3, 0.5), (0.7, 0.5), (0.5, 0.3), (0.5, 0.7), (0.15, 0.5), (0.85, 0.5)):
                    uu, vv = du.ParameterAt(su), dv.ParameterAt(sv)
                    if f.IsPointOnFace(uu, vv) == Rhino.Geometry.PointFaceRelation.Interior: vs.append(f.PointAt(uu, vv)); break
        if not vs: vs = [b.Center]
        for p in vs:
            ln = Rhino.Geometry.LineCurve(Point3d(p.X, p.Y, p.Z + 5), Point3d(p.X, p.Y, z)); hit = False
            for q, ob in qs:
                if not (q.Min.X <= p.X <= q.Max.X and q.Min.Y <= p.Y <= q.Max.Y): continue
                qb = _brep(ob.Geometry)
                if qb is None: continue
                ok, ov, ip = Rhino.Geometry.Intersect.Intersection.CurveBrep(ln, qb, tol)
                if ok and ip is not None and len(ip) > 0: hit = True; break
            if not hit: return False
        return True
    for top, b in cand:
        if covered(top, b): continue
        for g, lp2, el in _leaf_geoms(top):
            if kind(lp2, el) not in (None, 'EARTH'): out[('OLD', 'seen')] += _sil(g)
    return out

def _hld(det, z, depth, skip, allow, area):
    """보이는 선(벡터) = HiddenLineDrawing: 자른 높이 위·깊이판 아래를 자르고 숨은선 처리. allow = 넣을 단계들, area = 모델 XY 범위.
    HLD 자르기 평면 법선은 '지워지는 쪽' (Rhino 자르기 평면 객체와 반대, 시험으로 확인)"""
    P = Rhino.Geometry.HiddenLineDrawingParameters()
    P.AbsoluteTolerance = d.ModelAbsoluteTolerance; P.IncludeTangentEdges = False; P.IncludeHiddenCurves = False
    vpi = Rhino.DocObjects.ViewportInfo(det.Viewport)
    vpi.SetFrustumNearFar(1.0, 1.0e8)                         # 디테일 뷰포트의 near(수백 m)가 카메라 거리보다 커서 전부 잘림(겪음) → 넓힘
    P.SetViewport(vpi); P.Flatten = True
    n = 0
    for top in list(d.Objects):
        a = top.Attributes
        if a.Space != Rhino.DocObjects.ActiveSpace.ModelSpace or a.LayerIndex in skip or phase(top) not in allow: continue
        try: b = top.Geometry.GetBoundingBox(True)
        except: continue
        if b.Max.Z < z - depth or b.Min.Z > z or b.Max.X < area.Min.X or b.Min.X > area.Max.X or b.Max.Y < area.Min.Y or b.Min.Y > area.Max.Y: continue
        for g, X, lp, el in _leaves(top):
            k = kind(lp, el)
            if k == 'EARTH' or (k is None and not _is_glass(lp)): continue
            if isinstance(g, (Rhino.Geometry.Curve, Rhino.Geometry.Point, Rhino.Geometry.TextEntity)): continue
            if P.AddGeometry(g, X if X is not None else Transform.Identity, None): n += 1
    P.AddClippingPlane(Plane(Point3d(0, 0, z), Vector3d(0, 0, 1)))
    P.AddClippingPlane(Plane(Point3d(0, 0, z - depth), Vector3d(0, 0, -1)))
    h = Rhino.Geometry.HiddenLineDrawing.Compute(P, True)
    if h is None: return []
    vis = Rhino.Geometry.HiddenLineDrawingSegment.Visibility.Visible
    segs = [s.CurveGeometry.DuplicateCurve() for s in h.Segments if s.SegmentVisibility == vis and s.CurveGeometry is not None]
    out = list(Rhino.Geometry.Curve.JoinCurves(segs, d.ModelAbsoluteTolerance)) if segs else []
    back = Transform.PlaneToPlane(Plane.WorldXY, Plane(vpi.TargetPoint, vpi.CameraX, vpi.CameraY))   # 평탄화 출력 = 카메라 표적 원점 좌표(겪음) → 월드
    for c in out: c.Transform(back)
    return out

def _linetype(name, dash):
    for i in range(d.Linetypes.Count):
        if d.Linetypes[i].Name == name and not d.Linetypes[i].IsDeleted: return i
    lt = Rhino.DocObjects.Linetype(); lt.Name = name
    lt.AppendSegment(dash[0], True); lt.AppendSegment(dash[1], False)
    return d.Linetypes.Add(lt)

def _plane_of(c): return Plane(Point3d(0, 0, c.PointAtStart.Z), Vector3d.ZAxis)

def _union_outline(groups):
    """객체마다 고리 묶음 → 바깥 고리 합집합 + 구멍 고리 (점선 바탕용, 이음매 없는 벽 윤곽)"""
    tol = d.ModelAbsoluteTolerance; IN = Rhino.Geometry.PointContainment.Inside; outs, holes = [], []
    for cs in groups:
        for c in cs:
            n_in = sum(1 for e in cs if e is not c and e.Contains(c.PointAtStart, _plane_of(e), tol) == IN)
            (holes if n_in % 2 else outs).append(c)
    try:
        u = Rhino.Geometry.Curve.CreateBooleanUnion(outs, tol)
        if u and len(u) > 0: outs = list(u)
    except Exception: pass
    return outs + holes

def _bb_curves(bb, groups):
    for cs in groups:
        for c in (cs if isinstance(cs, list) else [cs]): bb.Union(c.GetBoundingBox(True))

# ---------------- 페이지 ----------------
def _detail(page, rect, z, depth, tgt, scale, dm, ca, skip, hide=(), empty=False):
    det = page.AddDetailView('ph', Point2d(rect[0], rect[1]), Point2d(rect[2], rect[3]), Rhino.Display.DefinedViewportProjection.Top)
    vp = det.Viewport; vp.DisplayMode = dm; t = Point3d(tgt.X, tgt.Y, z)
    vp.SetCameraLocations(t, t + Vector3d(0, 0, 50000)); vp.CameraUp = Vector3d(0, 1, 0)
    det.CommitViewportChanges(); det = d.Objects.FindId(det.Id)
    det.DetailGeometry.SetScale(scale, d.ModelUnitSystem, 1, d.PageUnitSystem)
    det.DetailGeometry.IsProjectionLocked = True; det.CommitChanges(); det = d.Objects.FindId(det.Id)
    da = det.Attributes.Duplicate(); da.PlotWeightSource = Rhino.DocObjects.ObjectPlotWeightSource.PlotWeightFromObject; da.PlotWeight = -1
    d.Objects.ModifyAttributes(det, da, True); det = d.Objects.FindId(det.Id)   # 디테일 테두리 출력 안 함
    vid = det.Viewport.Id
    if empty:                                                 # 모델은 안 보임 (전부 페이지 공간에서 그림)
        for i in range(d.Layers.Count):
            if not d.Layers[i].IsDeleted: d.Layers[i].SetPerViewportVisible(vid, False)
        return det
    o = Point3d(0, 0, z); vdir = Vector3d(0, 0, -1)
    d.Objects.AddClippingPlane(Plane(o, vdir), 1e6, 1e6, [vid], ca)
    d.Objects.AddClippingPlane(Plane(o + vdir * depth, -vdir), 1e6, 1e6, [vid], ca)
    for i in skip:
        if not d.Layers[i].FullPath.startswith(TAG): d.Layers[i].SetPerViewportVisible(vid, False)
    for ob in hide:
        a = ob.Attributes.Duplicate(); a.AddHideInDetailOverride(det.Id); d.Objects.ModifyAttributes(ob, a, True)
    return d.Objects.FindId(det.Id)

def build_phase(cfg):
    """층마다 페이지 cfg['page'] + ' ' + floor name. 모든 층·칸 카메라 x 같음, 위 줄 = 전 상태 범위, 아래 줄 = 후 상태 범위.
    cfg['vector'] (기본 True): 보이는 선을 HLD 벡터로 → PDF 벡터·일러 편집 가능. False 면 Technical 디테일(래스터 PDF 필요)"""
    st = sc.sticky.setdefault('secl_state', {'layers': {}, 'objs': {}, 'pages': []})
    dm = _mode(cfg.get('display')); _model_view(); vec = cfg.get('vector', True)
    W, H = cfg.get('paper', (841.0, 594.0)); scale = float(cfg.get('scale', 200)); floors = cfg['floors']
    skip = _hidden_layers(cfg.get('hide', []))
    for f in floors: f.setdefault('depth', float(f['cut']) - float(f.get('level', 0)) + 30)   # 깊이판 = 그 층 바닥 −30 (밑 장선·보 숨김)
    bb_pre, bb_post = BoundingBox.Empty, BoundingBox.Empty
    for f in floors:
        f['_cut'] = _cut_phase(float(f['cut']), skip)
        f['_so'] = _seen_over(float(f['cut']), float(f['cut']) - float(f.get('level', 0)) + 100, skip)
        C, S = f['_cut'], f['_so']
        _bb_curves(bb_pre, [cs for k in C if k[0] in ('OLD', 'DEMO') and k[1] == 'fill' for cs in C[k]] + S.get(('DEMO', 'seen'), []))
        _bb_curves(bb_post, [cs for k in C if k[0] in ('OLD', 'NEW') and k[1] == 'fill' for cs in C[k]] + S.get(('NEW', 'seen'), []) + S.get(('NEW', 'over'), []))
    x0 = min(bb_pre.Min.X, bb_post.Min.X); x1 = max(bb_pre.Max.X, bb_post.Max.X); xc = (x0 + x1) / 2.0
    mw = (x1 - x0) / scale + 16
    hs = [(bb_pre.Max.Y - bb_pre.Min.Y) / scale + 16, (bb_post.Max.Y - bb_post.Min.Y) / scale + 16]
    tg = [Point3d(xc, bb_pre.Center.Y, 0), Point3d(xc, bb_post.Center.Y, 0)]
    area = [BoundingBox(Point3d(x0 - 3000, bb_pre.Min.Y - 3000, -1e6), Point3d(x1 + 3000, bb_pre.Max.Y + 3000, 1e6)),
            BoundingBox(Point3d(x0 - 3000, bb_post.Min.Y - 3000, -1e6), Point3d(x1 + 3000, bb_post.Max.Y + 3000, 1e6))]
    gap = cfg.get('row_gap', 25.0); top, bot = H - cfg.get('head', 40.0), 15.0
    y_top = top - ((top - bot) - (hs[0] + gap + hs[1])) / 2.0
    rows = [(y_top - hs[0], y_top), (y_top - hs[0] - gap - hs[1], y_top - hs[0] - gap)]
    cols = [W / 4.0, 3 * W / 4.0]                                        # 책 두 쪽 = 왼쪽 반 · 오른쪽 반 가운데
    lc = _layer(LYR_CLIP); ca = Rhino.DocObjects.ObjectAttributes(); ca.LayerIndex = lc; ca.Space = Rhino.DocObjects.ActiveSpace.ModelSpace
    ms = [ob for ob in d.Objects if ob.Attributes.Space == Rhino.DocObjects.ActiveSpace.ModelSpace]
    hide = dict(found=[ob for ob in ms if phase(ob) == 'NEW'], built=[ob for ob in ms if phase(ob) != 'OLD'])
    allow = dict(found=('OLD', 'DEMO'), built=('OLD',))
    solid = d.HatchPatterns.Find('SOLID', True)
    lts = {'over': (_linetype('PH_파선', PH_STYLE['dash']), PH_STYLE['dash']), 'ghost': (_linetype('PH_점선', PH_GHOST['dash']), PH_GHOST['dash'])}
    G = System.Drawing.Color.FromArgb(*PH_GHOST['rgb']); SEEN = System.Drawing.Color.FromArgb(*PH_STYLE['seen_rgb']); stat = {}
    for f in floors:
        name = cfg['page'] + ' ' + f['name']
        remove_page(name)
        page = d.Views.AddPageView(name, W, H); st['pages'].append(name)
        pid = page.MainViewport.Id; z = float(f['cut']); root = LYR_SEC + '::' + name
        def att(layer, col, w=None, order=0, dash=None):
            x = Rhino.DocObjects.ObjectAttributes(); x.LayerIndex = _layer(root + '::' + layer)
            x.Space = Rhino.DocObjects.ActiveSpace.PageSpace; x.ViewportId = pid
            c = System.Drawing.Color.FromArgb(*PH_COL[col]) if isinstance(col, str) else col
            x.DisplayOrder = order
            x.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject; x.ObjectColor = c
            x.PlotColorSource = Rhino.DocObjects.ObjectPlotColorSource.PlotColorFromObject; x.PlotColor = c
            if w is not None: x.PlotWeightSource = Rhino.DocObjects.ObjectPlotWeightSource.PlotWeightFromObject; x.PlotWeight = w
            if dash is not None:
                x.LinetypeSource = Rhino.DocObjects.ObjectLinetypeSource.LinetypeFromObject; x.LinetypeIndex = lts[dash][0]
                x.SetUserString('ph_dash', '%g,%g' % lts[dash][1])  # 일러 내보내기용 (페이지 mm)
            return x
        C, S = f['_cut'], f['_so']; s = collections.Counter()
        for role, ci, ri, lname in PH_PANELS:
            r0, r1 = rows[ri]; rect = (cols[ci] - mw / 2, r0, cols[ci] + mw / 2, r1)
            empty = vec or role in ('demo', 'add')
            det = _detail(page, rect, z, float(f['depth']), tg[ri], scale, dm, ca, skip, hide.get(role, ()), empty=empty)
            xf = Transform.PlanarProjection(Plane.WorldXY) * det.WorldToPageTransform
            def P(c): q = c.DuplicateCurve(); q.Transform(xf); return q
            def cut_(ph, col):
                for cs in C.get((ph, 'fill'), []):
                    for h in Rhino.Geometry.Hatch.Create([P(c) for c in cs], solid, 0.0, 1.0, 0.001) or []: d.Objects.AddHatch(h, att(lname + '::cut', col, order=20)); s[role + '_fill'] += 1
                for mode in ('thin', 'line'):
                    for cs in C.get((ph, mode), []):
                        for c in cs: d.Objects.AddCurve(P(c), att(lname + '::thin', col, PH_STYLE[mode + '_w'], 22))
            def seen_(ph, col, over=True):
                for c in S.get((ph, 'seen'), []): d.Objects.AddCurve(P(c), att(lname + '::seen', col, PH_STYLE['seen_w'], 21))
                if over:
                    for c in S.get((ph, 'over'), []): d.Objects.AddCurve(P(c), att(lname + '::over', col, PH_STYLE['over_w'], 23, 'over')); s[role + '_over'] += 1
            def ghost_(phs):
                for c in _union_outline([cs for ph in phs for cs in C.get((ph, 'fill'), [])]) + S.get(('OLD', 'seen'), []):
                    d.Objects.AddCurve(P(c), att(lname + '::ghost', G, PH_GHOST['w'], 5, 'ghost')); s[role + '_ghost'] += 1
            if vec and role in allow:                         # 보이는 선 (벡터 HLD) — 디테일 대신
                for c in _hld(det, z, float(f['depth']), skip, allow[role], area[ri]):
                    d.Objects.AddCurve(P(c), att(lname + '::seen', SEEN, PH_STYLE['seen_w'], 10)); s[role + '_hld'] += 1
            if role == 'found':   cut_('OLD', 'OLD'); cut_('DEMO', 'OLD')                       # 전도면: 철거될 것까지 검정
            elif role == 'built': cut_('OLD', 'OLD'); cut_('NEW', 'OLD'); seen_('NEW', 'OLD')   # 현도면: 신축까지 검정
            elif role == 'demo':  ghost_(('OLD', 'DEMO')); cut_('DEMO', 'DEMO'); seen_('DEMO', 'DEMO', over=False)
            elif role == 'add':   ghost_(('OLD',)); cut_('NEW', 'NEW'); seen_('NEW', 'NEW')
        _head(cfg, f, att, W, H, scale)
        stat[name] = dict(s)
    d.Views.Redraw(); print('phase plan', stat)
    return stat

def _head(cfg, f, att, W, H, scale):
    """머리 줄 (책처럼 각 쪽 위 왼쪽): 왼쪽 = 제목·층·축척·방위·as found ↑ as built ↓ / 오른쪽 = 층·축척·방위·demolition ↑ addition ↓"""
    K = System.Drawing.Color.FromArgb(25, 25, 25); h = cfg.get('head_h', 3.2); y = H - cfg.get('head_y', 22.0)
    solid = d.HatchPatterns.Find('SOLID', True); L = PH_LABEL
    def seq(x, parts):
        ym = [y + h * 0.5]                                    # 글자 실제 높이 가운데 (첫 보통 글 상자에서 잼)
        for p in parts:
            if p == 'N':                                      # 방위: 작은 원 + 북쪽 삼각 (모델 +Y = 북)
                cx, cy = x + h * 0.55, ym[0]
                d.Objects.AddCurve(Rhino.Geometry.ArcCurve(Rhino.Geometry.Circle(Point3d(cx, cy, 0), h * 0.55)), att('0 head', K, 0.13, 50))
                tri = Rhino.Geometry.PolylineCurve([Point3d(cx, cy + h * 0.55, 0), Point3d(cx - h * 0.22, cy - h * 0.2, 0), Point3d(cx + h * 0.22, cy - h * 0.2, 0), Point3d(cx, cy + h * 0.55, 0)])
                for hh in Rhino.Geometry.Hatch.Create([tri], solid, 0, 1, 0.001) or []: d.Objects.AddHatch(hh, att('0 head', K, order=50))
                x += h * 2.0; continue
            if not p.lstrip('*'): continue
            te = Rhino.Geometry.TextEntity(); te.Plane = Plane(Point3d(x, y, 0), Vector3d.ZAxis); te.PlainText = p.lstrip('*'); te.TextHeight = h
            a = att('0 head', K, order=50)
            if p.startswith('*'):
                try: te.SetBold(True)
                except Exception: pass
                a.SetUserString('ph_bold', '1')
            g = d.Objects.AddText(te, a)
            b = d.Objects.FindId(g).Geometry.GetBoundingBox(True)
            if not p.startswith('*') and len(ym) == 1: ym[0] = (b.Min.Y + b.Max.Y) / 2.0; ym.append(1)
            x = b.Max.X + h * 1.4
    fl = '%s, 1:%d' % (f.get('label', f['name']), scale)
    seq(cfg.get('margin', 20.0), ['*' + cfg.get('project', ''), fl, 'N', '%s \u2191   %s \u2193' % (L['found'], L['built'])])
    seq(W / 2.0 + cfg.get('margin', 20.0), [fl, 'N', '%s \u2191   %s \u2193' % (L['demo'], L['add'])])

# ---------------- 내보내기 ----------------
def export_phase(cfg, ai=True):
    """PDF 한 파일(층 = 쪽, 벡터 모드면 벡터) + ai=True 면 층마다 일러스트레이터용 .jsx (PDF 옆, '<pdf 이름>_<층>.jsx').
    .ai 만들기: powershell -File <이 스킬>\scripts\run_jsx.ps1 <jsx> illustrator  (또는 일러 파일 > 스크립트 > 기타 스크립트)"""
    pages = [cfg['page'] + ' ' + f['name'] for f in cfg['floors']]
    pdf = cfg['pdf']; vec = cfg.get('vector', True)
    if ai:
        for f, name in zip(cfg['floors'], pages): print('jsx ->', write_ai_jsx(name, os.path.splitext(pdf)[0] + '_' + f['name']))
    export_pages(pages, pdf, dpi=cfg.get('dpi', 300), raster=cfg.get('raster', not vec))

def export_pages(pages, pdf, dpi=300, raster=False):
    """여러 페이지 → PDF 한 파일 (Idle 에서 — MCP 300초 제한 피함). 결과는 pdf 옆 _export_log.txt"""
    log = os.path.join(os.path.dirname(pdf), '_export_log.txt')
    if os.path.exists(log): os.remove(log)
    def job(sender, e):
        Rhino.RhinoApp.Idle -= sc.sticky['ph_idle']; t = time.time()
        try:
            plot_style(); f = Rhino.FileIO.FilePdf.Create()
            for name in pages:
                pg = [v for v in d.Views.GetPageViews() if v.PageName == name][0]
                s = Rhino.Display.ViewCaptureSettings(pg, dpi); s.RasterMode = raster
                s.OutputColor = Rhino.Display.ViewCaptureSettings.ColorMode.PrintColor
                s.UsePrintWidths = True; s.DefaultPrintWidthMillimeters = STYLE['beyond_w']
                f.AddPage(s)
            f.Write(pdf); open(log, 'w').write('ok %.1f s\n' % (time.time() - t))
        except Exception as ex: open(log, 'w').write('ERR %s\n' % ex)
        finally: restore_plot()
    sc.sticky['ph_idle'] = job; Rhino.RhinoApp.Idle += job
    print('export scheduled ->', pdf)

def _pts(c, tol=0.02):
    """페이지 곡선 → 점 목록 (mm, 소수 3자리). 직선·폴리선은 그대로, 나머지는 tol mm 안 폴리선"""
    ok, pl = c.TryGetPolyline()
    if not ok:
        pc = c.ToPolyline(0, 0, math.radians(3), 0, 0, tol, 0, 0, True)
        if pc is None: return []
        pl = pc.ToPolyline()
    return [[round(p.X, 3), round(p.Y, 3)] for p in pl]

def write_ai_jsx(page_name, out_stem):
    """페이지 하나의 페이지 공간 객체 → 일러스트레이터 .jsx (실행하면 같은 크기 대지 + 레이어(칸 › 종류) + 경로·채움·글자 → out_stem.ai 저장)"""
    pv = [v for v in d.Views.GetPageViews() if v.PageName == page_name][0]
    pid = str(pv.MainViewport.Id); root = LYR_SEC + '::' + page_name + '::'
    W, H = pv.PageWidth, pv.PageHeight
    items = collections.defaultdict(list)
    obs = [ob for ob in d.Objects if ob.Attributes.Space == Rhino.DocObjects.ActiveSpace.PageSpace and str(ob.Attributes.ViewportId) == pid]
    for ob in sorted(obs, key=lambda o: o.Attributes.DisplayOrder):
        a = ob.Attributes; lp = d.Layers[a.LayerIndex].FullPath
        if not lp.startswith(root): continue
        key = lp[len(root):].replace('::', '/')
        c = a.ObjectColor; col = [c.R, c.G, c.B]; g = ob.Geometry
        if isinstance(g, Rhino.Geometry.Hatch):
            loops = [_pts(x) for x in list(g.Get3dCurves(True)) + list(g.Get3dCurves(False))]
            loops = [l for l in loops if len(l) >= 3]
            if loops: items[key].append(dict(t='f', l=loops, c=col))
        elif isinstance(g, Rhino.Geometry.Curve):
            p = _pts(g)
            if len(p) < 2: continue
            it = dict(t='p', p=p, c=col, w=round(a.PlotWeight if a.PlotWeight > 0 else 0.13, 3), cl=1 if g.IsClosed else 0)
            ds = a.GetUserString('ph_dash')
            if ds: it['d'] = [float(v) for v in ds.split(',')]
            items[key].append(it)
        elif isinstance(g, Rhino.Geometry.TextEntity):
            b = g.GetBoundingBox(True)
            items[key].append(dict(t='t', s=g.PlainText, h=g.TextHeight, bb=[round(b.Min.X, 3), round(b.Min.Y, 3), round(b.Max.X, 3), round(b.Max.Y, 3)],
                                   c=col, b=1 if a.GetUserString('ph_bold') == '1' else 0))
    order = []                                                # 아래 → 위: 칸마다 ghost·seen·cut·thin·over, 머리 줄 맨 위
    for role, ci, ri, lname in PH_PANELS:
        for k in PH_KINDS:
            if lname + '/' + k in items: order.append(lname + '/' + k)
    order += [k for k in items if k not in order]
    data = dict(W=W, H=H, out=(out_stem + '.ai').replace('\\', '/'), order=order, items={k: items[k] for k in order})
    js = 'var D = ' + json.dumps(data, ensure_ascii=True, separators=(',', ':')) + ';\n' + _AI_JSX
    path = out_stem + '.jsx'
    open(path, 'w', encoding='utf-8').write(js)
    return path

_AI_JSX = r'''
// Rhino phase_plan → Illustrator: 대지 = 페이지 크기(mm), 레이어 = 칸/종류, 채움 = 복합 경로(홀짝), 글자 = 점 글자 (Rhino 글 상자에 맞춤)
var MM = 2.834645669, NP = 0, NF = 0, NT = 0;
function col(c) { var k = new RGBColor(); k.red = c[0]; k.green = c[1]; k.blue = c[2]; return k; }
function pts(a) { var r = []; for (var i = 0; i < a.length; i++) r.push([a[i][0] * MM, (a[i][1] - D.H) * MM]); return r; }
function layerOf(doc, path) {
  var parts = path.split('/'), L = null, ls, i, j, f;
  for (i = 0; i < parts.length; i++) {
    ls = (i == 0) ? doc.layers : L.layers; f = null;
    for (j = 0; j < ls.length; j++) if (ls[j].name == parts[i]) { f = ls[j]; break; }
    if (!f) { f = ls.add(); f.name = parts[i]; }
    L = f;
  }
  return L;
}
function addPath(L, it) {
  var p = L.pathItems.add(); p.setEntirePath(pts(it.p)); p.closed = it.cl == 1; p.filled = false;
  p.stroked = true; p.strokeColor = col(it.c); p.strokeWidth = it.w * MM; p.strokeCap = StrokeCap.BUTTENDCAP;
  if (it.d) p.strokeDashes = [it.d[0] * MM, it.d[1] * MM]; else p.strokeDashes = [];
  NP++;
}
function addFill(L, it) {
  var i, q, cp;
  if (it.l.length == 1) { q = L.pathItems.add(); q.setEntirePath(pts(it.l[0])); q.closed = true; q.stroked = false; q.filled = true; q.fillColor = col(it.c); NF++; return; }
  cp = L.compoundPathItems.add();
  for (i = 0; i < it.l.length; i++) { q = cp.pathItems.add(); q.setEntirePath(pts(it.l[i])); q.closed = true; }
  for (i = 0; i < cp.pathItems.length; i++) { q = cp.pathItems[i]; q.stroked = false; q.filled = true; q.fillColor = col(it.c); q.evenodd = true; }
  NF++;
}
function addText(L, it) {
  var t = L.textFrames.add(), ca, g;
  t.contents = it.s; ca = t.textRange.characterAttributes; ca.size = it.h * MM / 0.716; ca.fillColor = col(it.c);
  try { ca.textFont = app.textFonts.getByName(it.b == 1 ? 'Arial-BoldMT' : 'ArialMT'); } catch (e) {}
  g = t.geometricBounds;                                   // [왼, 위, 오른, 아래] → Rhino 글 상자 왼쪽·세로 가운데에 맞춤
  t.translate(it.bb[0] * MM - g[0], ((it.bb[1] + it.bb[3]) / 2 - D.H) * MM - (g[1] + g[3]) / 2);
  NT++;
}
app.coordinateSystem = CoordinateSystem.ARTBOARDCOORDINATESYSTEM;
var doc = app.documents.add(DocumentColorSpace.RGB, D.W * MM, D.H * MM), k, L, i, it, a;
for (k = 0; k < D.order.length; k++) layerOf(doc, D.order[k]);   // 차례로 만들면 나중 것이 위
for (k = 0; k < D.order.length; k++) {
  L = layerOf(doc, D.order[k]); a = D.items[D.order[k]];
  for (i = 0; i < a.length; i++) { it = a[i]; if (it.t == 'p') addPath(L, it); else if (it.t == 'f') addFill(L, it); else addText(L, it); }
}
for (k = doc.layers.length - 1; k >= 0; k--) if (doc.layers[k].pageItems.length == 0 && doc.layers[k].layers.length == 0) doc.layers[k].remove();
doc.saveAs(new File(D.out), new IllustratorSaveOptions());
'ok ' + D.out + ' paths ' + NP + ' fills ' + NF + ' texts ' + NT + ' layers ' + doc.layers.length;
'''
