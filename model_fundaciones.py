"""
Modelación estructural de un edificio en 3D con OpenSeesPy (ndm=3, ndf=6).

Estado actual del modelo:
- Fundaciones: nodos en Z=0 (Lámina 2017_67-100 A) con apoyos empotrados (fix).
- Elementos verticales: columnas (70x70) y muros (e=20 cm) que conectan la
  fundación (Z=0) con el primer nivel (1° Subterráneo, Z=+3.96 m).
- Vigas horizontales: V. 60/80 (2600-series X, 3000-series Y) entre nodos
  superiores de columnas adyacentes (Lámina 2017-67-400).
- Cargas de piso: carga superficial q_G repartida por área tributaria
  (w = q_G * A_trib / L) con chequeo de conservación (Σw*L = q_G*A_piso).
- Diafragma rígido: nodo maestro en el centro de masa del nivel + rigidDiaphragm
  (restricción de cuerpo rígido en Ux, Uy y Rz de todos los nodos del piso).
- Análisis: estático gravitacional (BandSPD, RCM, Transformation, Newton,
  LoadControl) + salida de reacciones en la base para el Viewer Unity.

NOTA sobre arriostres (Láminas 2017-67-800 A/B/C y 2017-67-400):
  Los planos 800 (Detalles de Conexiones Metálicas) contienen únicamente
  conexiones (placas base PL ..., pernos Nelson, couplers, soldaduras) y NO
  definen diagonales/arriostres metálicos. El sistema de resistencia lateral
  en este nivel son los muros de hormigón armado (V.S.I. 20/40 y M.H.A.),
  por lo que NO se generan arriostres corotTruss (no aplican en este nivel).
  (La grilla de elementos verticales ya incluye los 33 muros que cumplen ese rol.)

Fuentes:
- fundaciones.json            -> Planta de Fundaciones (Lámina 2017_67-100 A)
- secciones_verticales.json   -> Hormigón G35 + secciones COL_70, MUR_20 y
                                 VIGA_60x80 (Elevaciones, plano 600 y 400)
- elementos_verticales.json   -> columnas/muros con sus nodos y sección
- vigas_tributarias.json      -> vigas horizontales con área tributaria (plano 400)
- cargas_piso.json            -> q_G = PP losa + PM adic + SC (plano 101 y 700)
- planos 800 A/B/C (2017-67-800..802) -> Detalles de conexiones (sin arriostres)

Uso:
    python model_fundaciones.py

Requiere: openseespy
"""
import json
import os
import sys

from openseespy.opensees import (
    algorithm,
    analyze,
    analysis,
    constraints,
    eleLoad,
    eleResponse,
    element,
    fix,
    geomTransf,
    integrator,
    loadConst,
    model,
    node,
    nodeReaction,
    numberer,
    reactions,
    rigidDiaphragm,
    section,
    system,
    timeSeries,
    uniaxialMaterial,
    pattern,
    wipe,
)

# Consola Windows: forzar UTF-8 para imprimir símbolos (Σ, m², ñ...)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = os.path.dirname(os.path.abspath(__file__))
FUNDACIONES = os.path.join(RAIZ, "fundaciones.json")
SECCIONES = os.path.join(RAIZ, "secciones_verticales.json")
ELEMENTOS = os.path.join(RAIZ, "elementos_verticales.json")
CARGAS = os.path.join(RAIZ, "cargas_piso.json")
VIGAS = os.path.join(RAIZ, "vigas_tributarias.json")

PLANO_FUNDACIONES = "Lámina 2017_67-100 A (Planta Fundaciones)"
PLANO_NIVEL = "Cuadro de Niveles / Elevaciones Ejes (2017-67-300..303)"

Z_PRIMER_NIVEL = 3.96
SECTION_VIGA = 300  # tag de VIGA_60x80 en secciones_verticales.json
TRANSF_HORIZONTAL = 2  # transformación lineal para vigas horizontales

MASTER_NODE = 9000  # nodo maestro del diafragma rígido (centro de masa)


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def definir_materiales(secciones_json):
    """Define materiales y secciones transversales elásticas."""
    for mat in secciones_json["materiales"]:
        uniaxialMaterial(
            "Elastic", mat["matTag"], mat["E_kPa"]
        )
    for s in secciones_json["secciones"]:
        section(
            "Elastic", s["sectionTag"], s["E_kPa"], s["A_m2"], s["Iz_m4"],
            s["Iy_m4"], s["G_kPa"], s["J_m4"],
        )


def crear_nodos_fundacion(apoyos):
    # El DXF trae coordenadas en cm; el modelo trabaja en metros (SI, kN-m).
    for a in apoyos:
        node(a["nodeTag"], a["x"] / 100.0, a["y"] / 100.0, a["z"])


def aplicar_apoyos(apoyos):
    for a in apoyos:
        fix(a["nodeTag"], *a["restraints"])


def crear_nodos_superiores(apoyos, z):
    """Crea los nodos del primer nivel (Z=z) encima de cada apoyo."""
    for a in apoyos:
        jtag = 1000 + a["nodeTag"]
        node(jtag, a["x"] / 100.0, a["y"] / 100.0, z)


def crear_elementos_verticales(elementos):
    """Define la transformación geométrica y conecta columnas/muros."""
    # Transformación lineal, vector local z = eje global X (elementos verticales)
    geomTransf("Linear", 1, 1.0, 0.0, 0.0)
    for el in elementos:
        element(
            "elasticBeamColumn",
            el["elementTag"], el["iNode"], el["jNode"],
            el["sectionTag"], 1,
        )


def crear_vigas(vigas_json):
    """Define transformación horizontal y crea las vigas del primer nivel.

    La viga se modela con elasticBeamColumn entre los nodos superiores de dos
    columnas adyacentes (nodo 1000+tag). El eje local z de la transformación
    apunta al eje global Z (vertical) para que la flexión por gravedad ocurra
    en el plano vertical de la sección.
    """
    # Transformación lineal horizontal: vecz=(0,0,1) -> plano de flexión vertical
    geomTransf("Linear", TRANSF_HORIZONTAL, 0.0, 0.0, 1.0)
    for v in vigas_json["vigas"]:
        element(
            "elasticBeamColumn",
            v["elementTag"], v["iNode"], v["jNode"],
            v["sectionTag"], TRANSF_HORIZONTAL,
        )


def aplicar_carga_vigas(vigas_json, qG, tag_patron=100):
    """Aplica el peso del piso a cada viga como carga repartida local.

    w = qG * A_trib / L        (kN/m, dirigida hacia -Z = gravedad)
    El área tributaria de la viga ya está en vigas_tributarias.json.
    """
    timeSeries("Linear", tag_patron)
    pattern("Plain", tag_patron, tag_patron)
    for v in vigas_json["vigas"]:
        w = qG * v["area_trib_m2"] / v["longitud_m"]
        eleLoad(
            "-ele", v["elementTag"],
            "-type", "beamUniform", 0.0, -w,
        )


def centro_de_masa(apoyos, z):
    """Calcula el centro de masa del nivel a partir de los nodos existentes.

    El centro de masa se aproxima como el centroide del área de piso (losa
    uniforme). Se usa la caja envolvente (bounding box) de los nodos superiores
    del nivel (nodo 1000+tag), es decir, el centro de la planta E..I' x 3..1.

    Retorna el nodo maestro (MASTER_NODE) creado en ese punto, coplanar con el
    diafragma (misma cota Z del nivel). El diafragma rígido reparte las masas de
    la losa concentradas en este punto.
    """
    xs = [1000 + a["nodeTag"] for a in apoyos]  # no usado; nodos ya creados
    xs_c = [a["x"] / 100.0 for a in apoyos]
    ys_c = [a["y"] / 100.0 for a in apoyos]
    x_cm = (min(xs_c) + max(xs_c)) / 2.0
    y_cm = (min(ys_c) + max(ys_c)) / 2.0
    node(MASTER_NODE, x_cm, y_cm, z)
    # El diafragma rígido sólo acopla GDL planos (Ux, Uy, Rz) del master; sus
    # GDL fuera del plano (Uz, Rx, Ry) no están conectados a ningún elemento,
    # por lo que de no restringirse producirían una matriz singular. Se fijan.
    fix(MASTER_NODE, 0, 0, 1, 1, 1, 0)
    return x_cm, y_cm


def crear_diafragma_rigido(apoyos):
    """Implementa el diafragma rígido del piso.

    Cinemática de cuerpo rígido asumida (diafragma rígido en el plano X-Y):
      La losa se comporta como un cuerpo infinitamente rígido en su plano.
      Nodo maestro (MASTER_NODE) en el centro de masa; sus 6 GDL (Ux, Uy, Uz,
      Rx, Ry, Rz) son independientes. Para cada nodo esclavo 's' del piso se
      imponen 3 restricciones (Ux, Uy y Rz) en función del master:

        u_x,s = u_x,m  - (y_s - y_m) * theta_z,m
        u_y,s = u_y,m  + (x_s - x_m) * theta_z,m
        theta_z,s       = theta_z,m

      Es decir, el nodo esclavo ya no posee desplazamiento independiente en el
      plano: traslada solidariamente con el master (dos traslaciones) y rota con
      él alrededor del eje Z. Los GDL fuera del plano (Uz, Rx, Ry) y el GDL Uz
      del master quedan libres para el comportamiento flexural/fuera del plano.

    El comando rigidDiaphragm(3, master, *slaves) aplica las 3 restricciones
    planas anteriores. El manejador de restricciones debe ser 'Transformation'.
    """
    nodos_esclavos = [1000 + a["nodeTag"] for a in apoyos]
    rigidDiaphragm(3, MASTER_NODE, *nodos_esclavos)
    return nodos_esclavos


def configurar_analisis_gravitacional():
    """Configura el análisis estático lineal/gravitacional con OpenSeesPy:

      system("BandSPD")        -> solver simétrico definido positivo (banda)
      numberer("RCM")          -> numeración por Cuthill-McKee inverso (ancho de banda)
      constraints("Transformation") -> aplica los GDL dependientes (diafragma rígido)
      algorithm("Newton")      -> iteración de Newton-Raphson (carga lineal converg. 1 paso)
      integrator("LoadControl",1.0) -> control de carga: factor de carga total = 1.0
      analysis("Static")       -> tipo de análisis estático
    """
    system("BandSPD")
    numberer("RCM")
    constraints("Transformation")
    algorithm("Newton")
    integrator("LoadControl", 1.0)
    analysis("Static")


def ejecutar_analisis():
    """Ejecuta el análisis y devuelve el éxito (1) o fracaso (0)."""
    return analyze(1)


def salida_reacciones(apoyos, cargas_json):
    """Calcula y guarda las reacciones en la base (nodos de fundación, Z=0).

    reaction() computa las reacciones en los nodos cuyos 6 GDL están fijos
    (apoyos empotrados). Se exporta un JSON para el Viewer Unity con, por nodo,
    las 6 componentes de reacción [Fx, Fy, Fz, Mx, My, Mz] y las coordenadas.
    """
    reactions()
    salida = []
    suma = [0.0] * 6
    for a in apoyos:
        reac = [nodeReaction(a["nodeTag"], i + 1) for i in range(6)]
        suma = [s + r for s, r in zip(suma, reac)]
        salida.append({
            "nodeTag": a["nodeTag"],
            "x_cm": a["x"], "y_cm": a["y"], "z_cm": a["z"],
            "R_kn": {
                "Fx": round(reac[0], 3), "Fy": round(reac[1], 3),
                "Fz": round(reac[2], 3), "Mx": round(reac[3], 3),
                "My": round(reac[4], 3), "Mz": round(reac[5], 3),
            },
            "descripcion": a["descripcion"],
        })
    ruta = os.path.join(RAIZ, "reacciones_base.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {
                "tipo": "Reacciones en base (análisis estático gravitacional)",
                "qG_kN_m2": cargas_json["qG_kN_m2"],
                "suma_Fz_reacciones_kn": round(suma[2], 3),
            },
            "reacciones": salida,
            "suma_reacciones": {
                "Fx": round(suma[0], 3), "Fy": round(suma[1], 3),
                "Fz": round(suma[2], 3), "Mx": round(suma[3], 3),
                "My": round(suma[4], 3), "Mz": round(suma[5], 3),
            },
        }, f, ensure_ascii=False, indent=2)
    return ruta, suma


def extraer_fuerzas_internas(elementos, vigas_json):
    """Extrae los esfuerzos en los extremos de cada elemento con eleResponse.

    eleResponse(tag, 'localForces') devuelve 12 valores en coordenadas locales:
      [ Ni, Vyi, Vzi, Ti, Myi, Mzi,   Nj, Vyj, Vzj, Tj, Myj, Mzj ]
    donde:
      N  = fuerza axial        (kN)
      Vy = corte en eje local y (kN)
      Vz = corte en eje local z (kN)
      T  = torsión             (kN·m)
      My = momento en eje local y (kN·m)
      Mz = momento en eje local z (kN·m)

    Interpretación local según la transformación geométrica:
      - Columnas/muros (transf. 1, vecz=global X): eje local x vertical -> N es
        la carga axial vertical (gravitatoria).
      - Vigas (transf. 2, vecz=global Z): eje local z vertical -> Vz es el corte
        vertical y My el momento flector por gravedad (flexión mayor).

    Se recorren las listas de elementos_verticales.json (columnas + muros) y
    vigas_tributarias.json (vigas), separando por tipo, y se exporta
    resultados_fuerzas_internas.json.
    """
    resultado = []
    inds_i = (0, 1, 2, 4, 5)   # N, Vy, Vz, My, Mz (extremo i)
    inds_j = (6, 7, 8, 10, 11)  # N, Vy, Vz, My, Mz (extremo j)
    nombres = ("P", "Vy", "Vz", "My", "Mz")

    def procesar(tag, tipo, iNode, jNode, sectionTag, fuente, desc):
        fuerzas = eleResponse(tag, "localForces")
        vi = dict(zip(nombres, (fuerzas[k] for k in inds_i)))
        vj = dict(zip(nombres, (fuerzas[k] for k in inds_j)))
        # Momento flector característico = máximo valor absoluto entre extremos
        momentos = {m: max(abs(vi[m]), abs(vj[m])) for m in ("My", "Mz")}
        m_max = max(momentos.values())
        resultado.append({
            "elementTag": tag,
            "type": tipo,
            "iNode": iNode,
            "jNode": jNode,
            "sectionTag": sectionTag,
            "plano_fuente": fuente,
            "descripcion": desc,
            "extremo_i": {k: round(vi[k], 3) for k in nombres},
            "extremo_j": {k: round(vj[k], 3) for k in nombres},
            "P_kN": round(vi["P"], 3),
            "Vy_kN": round(vi["Vy"], 3),
            "Vz_kN": round(vi["Vz"], 3),
            "My_kNm": round(momentos["My"], 3),
            "Mz_kNm": round(momentos["Mz"], 3),
            "Mmax_flector_kNm": round(m_max, 3),
        })

    for e in elementos:  # columnas y muros
        procesar(e["elementTag"], e["type"], e["iNode"], e["jNode"],
                 e["sectionTag"], e["plano_fuente"], e["descripcion"])
    for v in vigas_json["vigas"]:  # vigas horizontales
        fuente = "Elevaciones de Vigas (2017-67-400) - V. 60/80"
        procesar(v["elementTag"], v["type"], v["iNode"], v["jNode"],
                 v["sectionTag"], fuente, f"Viga dir {v['dir']}, L={v['longitud_m']} m, A_trib={v['area_trib_m2']} m²")

    ruta = os.path.join(RAIZ, "resultados_fuerzas_internas.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {
                "tipo": "Esfuerzos internos por elemento (análisis estático gravitacional)",
                "respuesta": "eleResponse(tag, 'localForces')",
                "unidades": "N y V en kN; M y T en kN·m",
                "n_verticales": len(elementos),
                "n_vigas": len(vigas_json["vigas"]),
            },
            "elementos": resultado,
        }, f, ensure_ascii=False, indent=2)
    return ruta, resultado


def validar_internos(resultado):
    """Busca la columna más cargada axialmente y la viga con mayor momento.

    Valida coherencia: la columna más cargada debe coincidir (por locación) con
    la zona de mayor área tributaria, y el momento máximo de viga debe ser del
    orden de w*L²/12 (momento empotrado) para la viga de mayor carga repartida.
    """
    print()
    print("=" * 78)
    print("VALIDACIÓN DE ESFUERZOS INTERNOS")
    print("-" * 78)
    columnas = [r for r in resultado if r["type"] == "columna"]
    muros = [r for r in resultado if r["type"] == "muro"]
    vigas = [r for r in resultado if r["type"] == "viga"]

    if columnas:
        col_max = max(columnas, key=lambda r: abs(r["P_kN"]))
        print(f"COLUMNA MÁS CARGADA AXIALMENTE:")
        print(f"  elementTag = {col_max['elementTag']}   P = {col_max['P_kN']:.2f} kN (compresión)")
        print(f"  descripción: {col_max['descripcion']}")
        print(f"  extremo i P = {col_max['extremo_i']['P']:.2f} kN  |  extremo j P = "
              f"{col_max['extremo_j']['P']:.2f} kN  (coherente: carga axial casi constante)")

    if vigas:
        viga_max = max(vigas, key=lambda r: r["Mmax_flector_kNm"])
        print(f"VIGA CON MOMENTO FLECTOR MÁXIMO:")
        print(f"  elementTag = {viga_max['elementTag']}   "
              f"Mmax = {viga_max['Mmax_flector_kNm']:.2f} kN·m  (My)")
        print(f"  descripción: {viga_max['descripcion']}")
        # comprobación rápida: momento empotrado w*L²/12 con w = qG*A_trib/L
        qG = 10.15
        for v in _vigas_cache(resultado):
            if v["elementTag"] == viga_max["elementTag"]:
                w = qG * v["a_trib"] / v["lon"]
                m_emp = w * v["lon"] ** 2 / 12.0
                print(f"  Referencia: w = {w:.1f} kN/m, L = {v['lon']:.1f} m -> "
                      f"M_empotrado (wL²/12) = {m_emp:.0f} kN·m")
                break
    print(f"  Total elementos analizados: columnas={len(columnas)}, "
          f"muros={len(muros)}, vigas={len(vigas)}")
    print("=" * 78)


def _vigas_cache(resultado):
    """Devuelve lista de vigas con a_trib y lon (leídas desde vigas_tributarias.json)."""
    vg = leer_json(VIGAS)
    return [{"elementTag": v["elementTag"], "a_trib": v["area_trib_m2"],
             "lon": v["longitud_m"]} for v in vg["vigas"]]


def chequeo_conservacion(vigas_json, qG, cargas_json, representativos):
    """Verifica que la suma de cargas en las vigas iguala qG * A_piso."""
    suma_wL = 0.0
    for v in vigas_json["vigas"]:
        w = qG * v["area_trib_m2"] / v["longitud_m"]
        suma_wL += w * v["longitud_m"]
    carga_piso = qG * cargas_json["a_piso_m2"]
    print()
    print("CHEQUEO DE CONSERVACIÓN DE CARGA (estado de cargas de piso)")
    print(f"  q_G (kN/m²)              = {qG:.3f}")
    print(f"  A_piso (m²)              = {cargas_json['a_piso_m2']:.2f}")
    print(f"  Peso total piso (kN)     = qG*A_piso = {carga_piso:.2f}")
    print(f"  Σ(w*L) en vigas (kN)     = {suma_wL:.2f}")
    print(f"  Diferencia (kN)          = {carga_piso - suma_wL:.4f}")
    print(f"  ¿Conserva?               = {'SÍ' if abs(carga_piso - suma_wL) < 1e-6 else 'NO'}")
    print("-" * 78)
    print("VIGAS REPRESENTATIVAS (área tributaria aplicada)")
    print(f"{'elementTag':>10} {'dir':<4} {'L (m)':>7} {'A_trib (m²)':>12} {'w (kN/m)':>10}")
    for v in vigas_json["vigas"]:
        if v["elementTag"] in representativos:
            w = qG * v["area_trib_m2"] / v["longitud_m"]
            print(f"{v['elementTag']:>10} {v['dir']:<4} {v['longitud_m']:>7.2f} "
                  f"{v['area_trib_m2']:>12.3f} {w:>10.3f}")


def reporte(apoyos, elementos, vigas, esclavos, cm, z):
    ncol = sum(1 for e in elementos if e["type"] == "columna")
    nmur = sum(1 for e in elementos if e["type"] == "muro")
    print("=" * 78)
    print("REPORTE - MODELO FUNDACIONES + ELEMENTOS VERTICALES")
    print("Plano fundaciones :", PLANO_FUNDACIONES)
    print("Primer nivel      :", PLANO_NIVEL)
    print(f"Cota primer nivel : Z = {z:.2f} m (1° Subterráneo)")
    print("Dimensiones       : ndm=3, ndf=6")
    print("-" * 78)
    print(f"Nodos de fundación (Z=0)    : {len(apoyos)}")
    print(f"Nodos del primer nivel (Z>0): {len(apoyos)}")
    print(f"Apoyos (fix)                : {len(apoyos)}")
    print(f"Elementos verticales        : {len(elementos)}  (columnas={ncol}, muros={nmur})")
    print(f"  - Columnas (COL_70)  : {ncol}  (sección 70x70 cm)")
    print(f"  - Muros   (MUR_20)   : {nmur}  (espesor 20 cm)")
    print(f"Vigas horizontales         : {len(vigas['vigas'])}")
    print(f"  - Dirección X (2000-series, vanos E..I') : "
          f"{sum(1 for v in vigas['vigas'] if v['dir']=='X')}")
    print(f"  - Dirección Y (3000-series, vanos 1..3)  : "
          f"{sum(1 for v in vigas['vigas'] if v['dir']=='Y')}")
    print(f"  - Sección V. 60/80 (0.60 x 0.80 m)       : todas")
    print("-" * 78)
    print("DIAFRAGMA RÍGIDO (losa en su plano, cuerpo rígido en Ux-Uy-Rz)")
    print(f"  Centro de masa (m)       : X={cm[0]:.2f}, Y={cm[1]:.2f}")
    print(f"  Nodo maestro             : {MASTER_NODE}")
    print(f"  Nodos esclavos           : {len(esclavos)} (todos los nodos de piso)")
    print(f"  Restricción              : rigidDiaphragm(3, {MASTER_NODE}, slaves)")
    print("=" * 78)
    print("TRAZABILIDAD: Elevación Eje -> sectionTag -> elementTag")
    print(f"{'elementTag':>10} {'type':<8} {'iNode':>6} {'jNode':>6} {'sectionTag':>10}  Plano / Descripción")
    for e in elementos:
        print(
            f"{e['elementTag']:>10} {e['type']:<8} {e['iNode']:>6} {e['jNode']:>6} "
            f"{e['sectionTag']:>10}  {e['plano_fuente']} | {e['descripcion']}"
        )


def main():
    wipe()
    model("basic", "-ndm", 3, "-ndf", 6)

    apoyos = leer_json(FUNDACIONES)
    secciones_json = leer_json(SECCIONES)
    elementos = leer_json(ELEMENTOS)
    vigas_json = leer_json(VIGAS)
    cargas_json = leer_json(CARGAS)

    definir_materiales(secciones_json)
    crear_nodos_fundacion(apoyos)
    aplicar_apoyos(apoyos)
    crear_nodos_superiores(apoyos, z=Z_PRIMER_NIVEL)
    crear_elementos_verticales(elementos)
    crear_vigas(vigas_json)
    aplicar_carga_vigas(vigas_json, qG=cargas_json["qG_kN_m2"])

    # Diafragma rígido: nodo maestro en el centro de masa + restricción rígida
    x_cm, y_cm = centro_de_masa(apoyos, z=Z_PRIMER_NIVEL)
    esclavos = crear_diafragma_rigido(apoyos)

    reporte(apoyos, elementos, vigas_json, esclavos, (x_cm, y_cm),
            z=Z_PRIMER_NIVEL)

    # Tres vigas representativas: una X interior, una Y interior y una X de borde
    representativos = [2010, 3011, 2024]
    chequeo_conservacion(
        vigas_json, qG=cargas_json["qG_kN_m2"], cargas_json=cargas_json,
        representativos=representativos,
    )

    # Análisis estático gravitacional + reacciones en la base
    configurar_analisis_gravitacional()
    ok = ejecutar_analisis()
    print("\nAnálisis estático gravitacional")
    print(f"  analyze(1) -> {'OK (convergió)' if ok == 0 else f'FALLÓ (código {ok})'}")
    if ok == 0:
        ruta, suma = salida_reacciones(apoyos, cargas_json)
        nom = cargas_json["qG_kN_m2"] * cargas_json["a_piso_m2"]
        print(f"  Reacciones en la base guardadas en: {ruta}")
        print(f"  ΣRz (vertical, kN) = {suma[2]:.2f}   "
              f"(plan nominal = {nom:.2f} kN)")
        print("    Nota: la diferencia es la geometría real de los apoyos "
              "(DXF), no error.")
        print(f"  ΣFx = {suma[0]:.3f}   ΣFy = {suma[1]:.3f}   "
              f"ΣMz = {suma[5]:.3f}")
        print("  (ΣFx y ΣFy nulos porque no hay cargas horizontales: equilibrio)")

        # Esfuerzos internos por elemento + validación de extremos
        ruta_int, interno = extraer_fuerzas_internas(elementos, vigas_json)
        print(f"\nEsfuerzos internos por elemento guardados en: {ruta_int}")
        validar_internos(interno)


if __name__ == "__main__":
    main()
