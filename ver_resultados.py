"""
Imprime en el terminal los resultados del análisis estructural del edificio.

Lee:
- resultados_fuerzas_internas_edificio.json  (esfuerzos por elemento)
- reacciones_base_edificio.json              (reacciones en la base)

Uso:
    python ver_resultados.py                      -> resumen general
    python ver_resultados.py columnas             -> columnas más cargadas
    python ver_resultados.py vigas                -> vigas con mayor momento
    python ver_resultados.py muros                -> muros más cargados
    python ver_resultados.py reacciones           -> reacciones en la base
    python ver_resultados.py top N                -> N primeras filas (default 10)
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = os.path.dirname(os.path.abspath(__file__))
INT = os.path.join(RAIZ, "resultados_fuerzas_internas_edificio.json")
REA = os.path.join(RAIZ, "reacciones_base_edificio.json")

NOMBRES = {1: "1° Subt", 2: "1º Piso", 3: "2º Piso", 4: "3º Piso", 5: "4º Piso"}


def leer(r):
    with open(r, encoding="utf-8") as f:
        return json.load(f)


def parse_nivel(desc):
    if "nivel " in desc:
        try:
            return int(desc.split("nivel ")[-1])
        except ValueError:
            return None
    return None


def fmt(v):
    return f"{v:>10.1f}"


def cabecera(titulo):
    print("=" * 86)
    print(titulo)
    print("=" * 86)


def listar(elementos, clave, desc_titulo, top):
    print(f"  {'tag':>5}  {'sección':>7}  {'nivel':>9}  {'P kN':>9}  "
          f"{'Vy kN':>8}  {'Vz kN':>8}  {'My kN·m':>9}  {'Mz kN·m':>9}  desc")
    for e in elementos[:top]:
        niv = parse_nivel(e["descripcion"])
        nm = NOMBRES.get(niv, "-")
        formato = f"  {e['elementTag']:>5}  {e['sectionTag']:>7}  {nm:>9}"
        if e["type"] == "viga":
            print(f"{formato}  -  {'':>8}  {'':>8}  {e['My_kNm']:>9.1f}  {e['Mz_kNm']:>9.1f}  {e['descripcion']}")
        else:
            print(f"{formato}  {e['P_kN']:>9.1f}  {e['Vy_kN']:>8.1f}  {e['Vz_kN']:>8.1f}"
                  f"  {e['My_kNm']:>9.1f}  {e['Mz_kNm']:>9.1f}  {e['descripcion']}")


def main():
    int_data = leer(INT)
    elementos = int_data["elementos"]
    top = 10
    args = sys.argv[1:]
    if args:
        if args[0].isdigit():
            top = int(args[0])
            args = args[1:]
        elif len(args) >= 2 and args[1].isdigit():
            top = int(args[1])

    modo = args[0].lower() if args else "resumen"
    key = {"columnas": ("columna", "P_kN"), "muros": ("muro", "P_kN"),
           "vigas": ("viga", "My_kNm"), "reacciones": ("reac", None)}.get(modo)

    if modo == "resumen":
        cabecera("RESUMEN DEL ANÁLISIS — EDIFICIO COMPLETO")
        col = sorted([e for e in elementos if e["type"] == "columna"],
                     key=lambda e: abs(e["P_kN"]), reverse=True)
        muro = sorted([e for e in elementos if e["type"] == "muro"],
                      key=lambda e: abs(e["P_kN"]), reverse=True)
        viga = sorted([e for e in elementos if e["type"] == "viga"],
                      key=lambda e: e["My_kNm"], reverse=True)
        total_rz = 0.0
        if os.path.exists(REA):
            total_rz = leer(REA)["suma_reacciones"]["Fz"]
        print(f"Nº elementos            : {len(elementos)}")
        print(f"ΣRz (base)              : {total_rz:.1f} kN")
        c = col[0]
        print(f"Columna más cargada     : tag={c['elementTag']} "
              f"P={c['P_kN']:.1f} kN  ({c['descripcion']})")
        m = muro[0]
        print(f"Muro más cargado        : tag={m['elementTag']} "
              f"P={m['P_kN']:.1f} kN  ({m['descripcion']})")
        v = viga[0]
        print(f"Viga mayor momento      : tag={v['elementTag']} "
              f"My={v['My_kNm']:.1f} kN·m  ({v['descripcion']})")
        print()
        print("Sugerencias: python ver_resultados.py columnas | vigas | muros | reacciones [N]")
        return

    if modo == "reacciones":
        cabecera("REACCIONES EN LA BASE")
        rea = leer(REA)
        print(f"  {'nodo':>5}  {'X (m)':>8}  {'Y (m)':>8}  {'Fx kN':>8}  {'Fy kN':>8}"
              f"  {'Fz kN':>8}   descripción")
        for r in rea["reacciones"]:
            print(f"  {r['nodeTag']:>5}  {r['x_cm']/100:>8.2f}  {r['y_cm']/100:>8.2f}"
                  f"  {r['R_kn']['Fx']:>8.2f}  {r['R_kn']['Fy']:>8.2f}"
                  f"  {r['R_kn']['Fz']:>8.2f}   {r['descripcion']}")
        s = rea["suma_reacciones"]
        print(f"  Σ  Fx={s['Fx']:+.2f}  Fy={s['Fy']:+.2f}  Fz={s['Fz']:.2f} kN")
        return

    if key is None:
        print("Modo no reconocido.")
        return

    tipo, clave_ord = key
    titulos = {"columna": "COLUMNAS MÁS CARGADAS (por P)",
               "muro": "MUROS MÁS CARGADOS (por P)",
               "viga": "VIGAS DE MAYOR MOMENTO (por My)"}
    filtrados = [e for e in elementos if e["type"] == tipo]
    ordenados = sorted(filtrados, key=lambda e: abs(e[clave_ord]), reverse=True)
    cabecera(titulos[tipo] + f"  (top {min(top, len(ordenados))})")
    listar(ordenados, clave_ord, titulos[tipo], top)


if __name__ == "__main__":
    main()
