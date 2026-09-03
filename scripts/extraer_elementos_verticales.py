"""
Genera elementos_verticales.json conectando cada apoyo de fundación (nivel Z=0)
con un nodo del primer nivel superior (1° Subterráneo) a partir de la grilla y
las secciones extraídas de los planos.

Criterios (extraídos de los planos):
- Primera cota (primer nivel sobre fundaciones) : Z = 3.96 m  (Lámina 500, Cuadro de Niveles; altura de piso 396 cm, Elevaciones Ejes 1-2-3)
- Columnas de la grilla principal: sección 70x70 cm  -> sectionTag 100 (COL_70)
- Muros / núcleos / apoyos murales            : espesor 20 cm -> sectionTag 200 (MUR_20)

Uso:
    python scripts/extraer_elementos_verticales.py
"""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND = os.path.join(RAIZ, "fundaciones.json")
SALIDA = os.path.join(RAIZ, "elementos_verticales.json")

Z_PRIMER_NIVEL = 3.96

# Grilla principal del edificio (Lámina 100 A + Elevaciones 300-303)
AXES_X = [802.1, 1802.1, 2802.1, 3802.1, 4802.1, 5302.1]
AXES_Y = [4795.1, 5520.1, 6410.1]
TOL = 25.0


def es_columna(x, y):
    """Un apoyo es columna si coincide con una intersección de la grilla principal."""
    for ax in AXES_X:
        for ay in AXES_Y:
            if abs(x - ax) < TOL and abs(y - ay) < TOL:
                return True
    return False


def main():
    with open(FUND, encoding="utf-8") as f:
        apoyos = json.load(f)

    elementos = []
    ncol = 0
    nmur = 0
    for a in apoyos:
        tag = a["nodeTag"]
        # nodo superior: numeración propia continua a partir de 1000
        jtag = 1000 + tag
        if es_columna(a["x"], a["y"]):
            tipo = "columna"
            section = 100
            plano = "Elevación Eje 1-1'/2/3-3' (2017-67-300..303) - P. 70x70"
            ncol += 1
        else:
            tipo = "muro"
            section = 200
            plano = "Cortes/Muros (2017-67-600) - V.S.I. 20/40"
            nmur += 1
        elementos.append(
            {
                "elementTag": tag,
                "type": tipo,
                "iNode": tag,
                "jNode": jtag,
                "sectionTag": section,
                "plano_fuente": plano,
                "descripcion": a["descripcion"],
            }
        )

    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(elementos, f, ensure_ascii=False, indent=2)

    print(f"Elementos verticales: {len(elementos)} (columnas={ncol}, muros={nmur})")
    print(f"Z primer nivel: {Z_PRIMER_NIVEL} m -> {SALIDA}")


if __name__ == "__main__":
    main()
