import os
import shutil
import subprocess
import html

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "figures")
SVG_DIR = os.path.join(OUT_DIR, "svg")
PNG_DIR = os.path.join(OUT_DIR, "png")
PDF_DIR = os.path.join(OUT_DIR, "pdf")
ART_DIR = os.environ.get("ARTIFACT_DIR", "")
for d in (SVG_DIR, PNG_DIR, PDF_DIR):
    os.makedirs(d, exist_ok=True)

def esc(s):
    return html.escape(str(s))

class SVGCanvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.elements = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="background-color:#ffffff; font-family:\'DejaVu Sans\', Arial, Helvetica, sans-serif;">',
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
        ]

    def rect(self, x, y, w, h, fill="#ccc", stroke="#222", sw=1, rx=0, opacity=1.0):
        self.elements.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" rx="{rx}" fill-opacity="{opacity}"/>')

    def line(self, x1, y1, x2, y2, stroke="#222", sw=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.elements.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def circle(self, cx, cy, r, fill="#1f77b4", stroke="#fff", sw=1):
        self.elements.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x, y, txt, size=11, weight="normal", fill="#111", anchor="middle", baseline="auto", rotate=None):
        tr = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate else ''
        self.elements.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" dominant-baseline="{baseline}"{tr}>{esc(txt)}</text>')

    def polyline(self, pts, stroke="#1f77b4", sw=2.2, dash=None):
        pstr = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.elements.append(f'<polyline points="{pstr}" fill="none" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def save(self, name):
        svg_str = "\n".join(self.elements) + "\n</svg>\n"
        svg_path = os.path.join(SVG_DIR, f"{name}.svg")
        png_path = os.path.join(PNG_DIR, f"{name}.png")
        pdf_path = os.path.join(PDF_DIR, f"{name}.pdf")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_str)
        subprocess.run(["rsvg-convert", "-f", "png", "-d", "300", "-p", "300", "-o", png_path, svg_path], check=True)
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", pdf_path, svg_path], check=True)
        if ART_DIR and os.path.isdir(ART_DIR):
            shutil.copyfile(png_path, os.path.join(ART_DIR, f"{name}.png"))
        print(f"Rendered {name}.svg, {name}.png, and {name}.pdf")

def draw_hbar_panel(c, px, py, pw, ph, title, subtitle, xlabel, items, vmin, vmax):
    c.text(px + pw/2, py - 24, title, size=12, weight="bold", fill="#111")
    c.text(px + pw/2, py - 9, subtitle, size=10, weight="normal", fill="#444")
    c.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
    # grid
    def xmap(v):
        return px + (v - vmin) / (vmax - vmin) * pw
    step = 5 if (vmax - vmin) <= 35 else 10
    start_t = int(vmin // step) * step
    for gv in range(start_t, int(vmax)+1, step):
        if vmin <= gv <= vmax:
            gx = xmap(gv)
            c.line(gx, py, gx, py+ph, stroke="#ddd" if gv != 0 else "#222", sw=1 if gv != 0 else 1.4, dash="3,3" if gv != 0 else None)
            c.text(gx, py+ph+15, f"{gv}", size=9.5, fill="#333")
    c.text(px + pw/2, py+ph+32, xlabel, size=10.5, weight="bold", fill="#222")
    n = len(items)
    row_h = ph / n
    for i, (lbl, val, cil, cih, col) in enumerate(items):
        cy = py + (i + 0.5) * row_h
        x0 = xmap(0)
        xv = xmap(val)
        bx = min(x0, xv)
        bw = abs(xv - x0)
        bh = row_h * 0.56
        c.rect(bx, cy - bh/2, max(bw, 1.5), bh, fill=col, stroke="#222", sw=0.8, opacity=0.88)
        # CI line
        xl = xmap(cil)
        xh = xmap(cih)
        c.line(xl, cy, xh, cy, stroke="#111", sw=1.8)
        c.line(xl, cy-4, xl, cy+4, stroke="#111", sw=1.4)
        c.line(xh, cy-4, xh, cy+4, stroke="#111", sw=1.4)
        # label on left
        lines = lbl.split("\n")
        for li, ltxt in enumerate(lines):
            ly = cy + (li - (len(lines)-1)/2) * 11
            c.text(px - 7, ly, ltxt, size=9.2, fill="#111", anchor="end", baseline="middle")
        # value text
        if val >= 0:
            tx = max(xv, xh) + 5
            c.text(tx, cy, f"{val:+.2f} pp", size=9.2, weight="bold", fill="#111", anchor="start", baseline="middle")
        else:
            tx = max(x0, xh) + 5
            c.text(tx, cy, f"{val:+.2f} pp", size=9.2, weight="bold", fill="#a00", anchor="start", baseline="middle")

# ==============================================================================
# FIG 1: Three-Regime Synthesis Forest Plot
# ==============================================================================
c1 = SVGCanvas(1460, 440)
c1.text(730, 26, "Unified Three-Regime Empirical Synthesis Across >6,400 HPC Runs and 6 Public MI-EEG Cohorts", size=14.5, weight="bold", fill="#0b2545")
c1.text(730, 46, "Input-Space Second-Order Covariance Geometry Dominates Parameter-Space Refitting and Objective-Space Regularization", size=11.5, fill="#333")

r1_items = [
    ("Multi-Cohort Scale (S60-S9)\n[Min Recall, Neural]", 21.17, 17.12, 25.21, "#1f77b4"),
    ("Fixed-Budget Mix (2,592 tr)\n[Min Recall, Classical]", 11.00, 7.50, 14.50, "#2b8cbe"),
    ("Multi-Cohort Scale (S60-S9)\n[Balanced Accuracy]", 5.85, 4.06, 7.65, "#4eb3d3"),
    ("Fixed-Budget Mix (2,592 tr)\n[Balanced Accuracy]", 4.19, 2.40, 5.98, "#7bccc4"),
    ("Objective: TAIL+Cons vs ERM\n[Min Recall, 90 HPC fits]", 1.28, -0.35, 2.91, "#999999"),
    ("Objective: GroupDRO vs ERM\n[Min Recall Collapse]", -7.47, -11.30, -3.64, "#d62728"),
]
draw_hbar_panel(c1, 165, 92, 285, 290, "A. Regime I: Zero-Shot Transfer", "External Dreyer Cohort (n = 85)", "Paired Effect Size (pp)", r1_items, -15, 32)

r2_items = [
    ("Kumar12: EA vs Full CSP\n[Dynamic Weak Recall]", 10.45, 5.45, 16.05, "#2ca02c"),
    ("BNCI9: EA vs Full CSP\n[Dynamic Weak Recall]", 8.52, 5.00, 12.59, "#41ab5d"),
    ("BNCI9: EA vs Full CSP\n[Balanced Accuracy, 9/9+]", 5.65, 3.15, 8.70, "#74c476"),
    ("Kumar12: EA vs Full CSP\n[Balanced Accuracy]", 5.30, 2.82, 8.31, "#74c476"),
    ("BNCI9: Full EA vs RMS\n[Off-Diag Rotation Gain]", 4.63, 1.94, 7.96, "#a1d99b"),
    ("Kumar9: Cue 5s vs Task 2s\n[Window Anchor Shift]", 7.73, 3.76, 12.17, "#ff7f0e"),
    ("BNCI9: Spatial vs LDA-only\n[Unaligned Spatial Refit]", 0.19, -1.85, 2.13, "#999999"),
]
draw_hbar_panel(c1, 635, 92, 285, 290, "B. Regime II: Few-Label Calibration", "Longitudinal Kumar (n=12) & BNCI (n=9)", "Paired Effect Size at B = 20 (pp)", r2_items, -5, 22)

r3_items = [
    ("R3: Schur-Protected Tangent\nvs Unreg. Tangent [BA]", 4.66, 2.40, 6.91, "#8c6bb1"),
    ("R4: Cross-Fit Selection\nvs Profiled Tangent [BA]", 1.75, 0.99, 2.56, "#9ebcda"),
    ("R8: Bounded Fiber Rotation\nvs Support EA (Pan14) [BA]", 0.26, -0.15, 0.68, "#999999"),
    ("R9: Anchored Residual GP\nvs Support EA (Pan14) [BA]", 0.29, -0.25, 0.83, "#999999"),
    ("R10: ERFC vs Support EA\n(Stieger11 Holdout) [BA]", 0.04, -0.02, 0.10, "#999999"),
    ("R10: ERFC vs Matched MAP\n[Introduced Error Cut]", -0.75, -0.86, -0.64, "#17becf"),
    ("R10: ERFC vs Matched MAP\n[Neg-Transfer Session Cut]", -27.04, -32.86, -21.33, "#008b8b"),
]
draw_hbar_panel(c1, 1110, 92, 285, 290, "C. Regime III: Prefix Neural Calibration", "Stieger (n=11), Pan (n=14), Weibo (n=10)", "Paired Effect Size at B = 20 (pp)", r3_items, -38, 13)
c1.save("Fig1_Three_Regime_Synthesis")

# ==============================================================================
# FIG 2: Regime I Zero-Shot Cohort Scaling, Composition & Objectives
# ==============================================================================
c2 = SVGCanvas(1460, 440)
c2.text(730, 26, "Regime I (Repo 1): Multi-Cohort Acquisition Diversity vs. Trial Volume and Objective Regularization", size=14, weight="bold", fill="#0b2545")
c2.text(730, 45, "External Zero-Calibration Evaluation on Dreyer2023 (n = 85 Participants, 6,800 Trials) and Source Nested-CV (n = 60)", size=11, fill="#333")

# Panel A: Source scaling line chart
px, py, pw, ph = 70, 90, 370, 285
c2.text(px+pw/2, py-22, "A. Source Cohort Scaling (Study 1A)", size=12, weight="bold")
c2.text(px+pw/2, py-7, "Weaker-Class Recall Saturates by S29 (+21.17 pp)", size=10, fill="#444")
c2.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
for gv in range(25, 71, 10):
    gy = py + ph - (gv - 20) / 52 * ph
    c2.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c2.text(px-8, gy, f"{gv}%", size=9.5, anchor="end", baseline="middle")
c2.text(px-42, py+ph/2, "Decoding Metric (%)", size=10.5, weight="bold", rotate=-90)

xs_a = [px + 55, px + pw/2, px + pw - 55]
lbl_a = [("S9", "(9 BNCI)"), ("S29", "(9 BNCI + 20 Yang)"), ("S60", "(9 BNCI + 51 Yang)")]
for xi, (l1, l2) in zip(xs_a, lbl_a):
    c2.line(xi, py+ph, xi, py+ph+5, stroke="#222", sw=1.2)
    c2.text(xi, py+ph+18, l1, size=10, weight="bold")
    c2.text(xi, py+ph+31, l2, size=8.8, fill="#444")

def ymap_a(v): return py + ph - (v - 20) / 52 * ph
pts_nba = [(xs_a[i], ymap_a(v)) for i, v in enumerate([58.32, 64.16, 64.17])]
pts_cba = [(xs_a[i], ymap_a(v)) for i, v in enumerate([60.63, 64.59, 65.22])]
pts_nmr = [(xs_a[i], ymap_a(v)) for i, v in enumerate([27.32, 49.03, 48.48])]
pts_cmr = [(xs_a[i], ymap_a(v)) for i, v in enumerate([33.99, 46.84, 47.81])]

c2.polyline(pts_cba, stroke="#6baed6", sw=2.2, dash="5,3")
c2.polyline(pts_nba, stroke="#1f77b4", sw=2.8)
c2.polyline(pts_cmr, stroke="#fc9272", sw=2.2, dash="5,3")
c2.polyline(pts_nmr, stroke="#d62728", sw=2.8)

for i, (x, y) in enumerate(pts_nba):
    c2.circle(x, y, 4.5, fill="#1f77b4")
    c2.text(x, y-9, f"{[58.32,64.16,64.17][i]:.2f}%", size=9, weight="bold", fill="#1f77b4")
for i, (x, y) in enumerate(pts_nmr):
    c2.circle(x, y, 4.5, fill="#d62728")
    c2.text(x, y+15, f"{[27.32,49.03,48.48][i]:.2f}%", size=9, weight="bold", fill="#d62728")
for i, (x, y) in enumerate(pts_cba):
    c2.circle(x, y, 3.8, fill="#6baed6")
for i, (x, y) in enumerate(pts_cmr):
    c2.circle(x, y, 3.8, fill="#fc9272")

c2.rect(px+105, py+172, 245, 58, fill="#fff8f8", stroke="#d62728", sw=1, rx=4)
c2.text(px+227, py+188, "Primary Endpoint (S60 - S9 Min Recall):", size=8.8, weight="bold", fill="#a00")
c2.text(px+227, py+203, "+21.17 pp [17.12, 25.21], p = 8.88e-17", size=8.8, weight="bold", fill="#a00")
c2.text(px+227, py+218, "S60 - S29 = -0.55 pp (p_Holm = 1.00)", size=8.5, fill="#333")

# Legend A
c2.line(px+12, py+14, px+32, py+14, stroke="#1f77b4", sw=2.8); c2.text(px+37, py+17, "Neural BA", size=8.5, anchor="start")
c2.line(px+110, py+14, px+130, py+14, stroke="#6baed6", sw=2.2, dash="4,2"); c2.text(px+135, py+17, "Classical BA", size=8.5, anchor="start")
c2.line(px+215, py+14, px+235, py+14, stroke="#d62728", sw=2.8); c2.text(px+240, py+17, "Neural MinRec", size=8.5, anchor="start")

# Panel B: Study 1C Fixed-Budget Composition (2,592 trials)
px, py, pw, ph = 510, 90, 440, 285
c2.text(px+pw/2, py-22, "B. Fixed 2,592-Trial Composition (Study 1C)", size=12, weight="bold")
c2.text(px+pw/2, py-7, "Mixing Cohorts at Equal Trial Count Cancels Opposite Class Biases", size=10, fill="#444")
c2.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
for gv in range(30, 86, 10):
    gy = py + ph - (gv - 25) / 62 * ph
    c2.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c2.text(px-6, gy, f"{gv}%", size=9.2, anchor="end", baseline="middle")

def ymap_b(v): return py + ph - (v - 25) / 62 * ph
cells_b = [
    ("S9-all", "2,592 tr (BNCI)", 79.29, 41.97, 35.71, 60.63),
    ("Y51-match", "2,592 tr (Yang)", 49.94, 70.29, 37.79, 60.12),
    ("S29-match", "2,592 tr (5-draw)", 62.66, 65.34, 45.32, 64.00),
    ("S60-match", "2,592 tr (50:50)", 64.03, 65.62, 46.71, 64.82),
    ("S60-all", "33,183 tr (All)", 65.41, 65.53, 47.68, 65.47),
]
ba_pts = []
for i, (c_name, c_sub, l_rec, r_rec, m_rec, ba_v) in enumerate(cells_b):
    cx = px + (i + 0.5) * (pw / 5)
    bw = 18
    # Left, Right, MinRecall bars
    for bi, (val, col) in enumerate([(l_rec, "#4a90d9"), (r_rec, "#f28e2b"), (m_rec, "#e15759")]):
        bx = cx + (bi - 1.5) * bw
        by = ymap_b(val)
        c2.rect(bx, by, bw-1.5, py+ph-by, fill=col, stroke="#222", sw=0.7, opacity=0.9)
    c2.text(cx + bw, ymap_b(m_rec)-5, f"{m_rec:.1f}", size=8.2, weight="bold", fill="#b30000")
    c2.text(cx, py+ph+17, c_name, size=9.2, weight="bold")
    c2.text(cx, py+ph+29, c_sub, size=8.0, fill="#444")
    ba_pts.append((cx, ymap_b(ba_v)))

c2.polyline(ba_pts, stroke="#111111", sw=2.4)
for i, (cx, cy) in enumerate(ba_pts):
    c2.circle(cx, cy, 4.2, fill="#111111")
    c2.text(cx, cy-9, f"BA:{cells_b[i][5]:.1f}%", size=8.2, weight="bold", fill="#111")

# Legend B
c2.rect(px+10, py+8, 12, 9, fill="#4a90d9"); c2.text(px+26, py+16, "Left Recall", size=8.2, anchor="start")
c2.rect(px+100, py+8, 12, 9, fill="#f28e2b"); c2.text(px+116, py+16, "Right Recall", size=8.2, anchor="start")
c2.rect(px+195, py+8, 12, 9, fill="#e15759"); c2.text(px+211, py+16, "Min Recall", size=8.2, anchor="start")
c2.line(px+285, py+12, px+305, py+12, stroke="#111", sw=2.4); c2.text(px+310, py+16, "Balanced Acc", size=8.2, anchor="start")

# Panel C: Study 1B 5 Training Objectives (90/90 HPC tasks)
px, py, pw, ph = 1020, 90, 390, 285
c2.text(px+pw/2, py-22, "C. Five Training Objectives (Study 1B)", size=12, weight="bold")
c2.text(px+pw/2, py-7, "90 HPC Fits: Null Gain Over ERM; GroupDRO Collapses", size=10, fill="#444")
c2.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
for gv in range(40, 68, 5):
    gy = py + ph - (gv - 36) / 33 * ph
    c2.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c2.text(px-6, gy, f"{gv}%", size=9.2, anchor="end", baseline="middle")

def ymap_c(v): return py + ph - (v - 36) / 33 * ph
objs = ["ERM", "TAIL", "Consist.", "TAIL+Cons.", "GroupDRO"]
ext_ba = [64.13, 63.01, 63.92, 63.34, 56.03]
cv_ba = [64.00, 64.03, 64.12, 64.05, 61.69]
ext_mr = [50.11, 51.05, 49.55, 51.39, 42.64]
cv_mr = [50.11, 51.54, 49.88, 51.46, 49.15]

xs_c = [px + (i + 0.5) * (pw / 5) for i in range(5)]
for xi, ol in zip(xs_c, objs):
    c2.text(xi, py+ph+18, ol, size=9.2, weight="bold")

c2.polyline([(xs_c[i], ymap_c(v)) for i, v in enumerate(cv_ba)], stroke="#6baed6", sw=2.0, dash="4,3")
c2.polyline([(xs_c[i], ymap_c(v)) for i, v in enumerate(ext_ba)], stroke="#1f77b4", sw=2.6)
c2.polyline([(xs_c[i], ymap_c(v)) for i, v in enumerate(cv_mr)], stroke="#fc9272", sw=2.0, dash="4,3")
c2.polyline([(xs_c[i], ymap_c(v)) for i, v in enumerate(ext_mr)], stroke="#d62728", sw=2.6)

for i in range(5):
    c2.circle(xs_c[i], ymap_c(ext_ba[i]), 4.2, fill="#1f77b4")
    c2.text(xs_c[i], ymap_c(ext_ba[i])-9, f"{ext_ba[i]:.1f}", size=8.5, weight="bold", fill="#1f77b4")
    c2.circle(xs_c[i], ymap_c(ext_mr[i]), 4.2, fill="#d62728")
    c2.text(xs_c[i], ymap_c(ext_mr[i])+14, f"{ext_mr[i]:.1f}", size=8.5, weight="bold", fill="#d62728")

c2.rect(px+16, py+215, 250, 48, fill="#fff8f8", stroke="#d62728", sw=1, rx=4)
c2.text(px+141, py+231, "TAIL+Cons vs ERM: +1.28 pp (p = 0.124)", size=8.5, weight="bold", fill="#333")
c2.text(px+141, py+248, "GroupDRO Collapse: -8.75 pp (p_Holm = 4e-5)", size=8.5, weight="bold", fill="#a00")

c2.line(px+10, py+14, px+28, py+14, stroke="#1f77b4", sw=2.6); c2.text(px+32, py+17, "Dreyer85 BA", size=8.2, anchor="start")
c2.line(px+110, py+14, px+128, py+14, stroke="#6baed6", sw=2.0, dash="4,2"); c2.text(px+132, py+17, "Source60 CV BA", size=8.2, anchor="start")
c2.line(px+230, py+14, px+248, py+14, stroke="#d62728", sw=2.6); c2.text(px+252, py+17, "Dreyer85 MinRec", size=8.2, anchor="start")
c2.save("Fig2_Regime1_ZeroShot_Cohort_vs_Objective")

# ==============================================================================
# FIG 3: Regime II Few-Label Longitudinal Calibration & Mechanisms
# ==============================================================================
c3 = SVGCanvas(1480, 440)
c3.text(740, 26, "Regime II (Repo 2): Few-Label Cross-Session Disentanglement, Error Redistribution & Window Sensitivity", size=14, weight="bold", fill="#0b2545")
c3.text(740, 45, "Longitudinal Evaluation on Kumar2024 (18 Participants x 6 Sessions) and External BNCI2014-001 (9 Participants x 2 Sessions, B = 20 Labels)", size=11, fill="#333")

# Panel A: Component progression
px, py, pw, ph = 60, 90, 295, 285
c3.text(px+pw/2, py-22, "A. Component Disentanglement", size=11.5, weight="bold")
c3.text(px+pw/2, py-7, "BA & Dynamic Weaker-Class Recall", size=9.5, fill="#444")
c3.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
for gv in range(35, 81, 10):
    gy = py + ph - (gv - 30) / 53 * ph
    c3.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c3.text(px-6, gy, f"{gv}%", size=9, anchor="end", baseline="middle")
def ymap3a(v): return py + ph - (v - 30) / 53 * ph
xs3a = [px + (i + 0.5)*(pw/4) for i in range(4)]
for xi, l in zip(xs3a, ["Frozen", "LDA-only", "Full CSP", "EA+Full"]):
    c3.text(xi, py+ph+18, l, size=9, weight="bold")

b_ba = [70.56, 71.67, 71.85, 77.50]
k_ba = [57.94, 59.89, 65.36, 70.66]
b_wr = [54.63, 59.26, 60.00, 68.52]
k_wr = [35.42, 42.06, 47.74, 58.19]

c3.polyline([(xs3a[i], ymap3a(v)) for i, v in enumerate(b_ba)], stroke="#1f77b4", sw=2.6)
c3.polyline([(xs3a[i], ymap3a(v)) for i, v in enumerate(k_ba)], stroke="#2ca02c", sw=2.6)
c3.polyline([(xs3a[i], ymap3a(v)) for i, v in enumerate(b_wr)], stroke="#1f77b4", sw=2.0, dash="4,3")
c3.polyline([(xs3a[i], ymap3a(v)) for i, v in enumerate(k_wr)], stroke="#2ca02c", sw=2.0, dash="4,3")
for i in range(4):
    c3.circle(xs3a[i], ymap3a(b_ba[i]), 4, fill="#1f77b4"); c3.text(xs3a[i], ymap3a(b_ba[i])-8, f"{b_ba[i]:.1f}", size=8, weight="bold", fill="#1f77b4")
    c3.circle(xs3a[i], ymap3a(k_ba[i]), 4, fill="#2ca02c"); c3.text(xs3a[i], ymap3a(k_ba[i])-8, f"{k_ba[i]:.1f}", size=8, weight="bold", fill="#2ca02c")
    c3.circle(xs3a[i], ymap3a(b_wr[i]), 3.5, fill="#1f77b4")
    c3.circle(xs3a[i], ymap3a(k_wr[i]), 3.5, fill="#2ca02c"); c3.text(xs3a[i], ymap3a(k_wr[i])+13, f"{k_wr[i]:.1f}", size=8, fill="#1b4332")

c3.line(px+8, py+12, px+24, py+12, stroke="#1f77b4", sw=2.6); c3.text(px+28, py+15, "BNCI9 BA (Solid) / WeakRec (Dash)", size=8, anchor="start")
c3.line(px+8, py+25, px+24, py+25, stroke="#2ca02c", sw=2.6); c3.text(px+28, py+28, "Kumar12 BA (Solid) / WeakRec (Dash)", size=8, anchor="start")

# Panel B: Error Redistribution C vs I vs G
px, py, pw, ph = 410, 90, 325, 285
c3.text(px+pw/2, py-22, "B. Error Redistribution (C vs. I)", size=11.5, weight="bold")
c3.text(px+pw/2, py-7, "Why Unaligned Spatial Refit Stalls on BNCI", size=9.5, fill="#444")
c3.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap3b(v): return py + ph - (v - (-14)) / 34 * ph
y0_3b = ymap3b(0)
for gv in [-10, -5, 0, 5, 10, 15]:
    gy = ymap3b(gv)
    c3.line(px, gy, px+pw, gy, stroke="#ddd" if gv != 0 else "#222", sw=1 if gv != 0 else 1.4, dash="3,3" if gv != 0 else None)
    c3.text(px-6, gy, f"{gv}", size=9, anchor="end", baseline="middle")

ops3b = [
    ("K:LDA", 10.70, -8.75, 1.95),
    ("K:Spatial", 16.04, -10.57, 5.47),
    ("K:EA", 14.61, -9.32, 5.30),
    ("B:LDA", 3.24, -2.13, 1.11),
    ("B:Spatial", 4.17, -3.98, 0.19),
    ("B:EA", 12.78, -7.13, 5.65),
]
g_pts = []
for i, (ol, cv, iv, gv) in enumerate(ops3b):
    cx = px + (i + 0.5) * (pw / 6)
    bw = 26
    yc = ymap3b(cv)
    yi = ymap3b(iv)
    c3.rect(cx - bw/2, yc, bw, y0_3b - yc, fill="#2ca02c", stroke="#222", sw=0.7, opacity=0.85)
    c3.rect(cx - bw/2, y0_3b, bw, yi - y0_3b, fill="#d62728", stroke="#222", sw=0.7, opacity=0.85)
    c3.text(cx, py+ph+18, ol, size=8.5, weight="bold")
    g_pts.append((cx, ymap3b(gv)))
c3.polyline(g_pts, stroke="#111", sw=2.2)
for i, (cx, cy) in enumerate(g_pts):
    c3.circle(cx, cy, 4, fill="#111")
    c3.text(cx, cy - 8, f"{ops3b[i][3]:+.2f}", size=8, weight="bold", fill="#111")
c3.rect(px+10, py+8, 11, 9, fill="#2ca02c"); c3.text(px+25, py+16, "Corrected (+C)", size=8, anchor="start")
c3.rect(px+110, py+8, 11, 9, fill="#d62728"); c3.text(px+125, py+16, "Introduced (-I)", size=8, anchor="start")
c3.circle(px+220, py+12, 3.8, fill="#111"); c3.text(px+228, py+16, "Net Gain G=C-I", size=8, anchor="start")

# Panel C: Normalization Geometry (544 fits)
px, py, pw, ph = 790, 90, 310, 285
c3.text(px+pw/2, py-22, "C. Scale vs. Off-Diagonal EA", size=11.5, weight="bold")
c3.text(px+pw/2, py-7, "544 Matched Shared-Coordinate Fits", size=9.5, fill="#444")
c3.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap3c(v): return py + ph - (v - 60) / 22 * ph
for gv in [60, 65, 70, 75, 80]:
    gy = ymap3c(gv)
    c3.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c3.text(px-6, gy, f"{gv}%", size=9, anchor="end", baseline="middle")

norms3c = [
    ("Full CSP", 65.36, 71.85),
    ("Diag+Full", 67.88, 72.59),
    ("RMS+Full", 69.52, 72.87),
    ("Full EA", 70.43, 77.50),
]
for i, (nl, kv, bv) in enumerate(norms3c):
    cx = px + (i + 0.5) * (pw / 4)
    bw = 24
    yk = ymap3c(kv); yb = ymap3c(bv)
    c3.rect(cx - bw - 1, yk, bw, py+ph-yk, fill="#52b788", stroke="#222", sw=0.7)
    c3.rect(cx + 1, yb, bw, py+ph-yb, fill="#4a90d9", stroke="#222", sw=0.7)
    c3.text(cx - bw/2 - 1, yk - 5, f"{kv:.1f}", size=8, weight="bold", fill="#1b4332")
    c3.text(cx + bw/2 + 1, yb - 5, f"{bv:.1f}", size=8, weight="bold", fill="#0d3b66")
    c3.text(cx, py+ph+18, nl, size=8.8, weight="bold")
c3.rect(px+10, py+8, 12, 9, fill="#52b788"); c3.text(px+26, py+16, "Kumar Primary (n=12)", size=8, anchor="start")
c3.rect(px+155, py+8, 12, 9, fill="#4a90d9"); c3.text(px+171, py+16, "BNCI External (n=9)", size=8, anchor="start")
c3.text(px+pw/2, py+36, "BNCI EA - RMS: +4.63 pp [+1.94, +7.96]", size=8.5, weight="bold", fill="#0d3b66")
c3.text(px+pw/2, py+50, "Kumar EA - RMS: +0.91 pp [-1.28, +3.18]", size=8.5, fill="#1b4332")

# Panel D: Window Sensitivity (148 phase fits)
px, py, pw, ph = 1155, 90, 290, 285
c3.text(px+pw/2, py-22, "D. Window Anchor Mechanism", size=11.5, weight="bold")
c3.text(px+pw/2, py-7, "Cue [0,5)s vs. Task [2,4)s (148 Fits)", size=9.5, fill="#444")
c3.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap3d(v): return py + ph - (v - (-14)) / 30 * ph
y0_3d = ymap3d(0)
for gv in [-10, -5, 0, 5, 10, 15]:
    gy = ymap3d(gv)
    c3.line(px, gy, px+pw, gy, stroke="#ddd" if gv != 0 else "#222", sw=1 if gv != 0 else 1.4, dash="3,3" if gv != 0 else None)
    c3.text(px-6, gy, f"{gv}", size=9, anchor="end", baseline="middle")

w_items = [
    ("Cue 5s\n[0, 5) s", 7.85, 3.04, 13.66, 7.55, 2.32, 13.95),
    ("Task 2s\n[2, 4) s", 0.13, -1.40, 1.92, 0.53, -1.01, 2.39),
    ("Paired Diff\n(Task - Cue)", -7.73, -12.17, -3.76, -7.03, -11.84, -2.97),
]
for i, (wl, c9, c9l, c9h, m8, m8l, m8h) in enumerate(w_items):
    cx = px + (i + 0.5) * (pw / 3)
    bw = 24
    for bi, (val, vl, vh, col) in enumerate([(c9, c9l, c9h, "#ff7f0e"), (m8, m8l, m8h, "#ffbb78")]):
        bx = cx - bw - 1 if bi == 0 else cx + 1
        yv = ymap3d(val)
        c3.rect(bx, min(y0_3d, yv), bw, abs(yv - y0_3d), fill=col, stroke="#222", sw=0.7)
        bcx = bx + bw/2
        c3.line(bcx, ymap3d(vl), bcx, ymap3d(vh), stroke="#111", sw=1.5)
        if bi == 0:
            ty = (yv - 6) if val >= 0 else (yv + 13)
            c3.text(bcx - 12, ty, f"{val:+.2f}", size=8.2, weight="bold", fill="#b35900")
    for li, lstr in enumerate(wl.split("\n")):
        c3.text(cx, py+ph+16+li*12, lstr, size=8.5, weight="bold" if li==0 else "normal")
c3.rect(px+10, py+8, 12, 9, fill="#ff7f0e"); c3.text(px+26, py+16, "Conditional (n=9)", size=8, anchor="start")
c3.rect(px+145, py+8, 12, 9, fill="#ffbb78"); c3.text(px+161, py+16, "Metadata-Complete (n=8)", size=8, anchor="start")
c3.save("Fig3_Regime2_FewLabel_Alignment_and_Mechanisms")

# ==============================================================================
# FIG 4: Regime III Neural Churn Trap, Schur Protection & Multi-Round Plateau
# ==============================================================================
c4 = SVGCanvas(1460, 440)
c4.text(730, 26, "Regime III (Repo 3, Part 1): The 95% Error-Churn Trap in Prefix Neural Calibration & Schur Protection", size=14, weight="bold", fill="#0b2545")
c4.text(730, 45, "51-Condition Neural Error-Redistribution Grid, Round 3 Schur/Fisher Protection (n = 11), and Multi-Round BA Plateau (n = 35)", size=11, fill="#333")

# Panel A: 51-Condition Neural Grid Error Cancellation
px, py, pw, ph = 65, 90, 370, 285
c4.text(px+pw/2, py-22, "A. 51-Condition Neural Churn Audit", size=12, weight="bold")
c4.text(px+pw/2, py-7, "93.0%–95.4% of Trial Flips Cancel Out (C ≈ I)", size=10, fill="#444")
c4.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap4a(v): return py + ph - (v / 105) * ph
for gv in [0, 20, 40, 60, 80, 100]:
    gy = ymap4a(gv)
    c4.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c4.text(px-6, gy, f"{gv}", size=9, anchor="end", baseline="middle")

g_items = [
    ("Churn D (x5)\n(C + I, pp)", 9.52*5, 8.09*5, "9.52 pp", "8.09 pp"),
    ("Net |G| (x5)\n(|C - I|, pp)", 0.68*5, 0.01*5, "+0.68 pp", "+0.01 pp"),
    ("Within-Session\nCancel (%)", 84.42, 82.54, "84.4%", "82.5%"),
    ("Total Error\nCancel (%)", 93.02, 95.35, "93.0%", "95.4%"),
]
for i, (gl, v1, v2, t1, t2) in enumerate(g_items):
    cx = px + (i + 0.5) * (pw / 4)
    bw = 26
    y1 = ymap4a(v1); y2 = ymap4a(v2)
    c4.rect(cx - bw - 1, y1, bw, py+ph-y1, fill="#1f77b4", stroke="#222", sw=0.7)
    c4.rect(cx + 1, y2, bw, py+ph-y2, fill="#ff7f0e", stroke="#222", sw=0.7)
    c4.text(cx - bw/2 - 1, y1 - 5, t1, size=8, weight="bold", fill="#1f77b4")
    c4.text(cx + bw/2 + 1, y2 - 5, t2, size=8, weight="bold", fill="#b35900")
    for li, ls in enumerate(gl.split("\n")):
        c4.text(cx, py+ph+16+li*12, ls, size=8.5, weight="bold" if li==0 else "normal")
c4.rect(px+12, py+10, 12, 9, fill="#1f77b4"); c4.text(px+28, py+18, "Median vs Frozen f0", size=8.5, anchor="start")
c4.rect(px+165, py+10, 12, 9, fill="#ff7f0e"); c4.text(px+181, py+18, "Median vs Support EA", size=8.5, anchor="start")

# Panel B: Round 3 Schur/Information Protection across 11 Stieger Participants
px, py, pw, ph = 505, 90, 430, 285
c4.text(px+pw/2, py-22, "B. Round 3 Schur Protection (n = 11)", size=12, weight="bold")
c4.text(px+pw/2, py-7, "Recovers +4.66 pp Over Unregularized Tangent Collapse", size=10, fill="#444")
c4.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap4b(v): return py + ph - (v - (-3)) / 15 * ph
y0_4b = ymap4b(0)
for gv in [-2, 0, 2, 4, 6, 8, 10]:
    gy = ymap4b(gv)
    c4.line(px, gy, px+pw, gy, stroke="#ddd" if gv != 0 else "#222", sw=1 if gv != 0 else 1.4, dash="3,3" if gv != 0 else None)
    c4.text(px-6, gy, f"{gv:+} pp" if gv!=0 else "0", size=8.8, anchor="end", baseline="middle")

subs_r3 = [("S62", -1.99), ("S42", 0.51), ("S58", 1.10), ("S31", 2.67), ("S18", 2.80),
           ("S28", 3.73), ("S32", 6.43), ("S44", 7.93), ("S48", 8.65), ("S9", 9.30), ("S20", 10.11)]
for i, (sid, dv) in enumerate(subs_r3):
    cx = px + (i + 0.5) * (pw / 11)
    bw = 24
    yd = ymap4b(dv)
    col = "#2ca02c" if dv >= 0 else "#d62728"
    c4.rect(cx - bw/2, min(y0_4b, yd), bw, abs(yd - y0_4b), fill=col, stroke="#222", sw=0.7, opacity=0.86)
    ty = yd - 5 if dv >= 0 else yd + 12
    c4.text(cx, ty, f"{dv:+.1f}", size=7.8, weight="bold", fill="#1b4332" if dv>=0 else "#a00")
    c4.text(cx, py+ph+18, sid, size=8.8, weight="bold")

ym_r3 = ymap4b(4.66)
c4.line(px, ym_r3, px+pw, ym_r3, stroke="#111", sw=1.8, dash="6,4")
c4.rect(px+14, py+12, 255, 38, fill="#f0fff4", stroke="#2ca02c", sw=1, rx=4)
c4.text(px+141, py+27, "Mean Recovery: +4.66 pp [+2.40, +6.91]", size=8.8, weight="bold", fill="#1b4332")
c4.text(px+141, py+42, "p = 0.0049, p_Holm = 0.0439 (10/11 positive)", size=8.5, fill="#222")

# Panel C: Multi-Family BA Plateau at B=20 Across Stieger, Pan, Weibo
px, py, pw, ph = 1000, 90, 410, 285
c4.text(px+pw/2, py-22, "C. Post-Alignment BA Plateau (R8–R10)", size=12, weight="bold")
c4.text(px+pw/2, py-7, "All 12 Primary Contrasts Non-Significant (p_Holm >= 0.56)", size=10, fill="#444")
c4.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap4c(v): return py + ph - (v - 56) / 20 * ph
for gv in [58, 62, 66, 70, 74]:
    gy = ymap4c(gv)
    c4.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c4.text(px-6, gy, f"{gv}%", size=9, anchor="end", baseline="middle")

cohorts4c = [
    ("Stieger Holdout (n=11)", [62.21, 61.96, 62.20, 62.29, 62.25]),
    ("Pan2023 External (n=14)", [63.82, 63.60, 64.11, 64.11, 63.83]),
    ("Weibo2014 External (n=10)", [71.91, 72.59, 72.54, 72.52, 71.94]),
]
cols4c = ["#1f77b4", "#aec7e8", "#9467bd", "#ff7f0e", "#2ca02c"]
names4c = ["Support EA", "Spatial SGD100", "R9 Anchored GP", "Matched MAP", "ERFC (Ours)"]
for i, (cl, vals) in enumerate(cohorts4c):
    cx = px + (i + 0.5) * (pw / 3)
    bw = 18
    for bi, (v, col) in enumerate(zip(vals, cols4c)):
        bx = cx + (bi - 2.5) * bw
        yv = ymap4c(v)
        c4.rect(bx, yv, bw-1.5, py+ph-yv, fill=col, stroke="#222", sw=0.6)
        if bi in [0, 3, 4]:
            c4.text(bx + bw/2, yv - 5, f"{v:.1f}", size=7.2, weight="bold")
    c4.text(cx, py+ph+18, cl, size=8.8, weight="bold")

for bi, (nm, col) in enumerate(zip(names4c, cols4c)):
    lx = px + 12 + (bi % 3) * 132
    ly = py + 10 + (bi // 3) * 16
    c4.rect(lx, ly, 11, 8, fill=col); c4.text(lx+15, ly+7, nm, size=8, anchor="start")
c4.save("Fig4_Regime3_Neural_Churn_and_Schur_Protection")

# ==============================================================================
# FIG 5: Regime III ERFC Selectivity, Error Suppression & Negative-Transfer Control
# ==============================================================================
c5 = SVGCanvas(1460, 440)
c5.text(730, 26, "Regime III (Repo 3, Part 2): Evidence-Retaining Functional Calibration (ERFC) Selectivity & Risk Control", size=14, weight="bold", fill="#0b2545")
c5.text(730, 45, "18-Test Mechanistic Comparison Across Stieger (n = 11), Pan2023 (n = 14), and Weibo2014 (n = 10) at Budget B = 20", size=11, fill="#333")

# Panel A: Query Update Fraction
px, py, pw, ph = 70, 90, 380, 285
c5.text(px+pw/2, py-22, "A. Query Update Selectivity", size=12, weight="bold")
c5.text(px+pw/2, py-7, "ERFC Abstains on ~84.5% Unverified Query Trials", size=10, fill="#444")
c5.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap5a(v): return py + ph - (v / 110) * ph
for gv in [0, 20, 40, 60, 80, 100]:
    gy = ymap5a(gv)
    c5.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c5.text(px-6, gy, f"{gv}%", size=9, anchor="end", baseline="middle")

u_items = [
    ("Stieger (n=11)", 99.02, 15.07, "-83.95 pp", "p_Holm=0.0137"),
    ("Pan2023 (n=14)", 99.17, 14.37, "-84.80 pp", "p_Holm=0.0022"),
    ("Weibo2014 (n=10)", 99.30, 14.48, "-84.83 pp", "p_Holm=0.0195"),
]
for i, (cl, vm, ve, dtxt, ptxt) in enumerate(u_items):
    cx = px + (i + 0.5) * (pw / 3)
    bw = 32
    ym = ymap5a(vm); ye = ymap5a(ve)
    c5.rect(cx - bw - 2, ym, bw, py+ph-ym, fill="#ff7f0e", stroke="#222", sw=0.8, opacity=0.88)
    c5.rect(cx + 2, ye, bw, py+ph-ye, fill="#2ca02c", stroke="#222", sw=0.8, opacity=0.92)
    c5.text(cx - bw/2 - 2, ym - 6, f"{vm:.1f}%", size=8.5, weight="bold", fill="#b35900")
    c5.text(cx + bw/2 + 2, ye - 6, f"{ve:.1f}%", size=8.5, weight="bold", fill="#1b4332")
    c5.text(cx, py+135, dtxt, size=8.5, weight="bold", fill="#1b4332")
    c5.text(cx, py+148, ptxt, size=7.8, fill="#333")
    c5.text(cx, py+ph+18, cl, size=9.2, weight="bold")
c5.rect(px+12, py+8, 12, 9, fill="#ff7f0e"); c5.text(px+28, py+16, "Matched MAP (Unconstrained)", size=8.5, anchor="start")
c5.rect(px+210, py+8, 12, 9, fill="#2ca02c"); c5.text(px+226, py+16, "ERFC (Evidence-Retaining)", size=8.5, anchor="start")

# Panel B: Introduced Errors vs Corrected Errors (vs Support EA)
px, py, pw, ph = 525, 90, 410, 285
c5.text(px+pw/2, py-22, "B. Error Redistribution vs. Support EA", size=12, weight="bold")
c5.text(px+pw/2, py-7, "ERFC Cuts Newly Introduced Errors by 0.69–0.75 pp", size=10, fill="#444")
c5.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap5b(v): return py + ph - (v / 1.6) * ph
for gv in [0.0, 0.4, 0.8, 1.2, 1.6]:
    gy = ymap5b(gv)
    c5.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c5.text(px-6, gy, f"{gv:.1f}%", size=9, anchor="end", baseline="middle")

err_items = [
    ("Stieger (n=11)", 0.80, 0.05, 0.88, 0.09),
    ("Pan2023 (n=14)", 0.77, 0.06, 1.06, 0.07),
    ("Weibo2014 (n=10)", 0.74, 0.05, 1.35, 0.07),
]
cols5b = ["#d62728", "#ff9896", "#1f77b4", "#9ecae1"]
for i, (cl, im, ie, cm, ce) in enumerate(err_items):
    cx = px + (i + 0.5) * (pw / 3)
    bw = 21
    for bi, (v, col) in enumerate(zip([im, ie, cm, ce], cols5b)):
        bx = cx + (bi - 2) * bw
        yv = ymap5b(v)
        c5.rect(bx, yv, bw-1.5, py+ph-yv, fill=col, stroke="#222", sw=0.6)
        c5.text(bx + bw/2, yv - 5, f"{v:.2f}", size=7.5, weight="bold")
    c5.text(cx, py+ph+18, cl, size=9.2, weight="bold")

c5.rect(px+10, py+8, 11, 8, fill="#d62728"); c5.text(px+25, py+15, "MAP Introduced (I)", size=8, anchor="start")
c5.rect(px+145, py+8, 11, 8, fill="#ff9896"); c5.text(px+160, py+15, "ERFC Introduced (I)", size=8, anchor="start")
c5.rect(px+10, py+22, 11, 8, fill="#1f77b4"); c5.text(px+25, py+29, "MAP Corrected (C)", size=8, anchor="start")
c5.rect(px+145, py+22, 11, 8, fill="#9ecae1"); c5.text(px+160, py+29, "ERFC Corrected (C)", size=8, anchor="start")

# Panel C: Session-Level Negative Transfer Rate vs Support EA
px, py, pw, ph = 1005, 90, 395, 285
c5.text(px+pw/2, py-22, "C. Negative-Transfer Session Rate", size=12, weight="bold")
c5.text(px+pw/2, py-7, "Sessions Degraded Relative to Support EA (%)", size=10, fill="#444")
c5.rect(px, py, pw, ph, fill="#fafafa", stroke="#333", sw=1)
def ymap5c(v): return py + ph - (v / 36) * ph
for gv in [0, 5, 10, 15, 20, 25, 30, 35]:
    gy = ymap5c(gv)
    c5.line(px, gy, px+pw, gy, stroke="#ddd", sw=1, dash="3,3")
    c5.text(px-6, gy, f"{gv}%", size=9, anchor="end", baseline="middle")

nt_items = [
    ("Stieger (n=11)", 30.50, 3.46, "-27.04 pp", "p_Holm=0.0137"),
    ("Pan2023 (n=14)", 21.43, 3.57, "-17.86 pp", "p_Holm=0.0313"),
    ("Weibo2014 (n=10)", 16.67, 3.33, "-13.33 pp", "p_Holm=0.500"),
]
for i, (cl, nm, ne, dtxt, ptxt) in enumerate(nt_items):
    cx = px + (i + 0.5) * (pw / 3)
    bw = 32
    ym = ymap5c(nm); ye = ymap5c(ne)
    c5.rect(cx - bw - 2, ym, bw, py+ph-ym, fill="#e15759", stroke="#222", sw=0.8, opacity=0.88)
    c5.rect(cx + 2, ye, bw, py+ph-ye, fill="#4e79a7", stroke="#222", sw=0.8, opacity=0.92)
    c5.text(cx - bw/2 - 2, ym - 6, f"{nm:.1f}%", size=8.5, weight="bold", fill="#900")
    c5.text(cx + bw/2 + 2, ye - 6, f"{ne:.1f}%", size=8.5, weight="bold", fill="#0d3b66")
    c5.text(cx + 18, ye - 32, dtxt, size=8.2, weight="bold", fill="#0d3b66")
    c5.text(cx + 18, ye - 20, ptxt, size=7.6, fill="#333")
    c5.text(cx, py+ph+18, cl, size=9.2, weight="bold")
c5.rect(px+12, py+8, 12, 9, fill="#e15759"); c5.text(px+28, py+16, "Matched MAP Neg-Transfer", size=8.5, anchor="start")
c5.rect(px+205, py+8, 12, 9, fill="#4e79a7"); c5.text(px+221, py+16, "ERFC Neg-Transfer", size=8.5, anchor="start")
c5.save("Fig5_Regime3_ERFC_Selectivity_Tradeoff")
print("ALL 5 SVG+PNG+PDF FIGURES BUILT!")
