# Magic PEX — Macro KLayout para Extracción de Parásitos vía MAGIC VLSI

![Status](https://img.shields.io/badge/status-v12%20estable-success)
![Stack](https://img.shields.io/badge/stack-Python%20%7C%20KLayout%20%7C%20MAGIC%20VLSI-informational)
![Platform](https://img.shields.io/badge/platform-Windows%20%2B%20WSL-blue)
![Magic](https://img.shields.io/badge/MAGIC-8.3.683-purple)

Macro de Python para **KLayout** que invoca a **MAGIC VLSI** dentro de **WSL** en modo headless para automatizar dos tareas principales sobre el layout activo:

- generación de un netlist SPICE preparado para verificación **LVS**;
- extracción parasítica **PEX full-RC** con resistencias y capacitancias.

El flujo se ejecuta directamente desde KLayout, sin necesidad de abrir MAGIC manualmente ni preparar scripts Tcl o rutas WSL a mano.

Este trabajo forma parte de un proyecto de grado desarrollado en el marco de la **beca SENACYT de formación en semiconductores**, con trabajo realizado en colaboración con el **Centro de Ingeniería y Desarrollo Industrial (CIDESI)**.

> Este repositorio contiene únicamente la herramienta de automatización. No incluye PDKs, layouts de producción ni datos confidenciales de proceso de CIDESI.

---

## Estado actual

La versión estable actual es **v12**.

Esta versión consolida el flujo moderno de extracción full-RC de MAGIC y elimina la arquitectura experimental anterior basada en los modos `legacy`, `modern` y `auto`.

La v12 ha sido validada con:

- Windows;
- WSL;
- KLayout con soporte Python (`pya`);
- MAGIC VLSI 8.3.683;
- PDK `CIDESI_CM05`;
- generación de netlist para LVS;
- extracción PEX full-RC;
- un **Flip-Flop tipo D** como GDS de prueba.

El flujo PEX requiere **MAGIC >= 8.3.597**, debido al uso del mecanismo integrado de extracción resistiva.

---

## Motivación

KLayout es un excelente editor de layouts, pero no incorpora por sí mismo un motor completo de extracción parasítica ni de comparación LVS.

MAGIC VLSI sí dispone de herramientas maduras para extracción, pero su uso está orientado principalmente a entornos Linux y línea de comandos.

En un entorno Windows + WSL aparece además un problema práctico importante: MAGIC puede fallar al resolver rutas de Windows que contienen espacios, por ejemplo:

```text
C:\Users\Nombre Apellido\...
```

Esto complica cualquier flujo automatizado que dependa de rutas convertidas directamente a:

```text
/mnt/c/Users/Nombre Apellido/...
```

El macro resuelve este problema de manera transparente.

---

## Solución implementada

El macro automatiza principalmente:

1. detección del layout y de la celda activa;
2. detección de la ruta del GDS;
3. detección de la tecnología activa en KLayout;
4. localización del PDK dentro de `KLayout/salt`;
5. búsqueda recursiva del `.magicrc`;
6. adaptación del `.magicrc` para utilizar rutas WSL seguras;
7. conversión de rutas Windows → WSL;
8. creación de symlinks en `/tmp` cuando una ruta contiene espacios;
9. generación automática de scripts Tcl para LVS y PEX;
10. ejecución headless de MAGIC mediante `wsl.exe`;
11. validación automática de los archivos generados;
12. detección de fallos como timeout, `SIGSEGV`, PEX sin resistencias o resistencias negativas.

---

## Manejo de rutas Windows / WSL

El macro convierte automáticamente rutas de Windows:

```text
C:\Users\Nombre Apellido\KLayout\salt\CIDESI_CM05
```

a rutas WSL:

```text
/mnt/c/Users/Nombre Apellido/KLayout/salt/CIDESI_CM05
```

Si la ruta resultante contiene espacios, crea un symlink seguro dentro de `/tmp`.

Ejemplo:

```text
/tmp/cidesi_cm05_a1b2c3d4
        ↓
/mnt/c/Users/Nombre Apellido/KLayout/salt/CIDESI_CM05
```

Los symlinks se generan mediante WSL y utilizan un identificador derivado de la ruta original para reducir colisiones.

Este mecanismo se utiliza cuando es necesario para:

- PDK;
- `.magicrc`;
- GDS;
- archivos SPICE;
- scripts Tcl temporales.

---

## Flujo de ejecución

<p align="center">
  <img
    src="https://github.com/user-attachments/assets/817a9b37-65ff-480d-bad6-5ef4a0f52168"
    alt="Flujo de detección del PDK"
    width="480"
  />
</p>


## GDS de prueba

Para validar la v12 se utiliza un **Flip-Flop tipo D (D Flip-Flop)** implementado en la tecnología **CIDESI_CM05**.

Archivo utilizado durante las pruebas:

```text
FFD.gds
```

El diseño contiene la celda funcional:

```text
FFD
```

y se procesa mediante una celda superior:

```text
TOP
```

Este GDS se utiliza como caso de referencia para verificar:

1. lectura correcta del GDS;
2. carga de la jerarquía;
3. generación del netlist para LVS;
4. flatten del diseño para PEX;
5. extracción de resistencias y capacitancias parásitas;
6. generación de un SPICE full-RC válido.

### Captura del layout de prueba
<img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/19db0a0d-d447-4f2e-b3c0-e98bd4cbaf9f" />

*Layout de ejemplo utilizado para validar el flujo del sistema.*

<img width="1218" height="512" alt="image" src="https://github.com/user-attachments/assets/206fe622-1e0d-4614-b740-6cf54c16070a" />

captura más cercana del bloque FFD:


## Flujo LVS

El bloque denominado `LVS` dentro del macro genera un **netlist SPICE preparado para una posterior comparación layout-vs-schematic**.

La versión actual **no realiza por sí sola la comparación LVS final con un schematic externo** mediante herramientas como Netgen.

Flujo simplificado:
<p align="center">
  <img
    src="https://github.com/user-attachments/assets/ab572ef1-b604-42ca-b716-a96ec0b2aa17"
    alt="Flujo de detección del PDK"
    width="480"
  />
</p>


El resultado se guarda junto al GDS original:

```text
<celda>_lvs.spice
```


## Flujo PEX full-RC

La extracción PEX utiliza el mecanismo de resistencia integrado en versiones recientes de MAGIC.

Flujo simplificado:

<p align="center">
  <img
    src="https://github.com/user-attachments/assets/41cc07e9-001b-4002-878c-912637a436d1"
    alt="Flujo de detección del PDK"
    width="480"
  />
</p>

Durante el proceso se generan:

```text
<celda>.ext
<celda>.res.ext
<celda>_pex.spice
```

Los archivos `.ext` y `.res.ext` se mantienen dentro del directorio de trabajo para facilitar el diagnóstico de la extracción.

---

## Parámetros PEX actuales

La v12 utiliza:

```python
PEX_THRESHOLD_MOHM = 1
PEX_MINRES_MOHM = 1000
PEX_MINDELAY_PS = 0
PEX_SIMPLIFY = True
CTHRESH_FF = 0
```

Estos valores corresponden al estado actualmente validado del flujo.

`threshold = 1 mΩ` y `mindelay = 0` permiten incluir prácticamente todas las redes relevantes en el análisis resistivo, mientras que `minres` controla la simplificación de resistencias de muy bajo valor.

Estos parámetros pueden requerir calibración futura para otros procesos o PDKs.

---

## Detección del PDK

El macro consulta la tecnología activa de KLayout y busca el PDK correspondiente dentro de:

```text
<KLayout application data>/salt/
```

Ejemplo:

```text
KLayout/
└── salt/
    ├── CIDESI_CM05/
    └── CIDESI_TFS20/
```

Actualmente el flujo validado utiliza:

```text
CIDESI_CM05
```

`CIDESI_TFS20` permanece como trabajo futuro mientras se completa su `.magicrc` y su integración con MAGIC.

La selección se realiza de la siguiente manera:

<p align="center">
  <img
    src="https://github.com/user-attachments/assets/a3b86c6f-c8c4-4404-9756-e6723367c4dc"
    alt="Flujo de detección del PDK"
    width="480"
  />
</p>

###  Estructura del PDK

Si no existe una coincidencia exacta, el fallback se utiliza únicamente cuando existe **un solo PDK con `.magicrc` válido**.

Si existen varios candidatos, el macro no selecciona uno arbitrariamente.

Esto evita ejecutar accidentalmente un layout con una tecnología incorrecta.



## Búsqueda y preparación del `.magicrc`

La búsqueda del `.magicrc` es recursiva dentro del directorio del PDK.

Se da prioridad a:

```text
*_local.magicrc
```

y posteriormente a:

```text
*.magicrc
```

Los nombres que contienen `_local_local` se ignoran para evitar duplicaciones.

El macro puede generar o actualizar:

```text
<nombre>_local.magicrc
```

reemplazando las rutas necesarias por rutas WSL seguras.

---

## Ejecución de MAGIC

MAGIC se ejecuta desde Windows mediante:

```text
wsl.exe bash -c
```

con un comando equivalente a:

```bash
magic -dnull -noconsole -rcfile <magicrc> <script.tcl>
```

La ejecución es headless y el macro captura:

```text
stdout
stderr
return code
```

El timeout actual por ejecución es:

```text
300 segundos
```

---

## Validación automática del PEX

La generación de un SPICE por sí sola no se considera suficiente para declarar exitoso el PEX.

En v12, el PEX se considera válido únicamente cuando:

```text
Return code de MAGIC = 0
        AND
<celda>.ext existe
        AND
<celda>.res.ext existe
        AND
<celda>_pex.spice existe
        AND
Número de resistencias > 0
        AND
Resistencias negativas = 0
```

El macro analiza el SPICE generado y reporta:

```text
MOS
Resistencias
Capacitores
Resistencias negativas
```

También detecta explícitamente:

```text
Return code 139
```

correspondiente a un `SIGSEGV` de MAGIC.

---

## Resultado validado con CIDESI_CM05

Para el Flip-Flop tipo D utilizado como GDS de prueba se obtuvo:

```text
MOS:                    38
Resistencias:           119
Capacitores:            133
Resistencias negativas: 0
Return code:             0
```

También se generaron correctamente:

```text
TOP.ext
TOP.res.ext
TOP_lvs.spice
TOP_pex.spice
```

Resultado final:

```text
LVS: OK
PEX: OK
```

> Estas cantidades corresponden únicamente al circuito utilizado para las pruebas y no representan valores esperados para cualquier layout.

### Captura de ejecución

<img width="1913" height="1078" alt="Ejecución del macro Magic PEX" src="https://github.com/user-attachments/assets/1bfc7bb3-efee-491e-a305-47d7127a9247" />

*Ejecución del macro desde KLayout.*

### Imagen sugerida — Resumen final

```markdown
![Validación final LVS y PEX](docs/images/validacion_final.png)
```

> Imagen pendiente: `docs/images/validacion_final.png`

---

## Directorios y archivos generados

Los resultados finales se escriben junto al GDS original:

```text
<celda>_lvs.spice
<celda>_pex.spice
```

Los archivos intermedios se organizan en:

```text
<celda>_magic_work/
├── lvs/
└── pex/
```

Ejemplo:

```text
TOP_magic_work/
├── lvs/
│   └── TOP.ext
└── pex/
    ├── TOP.ext
    └── TOP.res.ext
```

Esto permite separar los archivos internos de MAGIC de los resultados finales.

---

## Requisitos

### Software

- KLayout con soporte de macros Python (`pya`);
- Windows con WSL habilitado;
- MAGIC VLSI instalado dentro de WSL y accesible como `magic`;
- PDK compatible con MAGIC;
- archivo `.magicrc` válido.

Versión validada:

```text
Magic 8.3 revision 683
```

### Python

No se requieren dependencias adicionales mediante `pip`.

El macro utiliza:

```text
pya
subprocess
os
time
re
shlex
hashlib
```

`pya` es proporcionado por KLayout y el resto pertenece a la biblioteca estándar de Python.

Ver también `requirements.txt`.

---

## Instalación

1. Coloca `magic_pex.py` en una ubicación desde la cual KLayout pueda cargar macros Python.

   Ejemplo utilizado durante el desarrollo:

   ```text
   <KLayout>/lvs/magic_pex.py
   ```

2. Verifica que el PDK esté disponible dentro de:

   ```text
   <KLayout>/salt/<PDK>/
   ```

3. El PDK debe contener un `.magicrc` válido en su raíz o en uno de sus subdirectorios.

4. Comprueba que MAGIC esté disponible dentro de WSL:

   ```bash
   magic --version
   ```

---

## Uso

1. Abre el GDS en KLayout.
2. Selecciona la celda que deseas procesar.
3. Verifica que el layout tenga asignada la tecnología correspondiente.
4. Ejecuta el macro desde KLayout.
5. Revisa la consola para confirmar:
   - celda detectada;
   - PDK detectado;
   - `.magicrc` utilizado;
   - resultado LVS;
   - resultado PEX.
6. Los archivos finales se generan junto al GDS original.

Una ejecución correcta termina con un resumen similar a:

```text
[Magic PEX] ===== RESULTADO FINAL =====
[Magic PEX] LVS: OK
[Magic PEX] PEX: OK
[Magic PEX] Return code: 0
[Magic PEX] Resistencias SPICE: 119
[Magic PEX] Resistencias negativas: 0
[Magic PEX] FIN
```

---

## Manejo de errores

La v12 incluye comprobaciones para detectar:

- ausencia de layout activo;
- GDS inexistente o inválido;
- imposibilidad de determinar el PDK;
- ausencia de `.magicrc`;
- errores al crear symlinks;
- timeout de MAGIC;
- `SIGSEGV` (`return code 139`);
- SPICE no generado;
- `.ext` no generado;
- `.res.ext` no generado;
- PEX sin resistencias;
- resistencias negativas.

Cuando MAGIC falla, el script Tcl puede conservarse para facilitar la depuración.

---



`magic_pex.py` corresponde a la versión estable más reciente.

La carpeta `versions/` conserva puntos importantes de la evolución del proyecto.

---

## Evolución del proyecto

### v8

Versión estabilizada del flujo histórico de extracción resistiva.

### v9

Introducción de una arquitectura experimental con:

```text
legacy
modern
auto
```

### v10

El flujo moderno pasa a ser el modo predeterminado.

### v11

Se eliminan los modos `legacy` y `auto`.

El macro pasa a utilizar exclusivamente la extracción full-RC moderna de MAGIC.

### v12

Versión estable actual.

Principales cambios:

- limpieza del código heredado;
- eliminación de variables y rutas sin uso;
- simplificación del flujo PEX;
- validación explícita de `.ext` y `.res.ext`;
- rechazo de PEX con resistencias negativas;
- mejora de la detección del PDK;
- fallback seguro cuando existe un único PDK válido;
- búsqueda recursiva del `.magicrc`;
- separación de directorios `lvs/` y `pex/`;
- mejora de mensajes y criterios de éxito;
- validación funcional con `CIDESI_CM05`;
- validación mediante un Flip-Flop tipo D.

---

## Limitaciones actuales

- Los parámetros PEX están definidos directamente en el código.
- No existe todavía una interfaz gráfica para configurar la extracción.
- El macro genera el netlist preparado para LVS, pero no realiza automáticamente la comparación contra un schematic.
- La calibración RC debe validarse para cada PDK/proceso.
- `CIDESI_TFS20` todavía no forma parte del flujo validado.
- Algunos warnings del GDS o del PDK pueden aparecer en `stderr` aunque MAGIC finalice correctamente.

---

## Roadmap

- [ ] Integrar y validar `CIDESI_TFS20`.
- [ ] Añadir una interfaz simple dentro de KLayout para configurar parámetros de extracción.
- [ ] Permitir selección explícita del PDK cuando existan múltiples candidatos válidos.
- [ ] Integrar una herramienta de comparación LVS.
- [ ] Calibrar parámetros PEX para diferentes procesos.
- [ ] Generar reportes automáticos de extracción.
- [ ] Validar el flujo sobre otros bloques y jerarquías.
- [ ] Completar la documentación visual del repositorio.

Por el momento, **v12 constituye el punto estable del desarrollo**.

---

