"""
Genera una vista 3D interactiva y autocontenida del modelo estructural en HTML.

Lee los JSON ya construidos del modelo:
- fundaciones.json            -> coordenadas de nodos (cm)
- elementos_verticales.json   -> columnas y muros
- vigas_tributarias.json      -> vigas horizontales
- resultados_fuerzas_internas.json -> esfuerzos (P, My, Mz) para tooltips (opcional)

El HTML resultante embebe plotly.js localmente (plotly.min.js), por lo que es
autocontenido: se abre sin conexión a internet en cualquier navegador (o con
Live Server en VS Code) y permite rotar, hacer zoom y pasar el cursor sobre cada
elemento para ver su esfuerzo.

Uso:
    python generar_vista_3d.py
"""
import json
import os

RAIZ = os.path.dirname(os.path.abspath(__file__))
FUND = os.path.join(RAIZ, "fundaciones.json")
ELV = os.path.join(RAIZ, "elementos_verticales.json")
VIG = os.path.join(RAIZ, "vigas_tributarias.json")
INT = os.path.join(RAIZ, "resultados_fuerzas_internas.json")
PLOTLY = os.path.join(RAIZ, "plotly.min.js")
SALIDA = os.path.join(RAIZ, "vista_3d_modelo.html")

Z = 3.96  # cota del primer nivel (m) - coincide con el modelo


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def carga():
    fundamentos = leer(FUND)
    verticales = leer(ELV)
    vigas = leer(VIG)["vigas"]
    internos = {}
    if os.path.exists(INT):
        for r in leer(INT)["elementos"]:
            internos[r["elementTag"]] = r
    # coords en metros: nodo tag (base) y 1000+tag (cima a Z)
    coords = {}
    for a in fundamentos:
        coords[a["nodeTag"]] = (a["x"] / 100.0, a["y"] / 100.0, 0.0)
        coords[1000 + a["nodeTag"]] = (a["x"] / 100.0, a["y"] / 100.0, Z)
    return fundamentos, verticales, vigas, internos, coords


def recuadro(coords, fundamentos):
    xs = [a["x"] / 100.0 for a in fundamentos]
    ys = [a["y"] / 100.0 for a in fundamentos]
    return min(xs), max(xs), min(ys), max(ys)


def segmentos_tipo(verticales, vigas, internos, coords):
    """Devuelve listas de trazas de líneas 3D por tipo con hover de esfuerzos."""
    trazas = []

    def coord_fn(tag):
        return coords[tag]

    def traza(nombre, color, items):
        xs, ys, zs, txt = [], [], [], []
        for it in items:
            (xi, yi, zi) = coord_fn(it["iNode"])
            (xj, yj, zj) = coord_fn(it["jNode"])
            xs += [xi, xj, None]
            ys += [yi, yj, None]
            zs += [zi, zj, None]
            r = internos.get(it["elementTag"])
            desc = (r["descripcion"] if r else "")
            f = ""
            if r:
                f = (f"<br>P={r['P_kN']} kN · Vy={r['Vy_kN']} · Vz={r['Vz_kN']}"
                     f"<br>My={r['My_kNm']} kN·m · Mz={r['Mz_kNm']} kN·m")
            txt += [f"{nombre} #{it['elementTag']}<br>{desc}{f}", "", ""]
        trazas.append({
            "type": "scatter3d", "mode": "lines", "name": nombre,
            "x": xs, "y": ys, "z": zs, "text": txt, "hoverinfo": "text",
            "line": {"color": color, "width": 6},
        })

    traza("Columnas", "#1f77b4",
          [e for e in verticales if e["type"] == "columna"])
    traza("Muros", "#b0b0b0",
          [e for e in verticales if e["type"] == "muro"])
    traza("Vigas", "#ff7f0e", vigas)
    return trazas


def superficie_losa(xmin, xmax, ymin, ymax):
    """Capa translúcida de la losa en Z=3.96."""
    return {
        "type": "mesh3d", "name": "Losa",
        "x": [xmin, xmax, xmax, xmin],
        "y": [ymin, ymin, ymax, ymax],
        "z": [Z, Z, Z, Z],
        "i": [0, 0], "j": [1, 2], "k": [3, 3],  # triangulación del cuadrado
        "opacity": 0.18, "color": "rgba(120,180,255,0.35)",
        "hoverinfo": "skip", "showscale": False,
    }


def apoyos_marcadores(fundamentos):
    xs = [a["x"] / 100.0 for a in fundamentos]
    ys = [a["y"] / 100.0 for a in fundamentos]
    zs = [0.0] * len(fundamentos)
    return {
        "type": "scatter3d", "mode": "markers", "name": "Apoyos (base)",
        "x": xs, "y": ys, "z": zs,
        "marker": {"size": 3, "color": "black"},
        "hoverinfo": "skip",
    }


def main():
    fundamentos, verticales, vigas, internos, coords = carga()
    xmin, xmax, ymin, ymax = recuadro(coords, fundamentos)
    trazas = segmentos_tipo(verticales, vigas, internos, coords)
    trazas.append(apoyos_marcadores(fundamentos))
    trazas.append(superficie_losa(xmin, xmax, ymin, ymax))

    data = json.dumps(trazas)
    layout = {
        "title": {
            "text": ("Modelo 3D - Fundaciones + Elementos Verticales + Vigas"
                     "<br><sup>1° Subterráneo (Z=3.96 m) · colores por tipo de elemento</sup>"),
            "font": {"size": 16},
        },
        "scene": {
            "aspectmode": "data",
            "xaxis": {"title": "X (m)"},
            "yaxis": {"title": "Y (m)"},
            "zaxis": {"title": "Z (m)"},
            "camera": {"eye": {"x": 1.6, "y": -1.6, "z": 0.9}},
        },
        "hoverlabel": {"bgcolor": "white", "font": {"size": 11}},
        "margin": {"l": 0, "r": 0, "t": 60, "b": 0},
        "legend": {"x": 0.98, "xanchor": "right", "y": 0.98, "yanchor": "top"},
    }
    layout_s = json.dumps(layout)

    with open(PLOTLY, encoding="utf-8") as f:
        plotly_js = f.read()

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Modelo Estructural 3D</title>
<style>
  body {{ margin:0; font-family: Arial, sans-serif; }}
  #info {{ position:absolute; top:8px; left:8px; z-index:10; background:#ffffffcc;
           padding:6px 10px; border-radius:6px; font-size:12px; }}
</style>
</head>
<body>
<div id="info">Arrastra para rotar · Rueda para zoom · Pasa el cursor sobre un
elemento para ver sus esfuerzos (P, My, Mz).</div>
<div id="plot" style="width:100vw;height:100vh;"></div>
<script>{plotly_js}</script>
<script>
  var data = {data};
  var layout = {layout_s};
  Plotly.newPlot('plot', data, layout, {{responsive:true, displaylogo:false}});
</script>
</body>
</html>
"""
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Vista 3D generada: {SALIDA}  ({os.path.getsize(SALIDA)/1e6:.1f} MB)")
    print("Abrir en VS Code: click derecho sobre el archivo -> 'Reveal in File "
          "Explorer' o usar la extensión 'Live Server', o doble clic para abrir "
          "en el navegador.")


if __name__ == "__main__":
    main()
