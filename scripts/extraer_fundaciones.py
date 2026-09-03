"""
Extrae los apoyos (bases de columnas y muros) de la Planta de Fundaciones
Lámina 2017_67-100 A y guarda fundaciones.json.

Uso:
    python scripts/extraer_fundaciones.py

Requiere: ezdxf
"""
import json
import os

import ezdxf

PLANO = r"C:\Users\matia\OneDrive\Documentos\MCOC\PROYECTO 1\Planos_dxf\Planos_dxf\Planos_1_dxf\2017_67-100.dxf"
SALIDA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fundaciones.json")

# Grilla principal detectada en el plano (lámina 100 A)
# Ejes alfabéticos (X constante) y numéricos (Y constante)
AXES_X = {802.1: "E", 1802.1: "F", 2802.1: "G", 3802.1: "H", 4802.1: "I", 5302.1: "I'"}
AXES_Y = {4795.1: "3", 5520.1: "2", 6410.1: "1"}


def obtener_centros_apoyos(doc):
    """Devuelve la lista de centros (x, y) de los apoyos a partir del relleno sólido
    de las fundaciones/columnas (capa RLE-SOLID)."""
    msp = doc.modelspace()
    centros = []
    for e in msp:
        if e.dxftype() == "HATCH" and e.dxf.layer == "RLE-SOLID":
            pts = []
            for p in e.paths:
                if p.path_type_flags & 2:
                    for v in p.vertices:
                        pts.append((v[0], v[1]))
                else:
                    for edge in p.edges:
                        pts.append((edge.start.x, edge.start.y))
                        pts.append((edge.end.x, edge.end.y))
            if pts:
                xs = [q[0] for q in pts]
                ys = [q[1] for q in pts]
                centros.append(((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0))
    return centros


def agrupar(pts, tol=45.0):
    """Colapsa centros que pertenecen al mismo apoyo (columnas dobles, etc.)."""
    pts = list(pts)
    usados = [False] * len(pts)
    grupos = []
    for i in range(len(pts)):
        if usados[i]:
            continue
        g = [pts[i]]
        usados[i] = True
        for j in range(i + 1, len(pts)):
            if usados[j]:
                continue
            if abs(pts[i][0] - pts[j][0]) < tol and abs(pts[i][1] - pts[j][1]) < tol:
                g.append(pts[j])
                usados[j] = True
        grupos.append(g)
    return [
        (round(sum(p[0] for p in g) / len(g), 1), round(sum(p[1] for p in g) / len(g), 1))
        for g in grupos
    ]


def describir(x, y):
    bx = min(AXES_X, key=lambda a: abs(a - x))
    by = min(AXES_Y, key=lambda a: abs(a - y))
    xl = AXES_X[bx] if abs(bx - x) < 10 else None
    yl = AXES_Y[by] if abs(by - y) < 10 else None
    if xl and yl:
        return f"Columna eje {xl}-{yl}"
    if xl:
        return f"Apoyo mural eje {xl} (Y={y:.0f})"
    if yl:
        return f"Apoyo mural nivel {yl} (X={x:.0f})"
    return f"Muro/{'nucleo'} (X={x:.0f}, Y={y:.0f})"


def main():
    doc = ezdxf.readfile(PLANO)
    centros = agrupar(obtener_centros_apoyos(doc))
    centros.sort(key=lambda p: (p[0], p[1]))
    nodos = []
    for i, (x, y) in enumerate(centros, start=1):
        nodos.append(
            {
                "nodeTag": i,
                "x": round(x, 1),
                "y": round(y, 1),
                "z": 0.0,
                "restraints": [1, 1, 1, 1, 1, 1],
                "descripcion": describir(x, y),
            }
        )
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(nodos, f, ensure_ascii=False, indent=2)
    print(f"Apoyos extraídos: {len(nodos)} -> {SALIDA}")


if __name__ == "__main__":
    main()
