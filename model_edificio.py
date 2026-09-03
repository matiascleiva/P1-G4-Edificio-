"""
Modelación estructural COMPLETA del edificio en 3D con OpenSeesPy (ndm=3, ndf=6).

Extiende el modelo del 1° Subterráneo (model_fundaciones.py) a los N niveles del
edificio, apilando la misma grilla (18 columnas + 33 muros + 27 vigas por nivel).

Esquema vertical (CUADRO DE NIVELES, plano 2017-67-500; elevaciones 300 vacías):
  - Entrepiso h = 3.96 m (valor consistente con el subterráneo ya modelado).
  - 5 niveles de losa/diafragma: Subterráneo + 4 pisos (1º a 4º según escaleras).
      k=1 Subterráneo  Z= 3.96
      k=2 1º Piso      Z= 7.92
      k=3 2º Piso      Z=11.88
      k=4 3º Piso      Z=15.84
      k=5 4º Piso      Z=19.80
  Las columnas y muros son CONTINUOS desde la base (Z=0) hasta la última losa,
  subdivididos en N tramos por elasticBeamColumn (un tramo por nivel) para
  conectarse con las vigas de cada piso. Cada nivel tiene su propio diafragma
  rígido (nodo maestro en el centro de masa).

Esquema de tags (sin colisiones):
  - Nodo base          : a.nodeTag                    (1..51)
  - Nodo losa nivel k  : 1000 + (k-1)*100 + a.nodeTag (1001..1051, 1101.., ...)
  - Nodo maestro nivel k : 9500 + k                   (9501..9505)
  - Elemento vertical (tramo k, apoyo a): 10000 + k*1000 + a.nodeTag
  - Elemento viga X nivel k (índice i): 20000 + k*100 + i
  - Elemento viga Y nivel k (índice j): 30000 + k*100 + j

Salidas:
  - reacciones_base_edificio.json   (reacciones en la base, para Unity)
  - resultados_fuerzas_internas_edificio.json (esfuerzos por elemento, para Unity)
  - modelo_edificio_geometria.json  (nodos + elementos por nivel, para visor 3D/Unity)

Uso:
    python model_edificio.py

Requiere: openseespy
"""
import json
import os
import sys

from openseespy.opensees import (
    algorithm, analyze, analysis, constraints, eleLoad, eleResponse, element,
    fix, geomTransf, integrator, model, node, nodeReaction, numberer, reactions,
    rigidDiaphragm, section, system, timeSeries, uniaxialMaterial, pattern, wipe,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = os.path.dirname(os.path.abspath(__file__))
FUNDACIONES = os.path.join(RAIZ, "fundaciones.json")
SECCIONES = os.path.join(RAIZ, "secciones_verticales.json")
ELEMENTOS = os.path.join(RAIZ, "elementos_verticales.json")
CARGAS = os.path.join(RAIZ, "cargas_piso.json")
VIGAS = os.path.join(RAIZ, "vigas_tributarias.json")

H_PISO = 3.96                 # altura de entrepiso (m)
N_NIVELES = 5                 # subterráneo + 4 pisos
SECTION_VIGA = 300
TRANSF_VERTICAL = 1
TRANSF_HORIZONTAL = 2


def z_nivel(k):
    """Cota de la losa del nivel k (k=1..N)."""
    return k * H_PISO


def tag_losa(k, base):
    """Nodo de losa del nivel k para el apoyo base 'a'."""
    return 1000 + (k - 1) * 100 + base


def tag_master(k):
    return 9500 + k


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def definir_materiales(sec):
    for mat in sec["materiales"]:
        uniaxialMaterial("Elastic", mat["matTag"], mat["E_kPa"])
    for s in sec["secciones"]:
        section("Elastic", s["sectionTag"], s["E_kPa"], s["A_m2"], s["Iz_m4"],
                s["Iy_m4"], s["G_kPa"], s["J_m4"])


def construir_geometria(apoyos, elementos, vigas, cm):
    """Crea nodos + elementos + diafragmas de todos los niveles.

    Devuelve datos de geometría para el visor/Unity y las listas de nodos
    superiores por nivel (usadas para diafragma y reportes).
    """
    # Nodos base (fundación) con apoyos
    for a in apoyos:
        node(a["nodeTag"], a["x"] / 100.0, a["y"] / 100.0, 0.0)
        fix(a["nodeTag"], *a["restraints"])

    # Nodos de losa de cada nivel + nodos maestro
    losas_por_nivel = {}
    for k in range(1, N_NIVELES + 1):
        zn = z_nivel(k)
        for a in apoyos:
            node(tag_losa(k, a["nodeTag"]), a["x"] / 100.0, a["y"] / 100.0, zn)
        node(tag_master(k), cm[0], cm[1], zn)
        fix(tag_master(k), 0, 0, 1, 1, 1, 0)  # fija Uz,Rx,Ry del master
        losas_por_nivel[k] = [tag_losa(k, a["nodeTag"]) for a in apoyos]

    # Transformaciones geométricas
    geomTransf("Linear", TRANSF_VERTICAL, 1.0, 0.0, 0.0)     # verticales
    geomTransf("Linear", TRANSF_HORIZONTAL, 0.0, 0.0, 1.0)   # vigas horizontales

    # Elementos verticales: por cada apoyo, un tramo por nivel (continuo)
    n_vert = 0
    for a in elementos:
        base = a["iNode"]
        for k in range(1, N_NIVELES + 1):
            ini = base if k == 1 else tag_losa(k - 1, base)
            fin = tag_losa(k, base)
            etag = 10000 + k * 1000 + base
            element("elasticBeamColumn", etag, ini, fin, a["sectionTag"],
                    TRANSF_VERTICAL)
            n_vert += 1

    # Vigas horizontales en CADA nivel + carga repartida
    n_vig = 0
    vigas_ids = []
    for k in range(1, N_NIVELES + 1):
        off = (k - 1) * 100
        for idx, v in enumerate(vigas):
            ini = v["iNode"] + off
            fin = v["jNode"] + off
            grp = "X" if v["dir"] == "X" else "Y"
            base_e = 20000 if grp == "X" else 30000
            # índice dentro de su grupo
            i_grp = idx if grp == "X" else (idx - len([x for x in vigas if x['dir'] == 'X']))
            etag = base_e + k * 100 + i_grp
            element("elasticBeamColumn", etag, ini, fin, SECTION_VIGA,
                    TRANSF_HORIZONTAL)
            vigas_ids.append(etag)
            n_vig += 1
    return losas_por_nivel, n_vert, n_vig, vigas_ids


def definir_voladizos():
    """Config de los voladizos detectados en planos de elevación (escala DXF
    100 uds = 1 m). Cada dict describe un voladizo y cómo se suma a la geometría
    de la losa (campos 'xmin/xmax/ymin/ymax' = desplazamiento de la esquina
    correspondiente de la huella base por voladizo) y a la carga de la viga de
    borde (campos 'grupo'/'i_grp'/'ancho_m').
      - 'k'     : nivel de losa sobre el que actúa
      - 'grupo' : 'X' o 'Y' -> tipo de viga de borde que soporta el voladizo
      - 'i_grp' : índices (dentro de su grupo) de las vigas de borde
      - 'ancho_m': saliente del voladizo (ancho de losa volada)
      - 'geometria': diccionario con el lado que se extiende (xmax->+X, etc.)
    """
    return [
        # ÚLTIMO PISO (piso 4 = k=5), dirección +X hacia extremo I' (X=53.021).
        # Plano 300 (fachada 1-1'): las vigas-Y del borde I' (índices 10,11)
        #   reciben la losa volada de 5.85 m.
        {"k": 5, "grupo": "Y", "i_grp": [10, 11], "ancho_m": 5.85,
         "geometria": {"xmax": 5.85},
         "origen": "Plano 2017-67-300 - voladizo último piso (dir X/I')"},
        # PISO 2 (k=3), dirección +Y hacia eje 1 (Y=64.101, frente): 4.1 m.
        # Plano 306 (fachada F-F'): vigas-X de la fila frontal (i_grp 10..14).
        {"k": 3, "grupo": "X", "i_grp": list(range(10, 15)), "ancho_m": 4.1,
         "geometria": {"ymax": 4.1},
         "origen": "Plano 2017-67-306 - voladizo piso 2 (dir Y hacia eje 1)"},
        # PISO 2 (k=3), dirección -Y hacia eje 3 (Y=47.951, fondo): 0.8 m.
        # Vigas-X de la fila trasera (i_grp 0..4).
        {"k": 3, "grupo": "X", "i_grp": list(range(0, 5)), "ancho_m": 0.8,
         "geometria": {"ymin": -0.8},
         "origen": "Plano 2017-67-306 - voladizo piso 2 (dir Y hacia eje 3)"},
    ]


def huella_losa(voladizos, k):
    """Polígono 3D de la losa del nivel k (rectángulo) con los voladizos
    correspondientes. Devuelve lista de 4 esquinas en orden: SW, SE, NE, NW.
    Coordenadas en metros (misma convención que el modelo)."""
    # Huella base del footprint (grilla regular de columnas/muros)
    xmin, xmax = 8.021, 53.021
    ymin, ymax = 47.951, 64.101
    for vol in voladizos:
        if vol["k"] == k:
            g = vol["geometria"]
            if "xmax" in g:
                xmax += g["xmax"]
            if "xmin" in g:
                xmin += g["xmin"]
            if "ymax" in g:
                ymax += g["ymax"]
            if "ymin" in g:
                ymin += g["ymin"]
    z = z_nivel(k)
    return [
        {"x": xmin, "y": ymin, "z": z},  # SW
        {"x": xmax, "y": ymin, "z": z},  # SE
        {"x": xmax, "y": ymax, "z": z},  # NE
        {"x": xmin, "y": ymax, "z": z},  # NW
    ]


def etiqueta_viga(vigas, idx, k):
    """Tag del elemento viga según su índice en la lista y el nivel (coherente
    con construir_geometria y salida_esfuerzos)."""
    grp = "X" if vigas[idx]["dir"] == "X" else "Y"
    base_e = 20000 if grp == "X" else 30000
    nX = len([x for x in vigas if x["dir"] == "X"])
    i_grp = idx if grp == "X" else (idx - nX)
    return base_e + k * 100 + i_grp


def indice_grupo(vigas, idx):
    """Índice del elemento dentro de su grupo (X o Y)."""
    grp = "X" if vigas[idx]["dir"] == "X" else "Y"
    if grp == "X":
        return idx
    nX = len([x for x in vigas if x["dir"] == "X"])
    return idx - nX


def aplicar_cargas(vigas):
    """Aplica la carga de piso (qG * A_trib/L) a las vigas de cada nivel,
    más la carga adicional de los VOLADIZOS detectados en los planos de
    elevación (ver voladizos.json)."""
    qG = leer(CARGAS)["qG_kN_m2"]
    # CONFIG VOLADIZOS (del análisis de planos, escala DXF 100 uds = 1 m): ver
    # definir_voladizos() para la interpretación de cada campo.
    voladizos = definir_voladizos()

    timeSeries("Linear", 100)
    pattern("Plain", 100, 100)
    for k in range(1, N_NIVELES + 1):
        for idx, v in enumerate(vigas):
            w = qG * v["area_trib_m2"] / v["longitud_m"]
            etag = etiqueta_viga(vigas, idx, k)
            eleLoad("-ele", etag, "-type", "beamUniform", 0.0, -w)

    # Carga extra por voladizo sobre las vigas de borde correspondientes
    for vol in voladizos:
        w_extra = qG * vol["ancho_m"]
        for i_grp in vol["i_grp"]:
            grp = vol["grupo"]
            if grp == "X":
                etag = 20000 + vol["k"] * 100 + i_grp
            else:
                etag = 30000 + vol["k"] * 100 + i_grp
            eleLoad("-ele", etag, "-type", "beamUniform", 0.0, -w_extra)
    return voladizos


def diafragmas(losas_por_nivel):
    """Aplica rigidDiaphragm(3, master, *slaves) en cada nivel."""
    for k in range(1, N_NIVELES + 1):
        rigidDiaphragm(3, tag_master(k), *losas_por_nivel[k])


def configurar_analisis():
    system("BandSPD")
    numberer("RCM")
    constraints("Transformation")
    algorithm("Newton")
    integrator("LoadControl", 1.0)
    analysis("Static")


def salida_reacciones(apoyos):
    reactions()
    salida, suma = [], [0.0] * 6
    for a in apoyos:
        reac = [nodeReaction(a["nodeTag"], i + 1) for i in range(6)]
        suma = [s + r for s, r in zip(suma, reac)]
        salida.append({
            "nodeTag": a["nodeTag"], "x_cm": a["x"], "y_cm": a["y"], "z_cm": 0.0,
            "R_kn": {"Fx": round(reac[0], 3), "Fy": round(reac[1], 3),
                     "Fz": round(reac[2], 3), "Mx": round(reac[3], 3),
                     "My": round(reac[4], 3), "Mz": round(reac[5], 3)},
            "descripcion": a["descripcion"],
        })
    ruta = os.path.join(RAIZ, "reacciones_base_edificio.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {"tipo": "Reacciones en base - edificio completo",
                      "n_niveles": N_NIVELES, "h_piso_m": H_PISO},
            "reacciones": salida,
            "suma_reacciones": {"Fx": round(suma[0], 3), "Fy": round(suma[1], 3),
                                "Fz": round(suma[2], 3), "Mx": round(suma[3], 3),
                                "My": round(suma[4], 3), "Mz": round(suma[5], 3)},
        }, f, ensure_ascii=False, indent=2)
    return ruta, suma


def salida_esfuerzos(apoyos, elementos, vigas):
    """Extrae esfuerzos por elemento (eleResponse localForces) y exporta JSON."""
    out = []

    def add(tag, tipo, desc, seccion, iNode, jNode):
        f = eleResponse(tag, "localForces")
        vi = {"P": f[0], "Vy": f[1], "Vz": f[2], "My": f[4], "Mz": f[5]}
        vj = {"P": f[6], "Vy": f[7], "Vz": f[8], "My": f[10], "Mz": f[11]}
        out.append({
            "elementTag": tag, "type": tipo, "iNode": iNode, "jNode": jNode,
            "sectionTag": seccion, "descripcion": desc,
            "P_kN": round(vi["P"], 3), "Vy_kN": round(vi["Vy"], 3),
            "Vz_kN": round(vi["Vz"], 3),
            "My_kNm": round(max(abs(vi["My"]), abs(vj["My"])), 3),
            "Mz_kNm": round(max(abs(vi["Mz"]), abs(vj["Mz"])), 3),
        })

    for k in range(1, N_NIVELES + 1):
        for a in elementos:
            etag = 10000 + k * 1000 + a["iNode"]
            ini = a["iNode"] if k == 1 else tag_losa(k - 1, a["iNode"])
            fin = tag_losa(k, a["iNode"])
            add(etag, a["type"], f"{a['descripcion']} · nivel {k}",
                a["sectionTag"], ini, fin)
    nX = len([v for v in vigas if v["dir"] == "X"])
    for k in range(1, N_NIVELES + 1):
        for idx, v in enumerate(vigas):
            grp = "X" if v["dir"] == "X" else "Y"
            base_e = 20000 if grp == "X" else 30000
            i_grp = idx if grp == "X" else (idx - nX)
            etag = base_e + k * 100 + i_grp
            ini = v["iNode"] + (k - 1) * 100
            fin = v["jNode"] + (k - 1) * 100
            add(etag, "viga", f"Viga dir {v['dir']} L={v['longitud_m']}m · nivel {k}",
                SECTION_VIGA, ini, fin)
    ruta = os.path.join(RAIZ, "resultados_fuerzas_internas_edificio.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {"tipo": "Esfuerzos internos - edificio completo",
                      "respuesta": "eleResponse(tag,'localForces')",
                      "n_elementos": len(out)},
            "elementos": out,
        }, f, ensure_ascii=False, indent=2)
    return ruta, out


def salida_geometria(apoyos, losas_por_nivel):
    """Exporta nodos + losas (huella real con voladizos) por nivel para visor
    3D / Unity."""
    voladizos = definir_voladizos()
    geom = []
    for a in apoyos:
        geom.append({"nodeTag": a["nodeTag"], "x": a["x"] / 100.0,
                     "y": a["y"] / 100.0, "z": 0.0, "tipo": "base"})
        for k in range(1, N_NIVELES + 1):
            geom.append({"nodeTag": tag_losa(k, a["nodeTag"]),
                         "x": a["x"] / 100.0, "y": a["y"] / 100.0,
                         "z": z_nivel(k), "tipo": f"losa_nivel_{k}"})

    losas = []
    for k in range(1, N_NIVELES + 1):
        pol = huella_losa(voladizos, k)
        nombres = {1: "1° Subterráneo", 2: "1º Piso", 3: "2º Piso",
                   4: "3º Piso", 5: "4º Piso"}
        kvols = [v for v in voladizos if v["k"] == k]
        losas.append({
            "nivel": k, "nombre": nombres.get(k, str(k)),
            "z_m": z_nivel(k), "esquinas": pol,
            "voladizos": [{"ancho_m": v["ancho_m"], "origen": v["origen"]}
                          for v in kvols],
        })

    ruta = os.path.join(RAIZ, "modelo_edificio_geometria.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {"n_niveles": N_NIVELES, "h_piso_m": H_PISO,
                      "z_niveles_m": {k: z_nivel(k) for k in range(1, N_NIVELES + 1)}},
            "nodos": geom,
            "losas": losas,
        }, f, ensure_ascii=False, indent=2)
    return ruta


def main():
    wipe()
    model("basic", "-ndm", 3, "-ndf", 6)
    apoyos = leer(FUNDACIONES)
    sec = leer(SECCIONES)
    elementos = leer(ELEMENTOS)
    vigas = leer(VIGAS)["vigas"]

    definir_materiales(sec)
    # Centro de masa (mismo para todos los niveles: planta uniforme)
    xs = [a["x"] / 100.0 for a in apoyos]
    ys = [a["y"] / 100.0 for a in apoyos]
    cm = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    qG = leer(CARGAS)["qG_kN_m2"]
    losas_por_nivel, n_vert, n_vig, vig_ids = construir_geometria(
        apoyos, elementos, vigas, cm)
    voladizos = aplicar_cargas(vigas)
    diafragmas(losas_por_nivel)

    print("=" * 78)
    print("MODELO EDIFICIO COMPLETO (N niveles)")
    print(f"  Niveles de losa : {N_NIVELES}  (Subterráneo + 4 pisos)")
    for k in range(1, N_NIVELES + 1):
        nombre = {1: "1° Subterráneo", 2: "1º Piso", 3: "2º Piso",
                  4: "3º Piso", 5: "4º Piso"}[k]
        print(f"    nivel {k} ({nombre:>13})  Z = {z_nivel(k):.2f} m")
    print(f"  Entrepiso h = {H_PISO} m")
    print(f"  Centro de masa (m) : X={cm[0]:.2f}, Y={cm[1]:.2f}")
    print(f"  Elementos verticales (tramos) : {n_vert}  "
          f"({len(elementos)} apoyos × {N_NIVELES} niveles)")
    print(f"  Vigas horizontales en total    : {n_vig}  ({len(vigas)} × {N_NIVELES})")
    if voladizos:
        print("  Voladizos considerados (carga extra sobre vigas de borde):")
        names = {1: "Subterráneo", 2: "1º Piso", 3: "2º Piso",
                 4: "3º Piso", 5: "4º Piso"}
        seen = {}
        for vol in voladizos:
            key = (vol["k"], vol["grupo"], vol["ancho_m"])
            seen[key] = vol
        for (k, grp, ancho), vol in sorted(seen.items()):
            extra = qG * ancho
            print(f"    - {names[k]} (k={k}) · {vol['origen'].split(' - ')[-1]}"
                  f": {extra:.1f} kN/m")
    print("=" * 78)

    configurar_analisis()
    ok = analyze(1)
    print(f"Análisis estático gravitacional -> "
          f"{'OK (convergió)' if ok == 0 else f'FALLÓ ({ok})'}")
    if ok == 0:
        ruta_r, suma = salida_reacciones(apoyos)
        print(f"  Reacciones base : {ruta_r}")
        print(f"  ΣRz = {suma[2]:.2f} kN (gravitatorio total)")
        print(f"  ΣFx = {suma[0]:.3f}  ΣFy = {suma[1]:.3f}  "
              f"(equilibrio horizontal, ~0)")
        ruta_i, out = salida_esfuerzos(apoyos, elementos, vigas)
        print(f"  Esfuerzos internos : {ruta_i}  ({len(out)} elementos)")
        # validación: columna más cargada y viga con mayor momento
        col = [o for o in out if o["type"] == "columna"]
        vga = [o for o in out if o["type"] == "viga"]
        cmax = max(col, key=lambda o: abs(o["P_kN"]))
        vmax = max(vga, key=lambda o: o["My_kNm"])
        print(f"  Columna más cargada: tag={cmax['elementTag']} P={cmax['P_kN']:.1f} kN"
              f"  ({cmax['descripcion']})")
        print(f"  Viga mayor momento: tag={vmax['elementTag']} My={vmax['My_kNm']:.1f} kN·m"
              f"  ({vmax['descripcion']})")
        ruta_g = salida_geometria(apoyos, losas_por_nivel)
        print(f"  Geometría para visor/Unity : {ruta_g}")


if __name__ == "__main__":
    main()
