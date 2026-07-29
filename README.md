# Magic PEX — Macro KLayout para Extracción de Parásitos vía MAGIC VLSI

![Status](https://img.shields.io/badge/status-desarrollo%20activo-yellow)
![Stack](https://img.shields.io/badge/stack-Python%20%7C%20KLayout%20%7C%20MAGIC%20VLSI-informational)
![Platform](https://img.shields.io/badge/platform-Windows%20%2B%20WSL-blue)

Macro de Python para KLayout que invoca a **MAGIC VLSI** (dentro de WSL) en modo headless para ejecutar **LVS** (Layout vs. Schematic) y **PEX** (extracción de parásitos) sobre el layout activo, sin salir de KLayout.

Trabajo de grado desarrollado en el marco de la beca SENACYT de formación en semiconductores, en colaboración con el **Centro de Investigación y Desarrollo Industrial (CIDESI)**.

>ste repositorio contiene únicamente la herramienta (el macro). No incluye PDKs, layouts de producción ni datos de proceso de CIDESI, que permanecen confidenciales.


KLayout es un excelente editor de layouts, pero no tiene motor propio de extracción de parásitos ni de LVS. MAGIC VLSI sí lo tiene, y es más maduro en esa área — pero es una herramienta de línea de comandos, pensada para correr en Linux.

En un entorno Windows con WSL, surge un problema: MAGIC falla al resolver rutas de Windows que contienen espacios (ej. `C:\Users\Nombre Apellido\...`), sin importar cómo se escapen los caracteres. Esto rompe cualquier flujo automatizado si el usuario tiene un espacio en su nombre de carpeta, algo común en cualquier instalación real de Windows.


El macro resuelve esto de forma transparente:

1. Convierte rutas de Windows a rutas WSL (`C:\...` → `/mnt/c/...`).
2. Si la ruta resultante contiene espacios, crea automáticamente un symlink dentro de WSL hacia una ruta sin espacios (`/tmp/<nombre-seguro>`), usando `wsl.exe ln -sfn`.
3. Usa esa ruta segura para invocar MAGIC (`path sys`, `addpath`, y para localizar el script `.tcl` a ejecutar).

Todo esto ocurre sin configuración manual — el macro detecta la carpeta del PDK activo y genera los symlinks que necesite.

## Flujo de ejecución

```
KLayout (layout activo, GDS)
        │
        ▼
1. Detecta celda activa y ruta del GDS
        │
        ▼
2. Localiza y "arregla" el .magicrc del PDK
   (genera <nombre>_local.magicrc con rutas seguras)
        │
        ▼
3. Genera scripts .tcl temporales:
   - LVS  → extract, ext2spice lvs
   - PEX  → flatten, extract all, extresist, ext2spice
        │
        ▼
4. Ejecuta MAGIC en modo headless vía wsl.exe
   (magic -rcfile ... -noc -dnull script.tcl)
        │
        ▼
5. Resultados: <celda>_lvs.spice y <celda>_pex.spice
```

## Requisitos

- KLayout con soporte de macros Python (`pya`)
- Windows con WSL habilitado
- MAGIC VLSI instalado dentro de WSL, accesible como `magic`
- Un PDK con archivo `.magicrc` válido en el directorio del proyecto

Ver `requirements.txt` — no hay dependencias de pip, solo librería estándar de Python más `pya` (viene incluido con KLayout).

## Uso

1. Coloca `magic_pex.py` en la carpeta de macros de tu PDK dentro de KLayout.
2. Abre el layout (GDS) que quieres verificar/extraer.
3. Ejecuta el macro desde KLayout (Macros → Magic PEX).
4. Revisa la consola de KLayout para ver el progreso (celda detectada, magicrc usado, resultado de LVS y PEX).
5. Los archivos `<celda>_lvs.spice` y `<celda>_pex.spice` se generan junto al GDS original.

## Capturas

<img width="1918" height="1078" alt="image" src="https://github.com/user-attachments/assets/ffed453f-d8a2-4ea2-822e-fef538a85d09" />
Layout de ejemplo para probar flujo del sistema.

<img width="1913" height="1078" alt="image" src="https://github.com/user-attachments/assets/1bfc7bb3-efee-491e-a305-47d7127a9247" />
Ejecución del macro. 



## Roadmap

- [ ] Interfaz simple dentro de KLayout para configurar parámetros de extracción (hoy están fijos en el `.tcl` generado)
- [ ] Manejo de errores más robusto si MAGIC falla a mitad de la extracción


