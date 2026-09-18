# magic_pex.py — Macro KLayout para extracción parasítica con Magic
# VERSION v9 — Magic 8.3.683 / PDK CIDESI_CM05
#
# Objetivos:
#   1) Mantener LVS estable.
#   2) Permitir RCX moderno (Magic >= 8.3.597).
#   3) Mantener un flujo LEGACY compatible con Magic actual para probar
#      el método que funcionaba en Magic 8.3.105:
#          extract -> ext2sim -> extresist all -> ext2spice
#      En Magic >= 8.3.597, la antigua resistencia "lumped" se activa
#      explícitamente con "extract do lumped".
#   4) Verificar que el SPICE realmente contiene resistencias.
#   5) Detectar SIGSEGV (return code 139) y resistencias negativas.
#
# MODO RECOMENDADO PARA TU CASO ACTUAL:
#   PEX_MODE = "legacy"
# porque el flujo moderno ya fue confirmado que cae con SIGSEGV dentro
# de "Processing cell TOP for resistance extraction".

import pya
import subprocess
import os
import glob
import time
import re
import shlex


# ============================================================
# CONFIGURACIÓN
# ============================================================

# "modern" : full-RC integrado de Magic >= 8.3.597
# "legacy" : flujo histórico ext2sim + extresist all
PEX_MODE = "modern"

# Parámetros para el flujo MODERNO.
# threshold=1 mOhm + mindelay=0 hace que prácticamente todas las redes
# entren al análisis resistivo, evitando el filtro por defecto de 10 ohmios.
MODERN_THRESHOLD_MOHM = 1
MODERN_MINRES_MOHM = 1000       # 1 ohm; simplifica resistores muy pequeños
MODERN_MINDELAY_PS = 0
MODERN_SIMPLIFY = True

# Parámetros para el flujo LEGACY.
# "extresist all" fuerza todas las redes, como en tu flujo antiguo.
# Mantener simplificación activa inicialmente reduce topologías patológicas.
LEGACY_MINRES_MOHM = 1000
LEGACY_SIMPLIFY = True

# Si quieres intentar reproducir una red extremadamente densa como la vieja:
#   LEGACY_MINRES_MOHM = 1
#   LEGACY_SIMPLIFY = False
# No lo recomiendo como primera opción: tu PEX viejo contiene resistencias
# negativas y esta configuración aumenta mucho el tamaño/estrés del extractor.

# Capacitancia mínima escrita a SPICE. 0 = conservar todas.
CTHRESH_FF = 0

# Timeout por ejecución de Magic.
MAGIC_TIMEOUT = 300

# Conservar Tcl temporal cuando Magic falla.
KEEP_FAILED_TCL = True

# Mostrar opciones detalladas de extresist.
EXTRESIST_VERBOSE = True


MACRO_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# WINDOWS -> WSL
# ============================================================

def to_wsl_path(win_path):
    if not win_path:
        return win_path

    p = win_path.replace("\\", "/")

    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"

    return p


def tcl_brace(value):
    """Protege paths/nombres para Tcl."""
    return "{" + str(value).replace("}", "\\}") + "}"


# ============================================================
# SYMLINKS WSL SIN ESPACIOS
# ============================================================

def safe_name_from_path(path):
    import hashlib

    filename = os.path.basename(path.rstrip("/")) or "path"
    stem, ext = os.path.splitext(filename)
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem).lower()
    h = hashlib.md5(path.encode("utf-8")).hexdigest()[:8]

    return f"{stem}_{h}{ext}"


def ensure_wsl_path_without_spaces(wsl_path):
    if not wsl_path or " " not in wsl_path:
        return wsl_path

    link_name = safe_name_from_path(wsl_path)
    link_path = f"/tmp/{link_name}"

    cmd = ["wsl.exe", "ln", "-sfn", wsl_path, link_path]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode != 0:
        print(
            "[Magic PEX] ADVERTENCIA: no se pudo crear symlink: "
            + result.stderr
        )
        return wsl_path

    print(f"[Magic PEX] Symlink creado: {link_path} -> {wsl_path}")
    return link_path


# ============================================================
# PDK / MAGICRC
# ============================================================

def find_magicrc(pdk_dir):
    local_rc = glob.glob(os.path.join(pdk_dir, "*_local.magicrc"))
    local_rc = [
        f for f in local_rc
        if "_local_local" not in os.path.basename(f)
    ]

    if local_rc:
        return local_rc[0]

    originals = glob.glob(os.path.join(pdk_dir, "*.magicrc"))
    originals = [
        f for f in originals
        if "_local" not in os.path.basename(f)
    ]

    if originals:
        return originals[0]

    return None


def fix_magicrc(original_path, pdk_dir, pdk_dir_safe_wsl):
    """
    Crea/actualiza *_local.magicrc reemplazando path sys y addpath
    por una ruta WSL segura sin espacios.
    """
    base = os.path.basename(original_path)
    stem = base.replace("_local.magicrc", "").replace(".magicrc", "")

    local_path = os.path.join(
        os.path.dirname(original_path),
        f"{stem}_local.magicrc"
    )

    with open(original_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    new_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("path sys"):
            new_lines.append(f"path sys +{pdk_dir_safe_wsl}\n")
            continue

        if stripped.startswith("addpath"):
            new_lines.append(f"addpath {pdk_dir_safe_wsl}\n")
            continue

        new_lines.append(line)

    with open(local_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(new_lines)

    return local_path


# ============================================================
# UTILIDADES DE ARCHIVOS
# ============================================================

def remove_file_if_exists(path):
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
            print(f"[Magic PEX Debug] Eliminado archivo anterior: {path}")
    except OSError as e:
        print(
            f"[Magic PEX] ADVERTENCIA: no se pudo eliminar {path}: {e}"
        )


def file_ok(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def clean_attempt_dir(work_dir, cell_name):
    """Elimina intermedios de ejecuciones previas del mismo intento."""
    candidates = []

    for base in (cell_name, f"{cell_name}-pex"):
        for ext in (
            ".ext",
            ".res.ext",
            ".sim",
            ".nodes",
            ".al",
            ".res.lump",
        ):
            candidates.append(os.path.join(work_dir, base + ext))

    for path in candidates:
        remove_file_if_exists(path)


def inspect_spice(spice_path):
    """
    Cuenta dispositivos y detecta resistencias negativas.
    Retorna un dict aun si el archivo no existe.
    """
    result = {
        "exists": False,
        "mos": 0,
        "resistors": 0,
        "capacitors": 0,
        "negative_resistors": 0,
        "negative_examples": [],
    }

    if not file_ok(spice_path):
        return result

    result["exists"] = True

    try:
        with open(spice_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith("*") or line.startswith("."):
                    continue

                first = line[0].upper()

                if first == "M":
                    result["mos"] += 1

                elif first == "C":
                    result["capacitors"] += 1

                elif first == "R":
                    result["resistors"] += 1

                    parts = line.split()
                    if len(parts) >= 4:
                        value = parts[3].strip()
                        if value.startswith("-"):
                            result["negative_resistors"] += 1
                            if len(result["negative_examples"]) < 8:
                                result["negative_examples"].append(line)

    except OSError as e:
        print(f"[Magic PEX] No se pudo analizar SPICE: {e}")

    return result


def print_spice_summary(label, spice_path):
    info = inspect_spice(spice_path)

    print(f"[Magic PEX] ===== RESUMEN {label} =====")
    print(f"[Magic PEX] Archivo: {spice_path}")
    print(f"[Magic PEX] Existe: {info['exists']}")
    print(f"[Magic PEX] MOS: {info['mos']}")
    print(f"[Magic PEX] Resistencias: {info['resistors']}")
    print(f"[Magic PEX] Capacitores: {info['capacitors']}")
    print(
        "[Magic PEX] Resistencias negativas: "
        f"{info['negative_resistors']}"
    )

    if info["negative_examples"]:
        print("[Magic PEX] ADVERTENCIA: ejemplos de R negativas:")
        for line in info["negative_examples"]:
            print("    " + line)

    return info


# ============================================================
# TCL — LVS
# ============================================================

def build_lvs_tcl(gds_path, cell_name, out_spice):
    return f"""
drc off
locking disable
crashbackups stop
box 0 0 0 0

puts "LVS STEP 1: leyendo GDS"
gds read {tcl_brace(gds_path)}

puts "LVS STEP 2: cargando {cell_name}"
load {tcl_brace(cell_name)}
select top cell
expand

# Para LVS no necesitamos parasitos.
extract no capacitance
extract no coupling
extract no resistance
extract no lumped
extract path .
extract all

ext2spice lvs
ext2spice -p . -o {tcl_brace(out_spice)}

puts "LVS completado: {cell_name}"
quit -noprompt
"""


# ============================================================
# TCL — RCX MODERNO (Magic >= 8.3.597)
# ============================================================

def build_pex_modern_tcl(gds_path, cell_name, out_spice):
    flat_cell = f"{cell_name}-pex"
    simplify = "on" if MODERN_SIMPLIFY else "off"
    verbose = "off" if EXTRESIST_VERBOSE else "on"

    return f"""
drc off
locking disable
crashbackups stop
box 0 0 0 0

puts "PEX MODERN STEP 1: leyendo GDS"
gds read {tcl_brace(gds_path)}

puts "PEX MODERN STEP 2: cargando {cell_name}"
load {tcl_brace(cell_name)}
select top cell

puts "PEX MODERN STEP 3: flatten -> {flat_cell}"
flatten {tcl_brace(flat_cell)}
load {tcl_brace(flat_cell)}

# El flujo RCX oficial recomienda que la celda plana tenga el nombre
# de la celda original durante la extracción.
cellname delete {tcl_brace(cell_name)}
cellname rename {tcl_brace(flat_cell)} {tcl_brace(cell_name)}
load {tcl_brace(cell_name)}
select top cell

extract path .
extract do unique

# Configuración del full-RC moderno.
extresist threshold {MODERN_THRESHOLD_MOHM}
extresist minres {MODERN_MINRES_MOHM}
extresist mindelay {MODERN_MINDELAY_PS}
extresist simplify {simplify}
extresist extout on
extresist silent {verbose}

puts "PEX MODERN threshold=[extresist threshold] mOhm"
puts "PEX MODERN minres=[extresist minres] mOhm"
puts "PEX MODERN mindelay=[extresist mindelay] ps"

# Desde Magic 8.3.597: full-RC integrado al extractor.
extract do resistance

puts "PEX MODERN STEP 4: extract all + full resistance"
extract all

puts "PEX MODERN STEP 5: extracción RC terminada"

ext2spice lvs
ext2spice format spice3
ext2spice cthresh {CTHRESH_FF}
ext2spice extresist on
ext2spice merge none

puts "PEX MODERN STEP 6: escribiendo SPICE"
ext2spice -p . -o {tcl_brace(out_spice)}

puts "PEX MODERN completado"
quit -noprompt
"""


# ============================================================
# TCL — RCX LEGACY COMPATIBLE CON MAGIC 8.3.683
# ============================================================

def build_pex_legacy_tcl(gds_path, cell_name, out_spice):
    """
    Reproduce conceptualmente el flujo anterior a Magic 8.3.597:

        extract -> ext2sim -> extresist all -> ext2spice

    Diferencia importante para Magic actual:
        "extract do lumped"
    activa explícitamente la resistencia lumped que antes se llamaba
    "extract do resistance" y que ext2sim/extresist utiliza como base.

    NO se activa "extract do resistance" aquí, porque en 8.3.683 eso
    dispara el nuevo full-RC integrado que actualmente te da SIGSEGV.
    """
    flat_cell = f"{cell_name}-pex"
    simplify = "on" if LEGACY_SIMPLIFY else "off"
    verbose = "off" if EXTRESIST_VERBOSE else "on"

    return f"""
drc off
locking disable
crashbackups stop
box 0 0 0 0

puts "PEX LEGACY STEP 1: leyendo GDS"
gds read {tcl_brace(gds_path)}

puts "PEX LEGACY STEP 2: cargando {cell_name}"
load {tcl_brace(cell_name)}
select top cell

puts "PEX LEGACY STEP 3: flatten -> {flat_cell}"
flatten {tcl_brace(flat_cell)}
load {tcl_brace(flat_cell)}
select top cell

extract path .
extract do unique

# CLAVE:
# En Magic >= 8.3.597, "lumped" es el nombre de la vieja estimación
# de resistencia que el flujo ext2sim/extresist necesita.
extract do lumped

# Capacitancias/coupling quedan activos para el PEX.
extract do capacitance
extract do coupling

puts "PEX LEGACY STEP 4: extracción base"
extract all

# Flujo histórico: generar .sim y .nodes.
puts "PEX LEGACY STEP 5: generando .sim/.nodes"
ext2sim labels on
ext2sim

# Configuración del standalone extresist.
extresist minres {LEGACY_MINRES_MOHM}
extresist simplify {simplify}
extresist extout on
extresist silent {verbose}

# IMPORTANTE:
# 'all' fuerza a procesar todas las redes, equivalente al comportamiento
# que te producía muchas R en la versión antigua.
puts "PEX LEGACY STEP 6: extresist all"
extresist all

puts "PEX LEGACY STEP 7: resistencia detallada terminada"

ext2spice lvs
ext2spice format spice3
ext2spice cthresh {CTHRESH_FF}
ext2spice extresist on
ext2spice merge none

puts "PEX LEGACY STEP 8: escribiendo SPICE"
ext2spice -p . -o {tcl_brace(out_spice)}

puts "PEX LEGACY completado: {flat_cell}"
quit -noprompt
"""


# ============================================================
# EJECUTAR MAGIC
# ============================================================

def run_magic(tcl_script, magicrc, work_dir, tag):
    os.makedirs(work_dir, exist_ok=True)

    tcl_win = os.path.join(
        work_dir,
        f"magic_{tag}_{int(time.time())}.tcl"
    )

    with open(tcl_win, "w", encoding="utf-8", newline="\n") as f:
        f.write(tcl_script)

    tcl_wsl = ensure_wsl_path_without_spaces(to_wsl_path(tcl_win))
    magicrc_wsl = ensure_wsl_path_without_spaces(to_wsl_path(magicrc))

    # Ejecutar bajo bash permite capturar correctamente señal/exit code.
    cmd_bash = (
        "ulimit -s unlimited 2>/dev/null || ulimit -s 65536; "
        "magic -dnull -noconsole "
        f"-rcfile {shlex.quote(magicrc_wsl)} "
        f"{shlex.quote(tcl_wsl)}"
    )

    result = None

    try:
        result = subprocess.run(
            ["wsl.exe", "bash", "-c", cmd_bash],
            capture_output=True,
            text=True,
            timeout=MAGIC_TIMEOUT,
            cwd=work_dir
        )

        return result.stdout, result.stderr, result.returncode, tcl_win

    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        stderr += (
            f"\n[Magic PEX] ERROR: timeout de {MAGIC_TIMEOUT} s."
        )
        return stdout, stderr, 124, tcl_win

    finally:
        success = result is not None and result.returncode == 0

        if success or not KEEP_FAILED_TCL:
            try:
                if os.path.exists(tcl_win):
                    os.unlink(tcl_win)
            except OSError:
                pass
        else:
            print(
                "[Magic PEX] Tcl conservado para depuración: "
                f"{tcl_win}"
            )


# ============================================================
# EJECUCIÓN DE UN INTENTO PEX
# ============================================================

def run_pex_attempt(
    mode,
    gds_wsl_safe,
    cell_name,
    out_pex,
    out_pex_wsl_safe,
    magicrc,
    attempt_dir,
):
    os.makedirs(attempt_dir, exist_ok=True)
    clean_attempt_dir(attempt_dir, cell_name)
    remove_file_if_exists(out_pex)

    if mode == "modern":
        title = "PEX MODERNO"
        script = build_pex_modern_tcl(
            gds_wsl_safe,
            cell_name,
            out_pex_wsl_safe
        )
    elif mode == "legacy":
        title = "PEX LEGACY"
        script = build_pex_legacy_tcl(
            gds_wsl_safe,
            cell_name,
            out_pex_wsl_safe
        )
    else:
        raise ValueError(f"Modo PEX inválido: {mode}")

    print(f"\n[Magic PEX] ===== INICIO {title} =====")

    stdout, stderr, rc, tcl_path = run_magic(
        script,
        magicrc,
        attempt_dir,
        mode
    )

    if stdout:
        print(stdout)

    if stderr:
        print(f"[STDERR {title}] {stderr}")

    print(f"[Magic PEX] {title} return code: {rc}")

    if rc == 139:
        print(
            "[Magic PEX] ERROR CRITICO: 139 = SIGSEGV. "
            "Magic se estrelló dentro del código nativo de extracción."
        )

    # El nombre del .res.ext depende del flujo.
    if mode == "modern":
        res_ext = os.path.join(attempt_dir, f"{cell_name}.res.ext")
        ext_file = os.path.join(attempt_dir, f"{cell_name}.ext")
    else:
        res_ext = os.path.join(attempt_dir, f"{cell_name}-pex.res.ext")
        ext_file = os.path.join(attempt_dir, f"{cell_name}-pex.ext")

    # Por seguridad, si el nombre esperado no aparece, buscar cualquiera.
    if not file_ok(ext_file):
        candidates = glob.glob(os.path.join(attempt_dir, "*.ext"))
        candidates = [p for p in candidates if not p.endswith(".res.ext")]
        if candidates:
            ext_file = candidates[0]

    if not file_ok(res_ext):
        candidates = glob.glob(os.path.join(attempt_dir, "*.res.ext"))
        if candidates:
            res_ext = candidates[0]

    print(
        "[Magic PEX Debug] .ext: "
        f"{'EXITO' if file_ok(ext_file) else 'FALLO'} -> {ext_file}"
    )
    print(
        "[Magic PEX Debug] .res.ext: "
        f"{'EXITO' if file_ok(res_ext) else 'FALLO'} -> {res_ext}"
    )

    spice_info = print_spice_summary(title, out_pex)

    success = (
        rc == 0
        and file_ok(out_pex)
        and spice_info["resistors"] > 0
    )

    if rc == 0 and file_ok(out_pex) and spice_info["resistors"] == 0:
        print(
            "[Magic PEX] ADVERTENCIA: Magic generó SPICE, pero no contiene "
            "ninguna línea R. Para este proyecto no se considera RCX exitoso."
        )

    if spice_info["negative_resistors"] > 0:
        print(
            "[Magic PEX] ADVERTENCIA IMPORTANTE: el PEX contiene resistencias "
            "negativas. El archivo fue generado, pero la red RC debe revisarse "
            "antes de considerarla físicamente válida."
        )

    return {
        "mode": mode,
        "success": success,
        "rc": rc,
        "tcl": tcl_path,
        "ext": ext_file,
        "res_ext": res_ext,
        "spice": spice_info,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    app = pya.Application.instance()
    mw = app.main_window()
    cv = mw.current_view()

    if cv is None:
        pya.MessageBox.warning(
            "Magic PEX",
            "No hay layout abierto.",
            pya.MessageBox.Ok
        )
        return

    active_cellview = cv.active_cellview()
    layout = active_cellview.layout()
    cell = layout.cell(active_cellview.cell_index)

    cell_name = cell.name
    gds_path = active_cellview.filename()

    if not gds_path or not os.path.exists(gds_path):
        pya.MessageBox.warning(
            "Magic PEX",
            "GDS no válido.",
            pya.MessageBox.Ok
        )
        return

    # --------------------------------------------------------
    # Detectar PDK dinámicamente desde KLayout/salt
    # --------------------------------------------------------
    tech_name = layout.technology().name
    app_data = app.application_data_path()
    salt_dir = os.path.join(app_data, "salt")

    pdk_dir = None
    magicrc_original = None

    if os.path.exists(salt_dir):
        # 1) Tecnología activa exacta.
        if tech_name and tech_name != "(Default)":
            tech_path = os.path.join(salt_dir, tech_name)

            if os.path.isdir(tech_path):
                m = find_magicrc(tech_path)
                if m:
                    pdk_dir = tech_path
                    magicrc_original = m

        # 2) Fallback: primera carpeta con magicrc.
        if not pdk_dir:
            for folder in os.listdir(salt_dir):
                folder_path = os.path.join(salt_dir, folder)

                if os.path.isdir(folder_path):
                    m = find_magicrc(folder_path)
                    if m:
                        pdk_dir = folder_path
                        magicrc_original = m
                        break

    if not pdk_dir or not magicrc_original:
        pya.MessageBox.warning(
            "Magic PEX",
            (
                "No se encontró .magicrc en salt.\n"
                f"Tecnología actual: {tech_name}"
            ),
            pya.MessageBox.Ok
        )
        return

    # --------------------------------------------------------
    # Rutas WSL seguras
    # --------------------------------------------------------
    pdk_dir_wsl = to_wsl_path(pdk_dir)
    pdk_dir_safe_wsl = ensure_wsl_path_without_spaces(pdk_dir_wsl)

    magicrc = fix_magicrc(
        magicrc_original,
        pdk_dir,
        pdk_dir_safe_wsl
    )

    gds_dir = os.path.dirname(gds_path)
    work_root = os.path.join(gds_dir, f"{cell_name}_magic_work")
    os.makedirs(work_root, exist_ok=True)

    lvs_dir = os.path.join(work_root, "lvs")
    modern_dir = os.path.join(work_root, "pex_modern")
    legacy_dir = os.path.join(work_root, "pex_legacy")

    os.makedirs(lvs_dir, exist_ok=True)
    os.makedirs(modern_dir, exist_ok=True)
    os.makedirs(legacy_dir, exist_ok=True)

    out_lvs = os.path.join(gds_dir, f"{cell_name}_lvs.spice")
    out_pex = os.path.join(gds_dir, f"{cell_name}_pex.spice")

    gds_wsl_safe = ensure_wsl_path_without_spaces(
        to_wsl_path(gds_path)
    )
    out_lvs_wsl_safe = ensure_wsl_path_without_spaces(
        to_wsl_path(out_lvs)
    )
    out_pex_wsl_safe = ensure_wsl_path_without_spaces(
        to_wsl_path(out_pex)
    )

    print(f"[Magic PEX] Celda: {cell_name}")
    print(f"[Magic PEX] PEX_MODE: {PEX_MODE}")
    print(f"[Magic PEX] PDK_DIR detectado: {pdk_dir}")
    print(f"[Magic PEX] PDK_DIR WSL seguro: {pdk_dir_safe_wsl}")
    print(f"[Magic PEX] magicrc original: {magicrc_original}")
    print(f"[Magic PEX] magicrc usado: {magicrc}")

    try:
        with open(magicrc, "r", encoding="utf-8", errors="replace") as f:
            print("[Magic PEX] Contenido magicrc:")
            print(f.read())
    except Exception as e:
        print(f"[Magic PEX] No se pudo leer magicrc: {e}")

    # --------------------------------------------------------
    # LVS
    # --------------------------------------------------------
    clean_attempt_dir(lvs_dir, cell_name)
    remove_file_if_exists(out_lvs)

    print("\n[Magic PEX] ===== INICIO LVS =====")

    tcl_lvs = build_lvs_tcl(
        gds_wsl_safe,
        cell_name,
        out_lvs_wsl_safe
    )

    stdout, stderr, lvs_rc, _ = run_magic(
        tcl_lvs,
        magicrc,
        lvs_dir,
        "lvs"
    )

    if stdout:
        print(stdout)
    if stderr:
        print("[STDERR LVS]", stderr)

    print(f"[Magic PEX] LVS return code: {lvs_rc}")
    lvs_ok = lvs_rc == 0 and file_ok(out_lvs)
    print(f"[Magic PEX] LVS generado: {lvs_ok} -> {out_lvs}")

    # --------------------------------------------------------
    # PEX
    # --------------------------------------------------------
    result = None

    if PEX_MODE == "modern":
        result = run_pex_attempt(
            "modern",
            gds_wsl_safe,
            cell_name,
            out_pex,
            out_pex_wsl_safe,
            magicrc,
            modern_dir,
        )

    elif PEX_MODE == "legacy":
        result = run_pex_attempt(
            "legacy",
            gds_wsl_safe,
            cell_name,
            out_pex,
            out_pex_wsl_safe,
            magicrc,
            legacy_dir,
        )


    else:
        print(
            f"[Magic PEX] ERROR: PEX_MODE inválido: {PEX_MODE}. "
            "Use 'modern' o 'legacy'."
        )
        return

    # --------------------------------------------------------
    # Resultado final
    # --------------------------------------------------------
    print("\n[Magic PEX] ===== RESULTADO FINAL =====")
    print(f"[Magic PEX] LVS: {'OK' if lvs_ok else 'FALLO'}")

    if result is None:
        print("[Magic PEX] PEX: NO EJECUTADO")
    else:
        print(f"[Magic PEX] Modo PEX usado: {result['mode']}")
        print(
            f"[Magic PEX] PEX RC: "
            f"{'OK' if result['success'] else 'FALLO'}"
        )
        print(f"[Magic PEX] Return code: {result['rc']}")
        print(
            "[Magic PEX] Resistencias SPICE: "
            f"{result['spice']['resistors']}"
        )
        print(
            "[Magic PEX] Resistencias negativas: "
            f"{result['spice']['negative_resistors']}"
        )
        print(f"[Magic PEX] Archivo PEX: {out_pex}")

        if result["rc"] == 139:
            print(
                "[Magic PEX] DIAGNOSTICO: SIGSEGV dentro del extractor "
                "resistivo de Magic. El siguiente paso es revisar el PDK "
                "o sacar backtrace con gdb."
            )

        elif file_ok(out_pex) and result["spice"]["resistors"] == 0:
            print(
                "[Magic PEX] DIAGNOSTICO: se generó SPICE, pero sin R. "
                "No se acepta como full-RC."
            )

        elif result["spice"]["negative_resistors"] > 0:
            print(
                "[Magic PEX] DIAGNOSTICO: hay R negativas. La extracción "
                "terminó, pero el PDK/red resistiva necesita revisión."
            )

    print("[Magic PEX] FIN")

main()
