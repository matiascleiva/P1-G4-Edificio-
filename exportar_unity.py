"""
Exporta las mallas y subelementos del edificio en un formato amigable para
Unity (vértices + triángulos de losa, y segmentos de columnas/muros/vigas).

Lee:
- modelo_edificio_geometria.json  -> nodos + losas (huella con voladizos)
- elementos_verticales.json       -> columnas y muros
- vigas_tributarias.json          -> vigas por nivel

Genera: edificio_para_unity.json
"""
import json
import os

RAIZ = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(RAIZ, "modelo_edificio_geometria.json")
ELV = os.path.join(RAIZ, "elementos_verticales.json")
VIG = os.path.join(RAIZ, "vigas_tributarias.json")
SAL = os.path.join(RAIZ, "edificio_para_unity.json")


def leer(r):
    with open(r, encoding="utf-8") as f:
        return json.load(f)


def main():
    geo = leer(GEO)
    verticales = leer(ELV)
    vv = leer(VIG)["vigas"]
    n_niv = geo["_meta"]["n_niveles"]
    coords = {n["nodeTag"]: [n["x"], n["y"], n["z"]] for n in geo["nodos"]}

    # ---- LOSAS: malla plana (2 triángulos por losa, con voladizos) ----
    losas = []
    for L in geo["losas"]:
        esc = L["esquinas"]  # SW, SE, NE, NW
        # orden para dos triángulos (orientación hacia arriba: +Z)
        idx = [0, 1, 2, 0, 2, 3]  # SW-SE-NE, SW-NE-NW
        verts = [[c["x"], c["y"], c["z"]] for c in esc]  # reindexar local
        # mapear a una lista global de vértices de esta losa
        losas.append({
            "nivel": L["nivel"], "nombre": L["nombre"], "z_m": L["z_m"],
            "vertices": verts, "triangulos": idx,
            "voladizos": L["voladizos"],
        })

    # ---- ELEMENTOS LINEALES ---- (columnas/muros por tramo, vigas por nivel)
    columnas, muros, vigas = [], [], []
    for e in verticales:
        base = e["iNode"]
        tramos = []
        prev = coords[base]
        for k in range(1, n_niv + 1):
            p = coords[1000 + (k - 1) * 100 + base]
            tramos.append({"a": prev, "b": p, "nivel": k,
                           "tag": 10000 + k * 1000 + base})
            prev = p
        destino = columnas if e["type"] == "columna" else muros
        destino.append({
            "id": base, "tipo": e["type"], "descripcion": e["descripcion"],
            "seccion": e["sectionTag"], "tramos": tramos,
        })
    nX = len([v for v in vv if v["dir"] == "X"])
    for idx, v in enumerate(vv):
        grp = "X" if v["dir"] == "X" else "Y"
        i_grp = idx if grp == "X" else (idx - nX)
        for k in range(1, n_niv + 1):
            a = coords[v["iNode"] + (k - 1) * 100]
            b = coords[v["jNode"] + (k - 1) * 100]
            vigas.append({
                "dir": v["dir"], "longitud_m": v["longitud_m"], "nivel": k,
                "a": a, "b": b, "iNode": v["iNode"], "jNode": v["jNode"],
                "tag": (20000 if grp == "X" else 30000) + k * 100 + i_grp,
            })

    out = {
        "_meta": {
            "destino": "Unity",
            "unidades": "metros (m)",
            "coordenadas": {"nx": "E->I' (+X)", "ny": "3->1 (+Y)", "nz": "vertical"},
            "n_niveles": n_niv, "h_piso_m": geo["_meta"]["h_piso_m"],
            "origen_z_base": 0.0,
            "nota": "Las losas son mallas planas (2 triangulos) en Z=nivel; "
                    "los demas son segmentos (lineas) por tramo/nivel.",
        },
        "losas": losas,
        "columnas": columnas,
        "muros": muros,
        "vigas": vigas,
        "niveles": geo["_meta"]["z_niveles_m"],
    }
    with open(SAL, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    n_los = len(losas)
    n_col = sum(len(c["tramos"]) for c in columnas)
    n_mur = sum(len(m["tramos"]) for m in muros)
    print(f"Export Unity: {SAL}")
    print(f"  Losas (mallas)      : {n_los}")
    print(f"  Columnas (tramos)   : {n_col}")
    print(f"  Muros (tramos)      : {n_mur}")
    print(f"  Vigas (por nivel)   : {len(vigas)}")


if __name__ == "__main__":
    main()
