# magic_pex.py — Macro KLayout para extraccion de parasitos
# FIXED VERSION v6
#
#   Problema resuelto: MAGIC ("path sys" / "addpath") no maneja correctamente
#   rutas WSL con espacios, sin
#   importar como se escapen (\, {}, etc.).
#
#   Solucion: si PDK_DIR (convertido a ruta WSL) contiene espacios, el
#   macro crea automaticamente un symlink DENTRO de WSL hacia una ruta
#   sin espacios (/tmp/cidesi_pdk_link), y usa esa ruta para
#   "path sys" / "addpath". Todo esto ocurre de forma transparente,
#   sin configuracion manual ni rutas hardcodeadas: el nombre del
#   symlink se deriva del nombre de PDK_DIR.

import pya
import subprocess
import os
import glob
import time
import re

MACRO_DIR = os.path.dirname(os.path.abspath(__file__))
PDK_DIR   = os.path.dirname(MACRO_DIR)


# ── Windows → WSL ────────────────────────────────────────────
def to_wsl_path(win_path):
    if not win_path:
        return win_path
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest  = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def tcl_brace(path):
    """Para comandos Tcl estandar (gds read, ext2spice -o, extract path)."""
    return "{" + path + "}"


# ── Symlink automatico sin espacios ──────────────────────────

def safe_name_from_path(path):
    """
    Genera nombre corto para symlink PERO preserva extensión.
    """

    import hashlib

    filename = os.path.basename(path.rstrip("/")) or "pdk"

    stem, ext = os.path.splitext(filename)

    stem = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        stem
    ).lower()

    h = hashlib.md5(
        path.encode("utf-8")
    ).hexdigest()[:8]

    return f"{stem}_{h}{ext}"


def ensure_wsl_path_without_spaces(wsl_path):
    """
    Si wsl_path NO tiene espacios, lo devuelve tal cual.
    Si tiene espacios, crea (o reutiliza) un symlink en /tmp/ sin espacios
    que apunte a wsl_path, y devuelve la ruta del symlink.

    El symlink se crea ejecutando 'ln -sf' dentro de WSL via wsl.exe,
    por lo que no requiere abrir una terminal manualmente.
    """
    if " " not in wsl_path:
        return wsl_path

    link_name = safe_name_from_path(wsl_path)
    link_path = f"/tmp/{link_name}"

    # Crear/actualizar el symlink dentro de WSL (idempotente: -f sobreescribe)
    cmd = ["wsl.exe", "ln", "-sfn", wsl_path, link_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        print(f"[Magic PEX] ADVERTENCIA: no se pudo crear symlink: {result.stderr}")
        return wsl_path  # fallback: intentar con la ruta original

    print(f"[Magic PEX] Symlink creado: {link_path} -> {wsl_path}")
    return link_path


# ── Buscar magicrc ───────────────────────────────────────────
def find_magicrc(pdk_dir):
    local_rc = glob.glob(os.path.join(pdk_dir, "*_local.magicrc"))
    local_rc = [f for f in local_rc if "_local_local" not in os.path.basename(f)]
    if local_rc:
        return local_rc[0]

    originals = glob.glob(os.path.join(pdk_dir, "*.magicrc"))
    originals = [f for f in originals if "_local" not in os.path.basename(f)]
    if originals:
        return originals[0]

    return None


# ── Fix magicrc ───────────────────────────────────────────────
def fix_magicrc(original_path, pdk_dir, pdk_dir_safe_wsl):
    """
    Genera <nombre>_local.magicrc con:
      path sys +/ruta/sin/espacios   (symlink si era necesario)
      addpath /ruta/sin/espacios
    """
    base = os.path.basename(original_path)
    stem = base.replace("_local.magicrc", "").replace(".magicrc", "")
    local_path = os.path.join(os.path.dirname(original_path), f"{stem}_local.magicrc")

    with open(original_path, 'r') as f:
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

    with open(local_path, 'w') as f:
        f.writelines(new_lines)

    return local_path


# ── LVS TCL ─────────────────────────────────────────────────
def build_lvs_tcl(gds_path, cell_name, out_spice, work_dir):
    gds_b = tcl_brace(gds_path)
    out_b = tcl_brace(out_spice)

    return f"""
drc off
crashbackups stop

gds read {gds_b}
load {cell_name}
select top cell
expand

extract no capacitance
extract no resistance
extract all

ext2spice lvs
ext2spice -o {out_b}

puts "LVS completado: {cell_name}"
quit
"""


# ── PEX TCL ─────────────────────────────────────────────────
def build_pex_tcl(gds_path, cell_name, out_spice, work_dir):

    flat_cell = f"{cell_name}-pex"

    return f"""
drc off
crashbackups stop

gds read {tcl_brace(gds_path)}

load {cell_name}

flatten {flat_cell}

load {flat_cell}

select top cell

extract all

extresist tolerance 10
extresist

ext2spice lvs
ext2spice cthresh 0.01
ext2spice extresist on

ext2spice -o {tcl_brace(out_spice)}

puts "PEX completado: {flat_cell}"

quit
"""


# ── Ejecutar MAGIC ──────────────────────────────────────────
def run_magic(tcl_script, magicrc, work_dir):
    tmp_dir = os.path.join(PDK_DIR, "_tmp_pex")
    os.makedirs(tmp_dir, exist_ok=True)

    tcl_win = os.path.join(tmp_dir, f"magic_script_{int(time.time())}.tcl")

    with open(tcl_win, "w", newline="\n") as f:
        f.write(tcl_script)

    tcl_wsl     = to_wsl_path(tcl_win)
    magicrc_wsl = to_wsl_path(magicrc)

    # El .tcl y el .magicrc tambien pueden tener espacios en su ruta
    # (estan dentro de PDK_DIR). Los pasamos por el mismo mecanismo.
    tcl_wsl_safe     = ensure_wsl_path_without_spaces(tcl_wsl)
    magicrc_wsl_safe = ensure_wsl_path_without_spaces(magicrc_wsl)

    try:
        result = subprocess.run(
            ["wsl.exe", "magic", "-rcfile", magicrc_wsl_safe, "-noc", "-dnull", tcl_wsl_safe],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=work_dir
        )
        return result.stdout, result.stderr, result.returncode
    finally:
        os.unlink(tcl_win)


# ── MAIN ────────────────────────────────────────────────────
def main():

    app = pya.Application.instance()
    mw  = app.main_window()
    cv  = mw.current_view()

    if cv is None:
        pya.MessageBox.warning("Magic PEX", "No hay layout abierto.", pya.MessageBox.Ok)
        return

    active_cellview = cv.active_cellview()
    layout     = active_cellview.layout()
    cell       = layout.cell(active_cellview.cell_index)

    cell_name  = cell.name
    gds_path   = active_cellview.filename()

    if not gds_path or not os.path.exists(gds_path):
        pya.MessageBox.warning("Magic PEX", "GDS no válido.", pya.MessageBox.Ok)
        return

    magicrc_original = find_magicrc(PDK_DIR)

    if not magicrc_original:
        pya.MessageBox.warning("Magic PEX", "No se encontró .magicrc original en:\n" + PDK_DIR, pya.MessageBox.Ok)
        return

    # ── Resolver PDK_DIR a una ruta WSL sin espacios (symlink si hace falta) ──
    pdk_dir_wsl      = to_wsl_path(PDK_DIR)
    pdk_dir_safe_wsl = ensure_wsl_path_without_spaces(pdk_dir_wsl)

    magicrc = fix_magicrc(magicrc_original, PDK_DIR, pdk_dir_safe_wsl)

    gds_dir  = os.path.dirname(gds_path)
    work_dir = os.path.join(gds_dir, f"{cell_name}_magic_work")
    os.makedirs(work_dir, exist_ok=True)

    out_lvs = os.path.join(gds_dir, f"{cell_name}_lvs.spice")
    out_pex = os.path.join(gds_dir, f"{cell_name}_pex.spice")

    gds_wsl     = to_wsl_path(gds_path)
    out_lvs_wsl = to_wsl_path(out_lvs)
    out_pex_wsl = to_wsl_path(out_pex)

    # GDS y salidas SPICE tambien pueden estar bajo rutas con espacios
    gds_wsl_safe     = ensure_wsl_path_without_spaces(gds_wsl)
    out_lvs_wsl_safe = ensure_wsl_path_without_spaces(out_lvs_wsl)
    out_pex_wsl_safe = ensure_wsl_path_without_spaces(out_pex_wsl)

    print(f"[Magic PEX] Celda: {cell_name}")
    print(f"[Magic PEX] PDK_DIR: {PDK_DIR}")
    print(f"[Magic PEX] PDK_DIR (WSL, seguro): {pdk_dir_safe_wsl}")
    print(f"[Magic PEX] magicrc original: {magicrc_original}")
    print(f"[Magic PEX] magicrc usado: {magicrc}")

    try:
        with open(magicrc, 'r') as f:
            print("[Magic PEX] Contenido magicrc:")
            print(f.read())
    except Exception as e:
        print(f"[Magic PEX] No se pudo leer magicrc: {e}")

    # LVS
    tcl_lvs = build_lvs_tcl(gds_wsl_safe, cell_name, out_lvs_wsl_safe, work_dir)
    stdout, stderr, rc = run_magic(tcl_lvs, magicrc, work_dir)
    if stdout:
        print(stdout)
    if stderr:
        print("[STDERR LVS]", stderr)

    # PEX
    tcl_pex = build_pex_tcl(gds_wsl_safe, cell_name, out_pex_wsl_safe, work_dir)
    stdout, stderr, rc = run_magic(tcl_pex, magicrc, work_dir)
    if stdout:
        print(stdout)
    if stderr:
        print("[STDERR PEX]", stderr)

    lvs_ok = os.path.exists(out_lvs)
    pex_ok = os.path.exists(out_pex)
    print(f"[Magic PEX] LVS generado: {lvs_ok} -> {out_lvs}")
    print(f"[Magic PEX] PEX generado: {pex_ok} -> {out_pex}")
    print("[Magic PEX] FIN")


main()
