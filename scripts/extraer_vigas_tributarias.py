"""
Genera vigas_tributarias.json: elementos viga horizontales del primer nivel
(1° Subterráneo, Z=3.96) con sus áreas tributarias calculadas por el método de
áreas tributarias de dos direcciones (a cada vano de losa se reparte 1/4 de su
área a cada una de las 4 vigas que lo bordean).

La suma de todas las áreas tributarias = A_piso (conservación exacta).

Fuente:
- Conectividad horizontal: Planta Cielo 1° Subterráneo (2017-67-101)
- Sección de vigas principales: 'V. 60/80' (Elevaciones de Vigas 2017-67-400)
- Grilla principal: ejes E,F,G,H,I,I'  x  1,2,3

Uso:
    python scripts/extraer_vigas_tributarias.py
"""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND = os.path.join(RAIZ, "fundaciones.json")
SALIDA = os.path.join(RAIZ, "vigas_tributarias.json")

Z = 3.96
SECTION_VIGA = 300  # VIGA_60x80

# Grilla principal (metros), correspondiente a las columnas del modelo
# X: E,F,G,H,I,I'   (nodos de columna de fundación)
XL = [8.021, 18.021, 28.021, 38.021, 48.021, 53.021]
YL = [47.951, 55.201, 64.101]


def shoelace(pts):
    """Devuelve el área (m²) de un polígono por shoelace (pts ordenados)."""
    s = 0.0
    n = len(pts)
    for k in range(n):
        x1, y1 = pts[k]
        x2, y2 = pts[(k + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def ordenar_ccw(pts):
    """Ordena puntos alrededor de su centroide en sentido antihorario."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return sorted(pts, key=lambda p: _ang(p[0] - cx, p[1] - cy))


def _ang(x, y):
    import math
    return math.atan2(y, x)


def main():
    with open(FUND, encoding="utf-8") as f:
        apoyos = json.load(f)

    # Índices de grilla para las columnas principales
    cols = {}
    for xi, x in enumerate(XL):
        for yi, y in enumerate(YL):
            for n in apoyos:
                if abs(n["x"] / 100.0 - x) < 0.25 and abs(n["y"] / 100.0 - y) < 0.25:
                    cols[(xi, yi)] = 1000 + n["nodeTag"]
                    break

    Xbay = [XL[i + 1] - XL[i] for i in range(len(XL) - 1)]
    Ybay = [YL[i + 1] - YL[i] for i in range(len(YL) - 1)]
    midX = [(XL[i] + XL[i + 1]) / 2.0 for i in range(len(XL) - 1)]
    midY = [(YL[j] + YL[j + 1]) / 2.0 for j in range(len(YL) - 1)]

    # Área de cada vano
    bayA = {(i, j): Xbay[i] * Ybay[j] for i in range(len(Xbay))
            for j in range(len(Ybay))}

    # Acumulamos triángulos por viga
    trib = {}

    def add(poly, area):
        trib[id(poly)] = (poly, area)

    # X-beams (5 por fila x 3 filas)
    beams = []
    for j in range(len(YL)):
        for i in range(len(Xbay)):
            poly = []
            if j < len(YL) - 1:  # triángulo vano superior (i,j)
                poly.append((XL[i], YL[j]))
                poly.append((XL[i + 1], YL[j]))
                poly.append((midX[i], midY[j]))
            if j - 1 >= 0:  # triángulo vano inferior (i,j-1)
                poly.append((XL[i], YL[j]))
                poly.append((XL[i + 1], YL[j]))
                poly.append((midX[i], midY[j - 1]))
            poly = ordenar_ccw(poly)
            A = shoelace(poly)
            L = Xbay[i]
            beams.append({
                "elementTag": 2000 + j * 10 + i,
                "type": "viga",
                "dir": "X",
                "iNode": cols[(i, j)],
                "jNode": cols[(i + 1, j)],
                "sectionTag": SECTION_VIGA,
                "longitud_m": round(L, 3),
                "area_trib_m2": round(A, 3),
                "poligono": [[round(p[0], 3), round(p[1], 3)] for p in poly],
            })

    # Y-beams (6 columnas x 2 vanos)
    for i in range(len(XL)):
        for j in range(len(Ybay)):
            poly = []
            if i < len(XL) - 1:  # triángulo vano (i,j) a la derecha
                poly.append((XL[i], YL[j]))
                poly.append((XL[i], YL[j + 1]))
                poly.append((midX[i], midY[j]))
            if i - 1 >= 0:  # triángulo vano (i-1,j) a la izquierda
                poly.append((XL[i], YL[j]))
                poly.append((XL[i], YL[j + 1]))
                poly.append((midX[i - 1], midY[j]))
            poly = ordenar_ccw(poly)
            A = shoelace(poly)
            L = Ybay[j]
            beams.append({
                "elementTag": 3000 + i * 10 + j,
                "type": "viga",
                "dir": "Y",
                "iNode": cols[(i, j)],
                "jNode": cols[(i, j + 1)],
                "sectionTag": SECTION_VIGA,
                "longitud_m": round(L, 3),
                "area_trib_m2": round(A, 3),
                "poligono": [[round(p[0], 3), round(p[1], 3)] for p in poly],
            })

    atot = sum(b["area_trib_m2"] for b in beams)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {
                "nivel": "1° Subterráneo",
                "z_m": Z,
                "sectionTag_viga": SECTION_VIGA,
                "seccion": "V. 60/80 (0.60 x 0.80 m)",
                "a_piso_m2": round(sum(bayA.values()), 3),
                "suma_areas_tributarias_m2": round(atot, 3),
                "método": "Áreas tributarias 2 direcciones (1/4 de vano por viga)",
            },
            "vigas": beams,
        }, f, ensure_ascii=False, indent=2)

    print(f"Vigas horizontales: {len(beams)}  (SumA_trib={round(atot,2)} m2, A_piso={round(sum(bayA.values()),2)} m2)")
    print(f"-> {SALIDA}")


if __name__ == "__main__":
    main()
