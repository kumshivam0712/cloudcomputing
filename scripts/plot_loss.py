"""Training-loss-per-epoch chart (SVG, standard library only) for the report.

    python scripts/plot_loss.py training/loss.csv:v1 training/loss_v2.csv:v2 > report/loss.svg
"""
import csv
import math
import sys

COLORS = ["#2a78d6", "#eb6834"]          # categorical slots 1-2 (validated adjacent pair)
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
W, H, L, R, T, B = 560, 230, 52, 70, 26, 38


def read(path):
    with open(path, encoding="utf-8") as f:
        return [(int(r["epoch"]), float(r["train_loss"])) for r in csv.DictReader(f)]


def main():
    series = []
    for arg in sys.argv[1:]:
        path, _, name = arg.partition(":")
        series.append((name or path, read(path)))
    xmax = max(e for _, pts in series for e, _ in pts)
    ymax = max(v for _, pts in series for _, v in pts)
    top = math.ceil(ymax * 2) / 2 if ymax > 1 else math.ceil(ymax * 10) / 10
    step = top / 5

    def x(e):
        return L + (e - 1) / max(1, xmax - 1) * (W - L - R)

    def y(v):
        return T + (1 - v / top) * (H - T - B)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="DejaVu Sans, Arial, sans-serif" font-size="10" role="img" '
           f'aria-label="Training loss per epoch">',
           f'<rect width="{W}" height="{H}" fill="#fcfcfb"/>']
    for i in range(6):
        v = i * step
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{L - 6}" y="{y(v) + 3:.1f}" text-anchor="end" fill="{MUTED}">{v:.2f}</text>')
    for e in range(1, xmax + 1):
        out.append(f'<text x="{x(e):.1f}" y="{H - B + 14}" text-anchor="middle" fill="{MUTED}">{e}</text>')
    out.append(f'<text x="{(L + W - R) / 2}" y="{H - 6}" text-anchor="middle" fill="{MUTED}">epoch</text>')
    out.append(f'<text x="{L}" y="{T - 10}" fill="{INK}" font-weight="bold">Training loss (mean cross-entropy '
               f'per target token)</text>')
    for i, (name, pts) in enumerate(series):
        c = COLORS[i % len(COLORS)]
        d = " ".join(f"{'M' if j == 0 else 'L'}{x(e):.1f},{y(v):.1f}" for j, (e, v) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>')
        for e, v in pts:
            out.append(f'<circle cx="{x(e):.1f}" cy="{y(v):.1f}" r="3" fill="{c}" stroke="#fcfcfb" stroke-width="1.5"/>')
        e, v = pts[-1]
        out.append(f'<text x="{x(e) + 8:.1f}" y="{y(v) + 3 + i * 11:.1f}" fill="{INK}">{name} {v:.3f}</text>')
        lx = W - R - 150 + i * 75
        out.append(f'<line x1="{lx}" x2="{lx + 16}" y1="{T - 13}" y2="{T - 13}" stroke="{c}" stroke-width="2"/>')
        out.append(f'<text x="{lx + 20}" y="{T - 10}" fill="{INK}">{name}</text>')
    out.append("</svg>")
    print("\n".join(out))


if __name__ == "__main__":
    main()
