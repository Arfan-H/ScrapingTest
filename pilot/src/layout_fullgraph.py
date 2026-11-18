"""Tata letak terstruktur: satu cakram per kategori (Cianjur kiri, Rembang kanan),
golongan di kolom kanan, dokumen dan RS di tepi. Input/Output: full.json (posisi diganti)."""
import json, math, sys
from collections import defaultdict
d = json.load(open(sys.argv[1]))
N, E = d["N"], d["E"]
nb = defaultdict(list)
for a, b, r in E:
    nb[a].append((b, r)); nb[b].append((a, r))
kat_of, gol_of, partner = {}, {}, {}
for a, b, r in E:
    if r == 1: kat_of[a] = b
    if r == 2: gol_of[a] = b
    if r == 3: partner[a] = b; partner[b] = a
kats = [i for i, n in enumerate(N) if n[2] == 2]
gols = [i for i, n in enumerate(N) if n[2] == 1]
docs = [i for i, n in enumerate(N) if n[2] == 3]
rss = [i for i, n in enumerate(N) if n[2] == 4]
mem = defaultdict(list)
for i, k in kat_of.items(): mem[k].append(i)
SP = 9.0          # jarak antar titik layanan
GA = math.pi * (3 - math.sqrt(5))
def disc_r(n): return SP * math.sqrt(n + 40) * 0.62
# susun cakram (rak) di area tengah selebar 1000
order = sorted(kats, key=lambda k: -len(mem[k]))
X0, WIDTH, GAP = 120, 1000, 46
x, y, rowh, pos = X0, 0, 0, {}
for k in order:
    R = disc_r(len(mem[k]))
    if x + 2 * R > X0 + WIDTH and x > X0:
        x, y, rowh = X0, y + rowh + GAP, 0
    pos[k] = (x + R, y + R + 22)
    x += 2 * R + GAP; rowh = max(rowh, 2 * R + 22)
H = y + rowh
# titik phyllotaxis per cakram, mulai dari cincin luar hub
gol_rank = {g: i for i, g in enumerate(sorted(gols, key=lambda g: N[g][4]))}
for k in kats:
    cx, cy = pos[k]; ms = mem[k]; n = len(ms); off = 30
    pts = []
    for j in range(off, off + n):
        r = SP * 0.62 * math.sqrt(j); a = j * GA
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.sort(key=lambda p: p[0])
    cj = [i for i in ms if N[i][3] == 0]; rb = [i for i in ms if N[i][3] == 1]
    left, right = pts[:len(cj)], pts[len(cj):]
    # Cianjur: yang punya padanan paling dekat sumbu tengah
    left.sort(key=lambda p: -p[0]); cj.sort(key=lambda i: (i not in partner, N[i][4].lower()))
    for i, p in zip(cj, left): N[i][0], N[i][1] = p
    # Rembang: yang punya padanan dekat sumbu, sisanya dikelompokkan per golongan (urut sudut)
    rp = [i for i in rb if i in partner]; rq = [i for i in rb if i not in partner]
    right.sort(key=lambda p: p[0]); near, far = right[:len(rp)], right[len(rp):]
    for i, p in zip(sorted(rp, key=lambda i: N[i][4].lower()), near): N[i][0], N[i][1] = p
    far.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    rq.sort(key=lambda i: (gol_rank.get(gol_of.get(i), -1), N[i][4].lower()))
    for i, p in zip(rq, far): N[i][0], N[i][1] = p
    N[k][0], N[k][1] = cx, cy
# kolom kanan: golongan, lalu dokumen & RS Rembang; kolom kiri: dokumen & RS Cianjur
gx = X0 + WIDTH + 70
gs = sorted(gols, key=lambda g: N[g][4])
for t, g in enumerate(gs):
    N[g][0], N[g][1] = gx, 40 + t * (H - 80) / max(1, len(gs) - 1)
side_doc = {N[i][3]: i for i in docs}; side_rs = {N[i][3]: i for i in rss}
N[side_doc[0]][0], N[side_doc[0]][1] = 40, H * 0.5
N[side_rs[0]][0], N[side_rs[0]][1] = 40, H * 0.5 - 90
N[side_doc[1]][0], N[side_doc[1]][1] = gx + 230, H * 0.5
N[side_rs[1]][0], N[side_rs[1]][1] = gx + 230, H * 0.5 - 90
xs = [n[0] for n in N]; ys = [n[1] for n in N]
mnx, mny = min(xs), min(ys); sc = 1000 / max(max(xs) - mnx, max(ys) - mny)
for n in N:
    n[0] = round((n[0] - mnx) * sc, 1); n[1] = round((n[1] - mny) * sc, 1)
d["box"] = [round((max(xs) - mnx) * sc, 1), round((max(ys) - mny) * sc, 1)]
json.dump(d, open(sys.argv[2], "w"), ensure_ascii=False, separators=(",", ":"))
print("box", d["box"], "kategori", [(N[k][4], len(mem[k])) for k in order])
