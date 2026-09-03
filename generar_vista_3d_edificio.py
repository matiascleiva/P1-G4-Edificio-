"""
Genera una vista 3D interactiva y autocontenida del EDIFICIO COMPLETO (N niveles).

Lee:
- modelo_edificio_geometria.json  -> nodos por nivel (generado por model_edificio.py)
- elementos_verticales.json       -> columnas y muros (tipo por apoyo)
- vigas_tributarias.json          -> vigas por nivel
- resultados_fuerzas_internas_edificio.json -> esfuerzos para tooltips (opcional)

Embebe plotly.js localmente (plotly.min.js) -> HTML autocontenido.

Uso:
    python generar_vista_3d_edificio.py
"""
import json
import os

RAIZ = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(RAIZ, "modelo_edificio_geometria.json")
ELV = os.path.join(RAIZ, "elementos_verticales.json")
VIG = os.path.join(RAIZ, "vigas_tributarias.json")
INT = os.path.join(RAIZ, "resultados_fuerzas_internas_edificio.json")
PLOTLY = os.path.join(RAIZ, "plotly.min.js")
SALIDA = os.path.join(RAIZ, "vista_3d_edificio.html")


def leer(r):
    with open(r, encoding="utf-8") as f:
        return json.load(f)


def main():
    geo = leer(GEO)
    verticales = leer(ELV)
    vv = leer(VIG)["vigas"]
    internos = {}
    if os.path.exists(INT):
        for r in leer(INT)["elementos"]:
            internos[r["elementTag"]] = r
    n_niv = geo["_meta"]["n_niveles"]

    coords = {n["nodeTag"]: (n["x"], n["y"], n["z"]) for n in geo["nodos"]}
    apoyos = set(n["nodeTag"] for n in geo["nodos"] if n["tipo"] == "base")

    def hover_txt(tag, nombre):
        r = internos.get(tag)
        if not r:
            return f"{nombre} #{tag}"
        return (f"{nombre} #{tag}<br>{r['descripcion']}"
                f"<br>P={r['P_kN']}·Vy={r['Vy_kN']}·Vz={r['Vz_kN']}"
                f"<br>My={r['My_kNm']}·Mz={r['Mz_kNm']} kN·m")

    def traza_lines(nombre, color, segments, width=6):
        xs, ys, zs, txt = [], [], [], []
        for (a, b, tag, mlabel) in segments:
            xs += [a[0], b[0], None]
            ys += [a[1], b[1], None]
            zs += [a[2], b[2], None]
            txt += [hover_txt(tag, mlabel), "", ""]
        return {"type": "scatter3d", "mode": "lines", "name": nombre,
                "x": xs, "y": ys, "z": zs, "text": txt, "hoverinfo": "text",
                "line": {"color": color, "width": width}}

    columns_walls = []
    cnt_col = 0
    cnt_mur = 0

    for e in verticales:
        base = e["iNode"]
        p0 = coords[base]
        # tramos verticales: base->n1->n2->...->nN
        segs = []
        prev = p0
        for k in range(1, n_niv + 1):
            tag_n = 1000 + (k - 1) * 100 + base
            p = coords[tag_n]
            etag = 10000 + k * 1000 + base
            segs.append((prev, p, etag, f"{e['type'].title()} {base}"))
            prev = p
        if e["type"] == "columna":
            cnt_col += 1
            for s in segs:
                columns_walls.append((s, "Columnas", "#1f77b4"))
        else:
            cnt_mur += 1
            for s in segs:
                columns_walls.append((s, "Muros", "#b0b0b0"))

    # agrupar columnas y muros
    trazas = []
    col_segs = [s[0] for s in columns_walls if s[1] == "Columnas"]
    mur_segs = [s[0] for s in columns_walls if s[1] == "Muros"]
    trazas.append(traza_lines("Columnas", "#1f77b4", col_segs))
    trazas.append(traza_lines("Muros", "#b0b0b0", mur_segs))

    # Vigas por nivel
    nX = len([v for v in vv if v["dir"] == "X"])
    for k in range(1, n_niv + 1):
        segs = []
        for idx, v in enumerate(vv):
            grp = "X" if v["dir"] == "X" else "Y"
            base_e = 20000 if grp == "X" else 30000
            i_grp = idx if grp == "X" else (idx - nX)
            etag = base_e + k * 100 + i_grp
            a = coords[v["iNode"] + (k - 1) * 100]
            b = coords[v["jNode"] + (k - 1) * 100]
            segs.append((a, b, etag, f"Viga {v['dir']} L={v['longitud_m']}m"))
        trazas.append(traza_lines(f"Vigas nivel {k}", "#ff7f0e", segs, width=4))

    # Losas translúcidas por nivel (huella real con voladizos) + base markers
    losas = geo.get("losas", [])
    for L in losas:
        esc = L["esquinas"]  # SW, SE, NE, NW
        xs = [c["x"] for c in esc]
        ys = [c["y"] for c in esc]
        z = L["z_m"]
        k = L["nivel"]
        trazas.append({
            "type": "mesh3d", "name": f"Losa {L['nombre']}",
            "x": xs, "y": ys, "z": [z] * 4, "i": [0, 0], "j": [1, 2], "k": [3, 3],
            "opacity": 0.16, "color": f"rgba(120,{160+10*k},255,0.35)",
            "hoverinfo": "text",
            "customdata": json.dumps(
                [{"voladizos": L["voladizos"]}] * 4, ensure_ascii=False),
            "text": [f"Losa {L['nombre']} (Z={z} m)<br>"
                     f"Voladizos: "
                     + ("; ".join(f"{v['ancho_m']} m ({v['origen'].split(' - ')[-1]})"
                                 for v in L["voladizos"]) or "ninguno")
                     + f"<br>{len(L['voladizos'])} voladizo(s)"],
            "showscale": False,
        })

    base_seg = [(coords[a], (coords[a][0], coords[a][1], 0.01),
                 a, "Base") for a in apoyos]
    trazas.append(traza_lines("Base (apoyos)", "black",
                              base_seg, width=3))

    data = json.dumps(trazas)
    layout = {
        "title": {"text": ("Modelo 3D - EDIFICIO COMPLETO "
                           f"({n_niv} niveles · h={geo['_meta']['h_piso_m']} m)"
                           "<br><sup>1° Subterráneo + 4 pisos · colores por tipo</sup>"),
                  "font": {"size": 15}},
        "scene": {"aspectmode": "data",
                  "xaxis": {"title": "X (m)"}, "yaxis": {"title": "Y (m)"},
                  "zaxis": {"title": "Z (m)"},
                  "camera": {"eye": {"x": 1.8, "y": -1.4, "z": 1.1}},
                  "aspectratio": {"x": 1, "y": 1, "z": 0.9}},
        "hoverlabel": {"bgcolor": "white", "font": {"size": 11}},
        "margin": {"l": 0, "r": 0, "t": 55, "b": 0},
        "legend": {"x": 0.98, "xanchor": "right", "y": 0.98, "yanchor": "top"},
    }
    layout_s = json.dumps(layout)
    plotly_js = open(PLOTLY, encoding="utf-8").read()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Modelo Estructural 3D - Edificio</title>
<style>body{{margin:0;font-family:Arial,sans-serif}}
#info{{position:absolute;top:8px;left:8px;z-index:10;background:#ffffffd9;
padding:6px 10px;border-radius:6px;font-size:12px;max-width:320px}}</style></head>
<body><div id="info">Arrastra rotar · Rueda zoom · Cursor sobre elemento = esfuerzos
(P, Vy, Vz, My, Mz). Losas semi-transparentes.</div>
<div id="plot" style="width:100vw;height:100vh;"></div>
<script>{plotly_js}</script>
<script>var data={data};var layout={layout_s};
Plotly.newPlot('plot',data,layout,{{responsive:true,displaylogo:false}});</script>
</body></html>
"""
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Vista 3D edificio completo: {SALIDA}  ({os.path.getsize(SALIDA)/1e6:.1f} MB)")
    print(f"Elementos: columnas={cnt_col}, muros={cnt_mur}, vigas={n_niv*len(vv)}")


if __name__ == "__main__":
    main()
