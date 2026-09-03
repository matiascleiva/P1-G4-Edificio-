#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera el documento 'DOCUMENTO_EDIFICIO.md' con el detalle completo de cada
elemento del edificio y sus esfuerzos, a partir de los JSON producidos por
model_edificio.py.

Datos fuente (misma carpeta):
  - secciones_verticales.json          (materiales + secciones)
  - elementos_verticales.json          (columnas/muros: posiciones, secciones)
  - fundaciones.json                   (nodos base + apoyos)
  - vigas_tributarias.json             (vigas: longitud, área tributaria)
  - cargas_piso.json                   (cargas de piso, qG)
  - resultados_fuerzas_internas_edificio.json  (esfuerzos por elemento)
  - reacciones_base_edificio.json      (reacciones por nodo base)

Uso:
    python generar_documento_edificio.py
"""
import json
import os

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8")

RAIZ = os.path.dirname(os.path.abspath(__file__))
NIVEL_NOMBRE = {1: "1° Subterráneo", 2: "1º Piso", 3: "2º Piso",
                4: "3º Piso", 5: "4º Piso"}
Z_NIVEL = {k: round(k * 3.96, 2) for k in range(1, 6)}
H_PISO = 3.96


def leer(r):
    with open(os.path.join(RAIZ, r), encoding="utf-8") as f:
        return json.load(f)


def fmt(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def parse_nivel(desc):
    if "nivel " in desc:
        try:
            return int(desc.split("nivel ")[-1])
        except ValueError:
            return None
    return None


def build():
    secc = leer("secciones_verticales.json")
    elem = leer("elementos_verticales.json")
    fund = leer("fundaciones.json")
    vigas = leer("vigas_tributarias.json")["vigas"]
    carga = leer("cargas_piso.json")
    ints = leer("resultados_fuerzas_internas_edificio.json")["elementos"]
    rea = leer("reacciones_base_edificio.json")

    materiales = {m["matTag"]: m for m in secc["materiales"]}
    secciones = {s["sectionTag"]: s for s in secc["secciones"]}

    L = []
    A = L.append
    A("# Documento Técnico del Edificio — Modelo Estructural Completo\n")

    # ---------------- 1. GENERAL ----------------
    A("## 1. Resumen general\n")
    A("Edificio de concreto armado modelado en 3D (OpenSeesPy, `ndm=3, ndf=6`), "
      "con diafragmas rígidos por nivel y análisis estático gravitacional.\n")
    A("| Parámetro | Valor |")
    A("|---|---|")
    A(f"| Niveles de losa | 5 (Subterráneo + 4 pisos) |")
    A(f"| Altura de entrepiso | {fmt(H_PISO, 2)} m |")
    A("| Cotas de losa (Z) | " +
      ", ".join(f"k={k}: {fmt(z, 2)} m" for k, z in Z_NIVEL.items()) + " |")
    A(f"| Área de losa por nivel (A_piso) | {fmt(carga['a_piso_m2'])} m² |")
    A(f"| Carga superficial total qG | {fmt(carga['qG_kN_m2'])} kN/m² |")
    A("| Carga gravitatoria total (ΣRz) | "
      f"{fmt(rea['suma_reacciones']['Fz'])} kN |")
    A(f"| Nº columnas por nivel | {sum(1 for e in elem if e['type']=='columna')} |")
    A(f"| Nº muros por nivel | {sum(1 for e in elem if e['type']=='muro')} |")
    A(f"| Nº vigas por nivel | {len(vigas)} |")
    A(f"| Elementos con esfuerzos exportados | {len(ints)} "
      f"(165 muros + 90 columnas + 135 vigas) |")
    A("")

    # ---------------- 2. MATERIALES ----------------
    A("## 2. Materiales\n")
    A("| Mat | Material | fc [MPa] | E [MPa] | ν | G [MPa] | γ [kN/m³] |")
    A("|---|---|---|---|---|---|---|")
    A("| 1 | Hormigón G35 (sin armadura) | 35 | "
      f"{fmt(27805600/1000)} | 0,20 | {fmt(11585700/1000)} | 24 | |")
    A("")

    # ---------------- 3. SECCIONES ----------------
    A("## 3. Secciones\n")
    A("| Tag | Nombre | Tipo | b [m] | h [m] | t/L | A [m²] | Iy [m⁴] | Iz [m⁴] | J [m⁴] |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for tag, s in sorted(secciones.items()):
        b = s.get("b_m", "-"); h = s.get("h_m", "-")
        t = s.get("t_m") if s.get("t_m") is not None else s.get("L_m", "-")
        A(f"| {s['sectionTag']} | {s['nombre']} | {s['tipo']} | "
          f"{fmt(b) if b!='-' else '-'} | {fmt(h) if h!='-' else '-'} | "
          f"{fmt(t) if t!='-' else '-'} | {fmt(s['A_m2'],3)} | "
          f"{fmt(s['Iy_m4'],4)} | {fmt(s['Iz_m4'],4)} | {fmt(s['J_m4'],4)} |")
    A("")

    # ---------------- 4. CARGAS ----------------
    A("## 4. Cargas de piso\n")
    A(f"| Concepto | Valor |")
    A("|---|---|")
    A(f"| Espesor de losa | {fmt(carga['losa']['espesor_m'],2)} m |")
    A(f"| Peso propio losa (e=15 cm) | {fmt(carga['losa']['pp_losa_kN_m2'])} kN/m² |")
    A(f"| Peso muerto adicional | {fmt(carga['cargas']['pm_adic_kN_m2'])} kN/m² "
      f"({int(carga['cargas']['pm_adic_kg_m2'])} kg/m²) |")
    A(f"| Sobrecarga de uso | {fmt(carga['cargas']['sc_kN_m2'])} kN/m² "
      f"({int(carga['cargas']['sc_kg_m2'])} kg/m²) |")
    A(f"| **Carga total qG** | **{fmt(carga['qG_kN_m2'])} kN/m²** |")
    A(f"| Área tributaria total (Σ) | {fmt(sum(v['area_trib_m2'] for v in vigas),2)} m² "
      f"(= A_piso) |")
    A("")

    # ---------------- 5. COLUMNAS ----------------
    cols = [e for e in elem if e["type"] == "columna"]
    A("## 5. Columnas (por nivel)\n")
    A(f"Sección única: **{secciones[100]['nombre']}** (70×70 cm). "
      "Cada columna es continua de base a losa, con un tramo `elasticBeamColumn` "
      "por nivel.\n")
    A("| Nivel | Tag elem. | Posición (X,Y) [m] | Sección | P [kN] | Vy [kN] | Vz [kN] | My [kN·m] | Mz [kN·m] |")
    A("|---|---|---|---|---|---|---|---|---|")
    for c in cols:
        base = c["iNode"]
        fx = next((f for f in fund if f["nodeTag"] == base), None)
        pos = f"({fmt(fx['x']/100,2)}, {fmt(fx['y']/100,2)})" if fx else "-"
        desc = c["descripcion"]
        for k in range(1, 6):
            etag = 10000 + k * 1000 + base
            s = next((o for o in ints if o["elementTag"] == etag), None)
            if not s:
                continue
            A(f"| {NIVEL_NOMBRE[k]} | {etag} | {pos} | {secciones[100]['nombre']} | "
              f"{fmt(s['P_kN'])} | {fmt(s['Vy_kN'])} | {fmt(s['Vz_kN'])} | "
              f"{fmt(s['My_kNm'])} | {fmt(s['Mz_kNm'])} |")
    A("")

    # ---------------- 6. MUROS ----------------
    muros = [e for e in elem if e["type"] == "muro"]
    A("## 6. Muros (por nivel)\n")
    A(f"Sección única: **{secciones[200]['nombre']}** (espesor 0,20 m, L=1,0 m). "
      "La rigidez real del núcleo se representa con esta sección equivalente por "
      "tramo y nivel.\n")
    A("| Nivel | Tag elem. | Posición (X,Y) [m] | Sección | P [kN] | Vy [kN] | Vz [kN] | My [kN·m] | Mz [kN·m] |")
    A("|---|---|---|---|---|---|---|---|---|")
    for m in muros:
        base = m["iNode"]
        fx = next((f for f in fund if f["nodeTag"] == base), None)
        pos = f"({fmt(fx['x']/100,2)}, {fmt(fx['y']/100,2)})" if fx else "-"
        for k in range(1, 6):
            etag = 10000 + k * 1000 + base
            s = next((o for o in ints if o["elementTag"] == etag), None)
            if not s:
                continue
            A(f"| {NIVEL_NOMBRE[k]} | {etag} | {pos} | {secciones[200]['nombre']} | "
              f"{fmt(s['P_kN'])} | {fmt(s['Vy_kN'])} | {fmt(s['Vz_kN'])} | "
              f"{fmt(s['My_kNm'])} | {fmt(s['Mz_kNm'])} |")
    A("")

    # ---------------- 7. VIGAS ----------------
    A("## 7. Vigas (por nivel)\n")
    A(f"Sección única: **{secciones[300]['nombre']}** (60×80 cm). "
      "Las vigas se cargan con qG × área tributaria / longitud, más la carga de "
      "los voladizos en vigas de borde.\n")

    nX = len([v for v in vigas if v["dir"] == "X"])
    for k in range(1, 6):
        A(f"\n### Nivel {k} — {NIVEL_NOMBRE[k]} (Z = {fmt(Z_NIVEL[k])} m)\n")
        A("| Tag | Dir | L [m] | A_trib [m²] | My [kN·m] | Mz [kN·m] | Vz [kN] | P [kN] |")
        A("|---|---|---|---|---|---|---|---|")
        for idx, v in enumerate(vigas):
            grp = "X" if v["dir"] == "X" else "Y"
            base_e = 20000 if grp == "X" else 30000
            i_grp = idx if grp == "X" else (idx - nX)
            etag = base_e + k * 100 + i_grp
            s = next((o for o in ints if o["elementTag"] == etag), None)
            if not s:
                continue
            A(f"| {etag} | {v['dir']} | {fmt(v['longitud_m'])} | "
              f"{fmt(v['area_trib_m2'],2)} | {fmt(s['My_kNm'])} | "
              f"{fmt(s['Mz_kNm'])} | {fmt(s['Vz_kN'])} | {fmt(s['P_kN'])} |")
    A("")

    # ---------------- 8. REACCIONES ----------------
    A("## 8. Reacciones en la base\n")
    A("| Nodo | X [m] | Y [m] | Fx [kN] | Fy [kN] | Fz [kN] | Descripción |")
    A("|---|---|---|---|---|---|---|")
    for r in rea["reacciones"]:
        A(f"| {r['nodeTag']} | {fmt(r['x_cm']/100,2)} | {fmt(r['y_cm']/100,2)} | "
          f"{fmt(r['R_kn']['Fx'])} | {fmt(r['R_kn']['Fy'])} | {fmt(r['R_kn']['Fz'])} | "
          f"{r['descripcion']} |")
    A("")
    s = rea["suma_reacciones"]
    A("| **Σ** | | | "
      f"**{fmt(s['Fx'])}** | **{fmt(s['Fy'])}** | **{fmt(s['Fz'])}** | |")
    A("")

    # ---------------- 9. VALORES CRÍTICOS ----------------
    A("## 9. Valores máximos (envolvente)\n")
    col_p = [o for o in ints if o["type"] == "columna"]
    muro_p = [o for o in ints if o["type"] == "muro"]
    viga_m = [o for o in ints if o["type"] == "viga"]
    cmax = max(col_p, key=lambda o: abs(o["P_kN"]))
    mmax = max(muro_p, key=lambda o: abs(o["P_kN"]))
    vmax = max(viga_m, key=lambda o: o["My_kNm"])
    A("| Ítem | Valor | Elemento |")
    A("|---|---|---|")
    A(f"| Columna más cargada | P = {fmt(cmax['P_kN'])} kN | {cmax['descripcion']} |")
    A(f"| Muro más cargado | P = {fmt(mmax['P_kN'])} kN | {mmax['descripcion']} |")
    A(f"| Viga de mayor momento | My = {fmt(vmax['My_kNm'])} kN·m | {vmax['descripcion']} |")
    A("")
    A("---\n*Documento generado automáticamente a partir del modelo "
      "`model_edificio.py` (OpenSeesPy).*")

    ruta = os.path.join(RAIZ, "DOCUMENTO_EDIFICIO.md")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("Documento generado:", ruta, f"({len(L)} líneas)")


if __name__ == "__main__":
    build()
