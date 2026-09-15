# Por qué la partida vive en Roblox y no en Praxsuite

Hasta hace poco, este place mostraba a Praxsuite como el motor completo del juego: cada click
llamaba a una automatización (`buscaminas-jugar`) que sembraba las minas, hacía el flood-fill y
devolvía el resultado. Funcionaba, pero cada jugada pagaba una vuelta de red completa —
Roblox → gateway → automatización → base de datos → automatización → gateway → Roblox — antes de
que el jugador viera el efecto de su click. Con varios clicks seguidos (abrir una zona vacía a las
apuradas, por ejemplo) esa latencia se sentía.

## El cambio de arquitectura

**El gameplay en sí vive enteramente en Roblox** (`BuscaminasMotor.lua`, ver más abajo).
**Praxsuite es infraestructura de plataforma, no árbitro de cada click**: cuentas
(`Auth.LoginPlayer`), cosméticos (`Canjear`/`MisCosmeticos`/`Equipar`) y el marcador cruzado con
Unity/web. Es el patrón que se usa en un juego real con un motor que ya tiene su propio backend:

> Roblox ya trae su propio modelo de confianza servidor-cliente — el `ServerScriptService` de
> este place SIEMPRE fue "la parte de confianza" (ver el comentario largo de `Data.lua` en el
> SDK). Mover el cálculo de la partida ahí no relaja ninguna garantía de seguridad que este demo
> tuviera antes: la matriz de minas sigue sin llegar nunca al cliente, sólo cambió en qué proceso
> vive del lado servidor. Lo que Praxsuite aporta acá no es "árbitro de cada click" — es la capa
> compartida entre plataformas: identidad, comercio (cosméticos) y métricas (el leaderboard).

Esto no es una regla universal ("la lógica de juego nunca debe vivir en Praxsuite") — es una
decisión por feature. Ver la guía general en el repo del SDK
(`Praxsuite-SDK-Lua/docs/motor-local-vs-automatizaciones.md`) para el criterio que se usó acá y
cómo aplicarlo a otra decisión.

## Vuelta parcial: por qué Praxsuite sí vuelve a hablar con la partida (dos veces, no por click)

La primera versión de este cambio sacó a Praxsuite del todo: `NuevaPartida` generaba el código
local y el leaderboard se escribía con un `Praxsuite.Data.Insert` directo, sin que nadie del lado
de Praxsuite supiera cómo era el tablero. Funcionaba, pero dejaba un agujero: nada impedía que un
resultado corrupto (un bug en el motor local, o un reporte manipulado) escribiera cualquier
puntaje al leaderboard compartido — no había ningún registro independiente contra el cual
compararlo.

La corrección **no revive las automatizaciones por click** — el problema de latencia era ahí, no
en el juego completo. Es agregar de vuelta **dos llamadas por partida, no por click**:

1. **Al abrir la partida**, `NuevaPartida` vuelve a llamar a la automatización
   `buscaminas-nueva-partida`. Le devuelve el código, filas, columnas y minas — que Praxsuite
   guarda como fila en `Buscaminas Partidas` — y con eso arma `BuscaminasMotor.Nueva(...)` local.
   Una llamada HTTP al empezar es imperceptible; el juego sigue sin red por click.
2. **Al terminar la partida**, en vez de escribir directo al leaderboard, se llama a la
   automatización nueva `buscaminas-validar-resultado`, que compara el resultado reportado contra
   esa misma fila (dimensiones y cantidad de minas — nunca lo que manda el cliente) y sólo si es
   consistente cierra la partida y escribe el leaderboard.

Si Praxsuite no contesta al abrir la partida (`registrada = false` en la sesión), el juego sigue
siendo jugable igual — sólo que esa partida en particular no se valida ni entra al leaderboard al
terminar. El gameplay nunca depende de que Praxsuite esté arriba.

### Qué verifica `buscaminas-validar-resultado`

El endpoint recibe `{ codigo, estado, matriz, revelado, banderas, puntaje, segundos, ... }` — el
resultado final tal como quedó el motor local — y antes de escribir nada revisa, todo del lado
servidor:

- La partida existe y sigue `"En curso"` (una fila ya cerrada rechaza cualquier reintento —
  protección contra volver a mandar la misma partida dos veces).
- La matriz reportada tiene exactamente la cantidad de minas que generó `Nueva Partida`
  (`Filas`/`Columnas`/`Minas` de la fila, nunca del payload) y las medidas coinciden.
- Cada número no-mina de la matriz es consistente con las posiciones de minas reportadas
  (recalculado celda por celda) — no alcanza con mandar una matriz cualquiera con la cantidad
  correcta de minas.
- Si `estado = "Ganada"`: ninguna celda revelada es una mina, y están reveladas *todas* las celdas
  seguras (`filas × columnas − minas`).
- Si `estado = "Perdida"`: al menos una celda revelada es una mina.
- El puntaje se recalcula con la misma fórmula que usaba `buscaminas-jugar`
  (`reveladas × 10`, más `minas × 50 + max(0, 600 − segundos) × 2` si ganó) y tiene que coincidir
  exacto con lo reportado.

Si cualquiera de estos chequeos falla, la automatización no toca la fila ni el leaderboard —
responde `{ ok: false, motivos: [...] }` y el jugador ya vio su resultado local de todas formas
(la validación es asíncrona, `task.spawn`, nunca bloquea el click ni el fin de partida).

Probado en vivo (2026-09-09): un resultado válido cierra la fila y escribe el leaderboard; el
mismo código reenviado se rechaza (`partida_ya_cerrada`); un resultado alterado a mano (dice que
ganó pero deja una celda segura sin revelar, con puntaje inventado) se rechaza
(`gano_pero_no_revelo_todas_las_celdas_seguras`) sin tocar la fila. Una sesión real de Play
(8×8, 10 minas) corrió el flujo completo — login, apertura, 33 clicks locales, derrota — y el
puntaje que calculó Roblox (330) llegó intacto al leaderboard tras pasar la validación.

## Qué se movió, y a dónde

| Antes (automatizaciones por click) | Ahora (híbrido) |
|---|---|
| Click → `Endpoints.Call("Jugar")` → automatización `buscaminas-jugar` (siembra, flood-fill, puntaje, `UpdateRows`) → respuesta | Click → `BuscaminasMotor.Jugar(partida, accion, fila, columna)`, local, síncrono, sin red — **sin cambios** |
| `NuevaPartida` → `Endpoints.Call("NuevaPartida")` → automatización `buscaminas-nueva-partida` → respuesta, en cada click de apertura | `remotes.NuevaPartida.OnServerInvoke` llama a la misma automatización **una vez por partida**, arma `s.partida = Motor.Nueva(...)` con lo que devuelve (o local puro si Praxsuite no contestó) |
| El leaderboard se escribía dentro de `buscaminas-jugar` (`InsertRows` a `Demos Leaderboard`) | Al terminar, `validarResultado()` llama a `buscaminas-validar-resultado`; sólo si valida, esa automatización cierra la fila e inserta el leaderboard |

Lo que **no** cambió: `Auth.LoginPlayer` (login), `Canjear`/`MisCosmeticos`/`Equipar` (cosméticos,
automatizaciones sin tocar), la lectura del leaderboard (`Endpoints.Call("Leaderboard")`, sigue
siendo la automatización — hace dedupe y formateo que no vale la pena duplicar en Luau para una
lectura ocasional), y sobre todo: **cero llamadas a Praxsuite por click**. La automatización
`buscaminas-jugar` sigue existiendo en el workspace tal cual — Roblox simplemente no la llama;
Unity o una demo web podrían seguir usándola.

## El código, archivo por archivo

- **`ServerScriptService.BuscaminasMotor`** (ModuleScript) — el álgebra del juego, sin ninguna
  llamada a Praxsuite adentro. Puerto 1:1 del script JavaScript que tenía la automatización:
  - `Motor.GenerarCodigo()` — código de 8 caracteres, mismo alfabeto que usaba Praxsuite. Sólo se
    usa como respaldo si `NuevaPartida` no pudo hablar con Praxsuite.
  - `Motor.Nueva(filas, columnas, minas, codigo)` — arma el estado vacío, sin sembrar. El tipo
    `Partida` tiene un campo `registrada: boolean?` — true si esta partida tiene fila en
    `Buscaminas Partidas` contra la cual `validarResultado` puede comparar al terminar.
  - `Motor.VistaVacia(filas, columnas)` — todo `"?"`, para pintar el tablero antes del primer click.
  - `Motor.Jugar(partida, accion, fila, columna)` — siembra en la primera jugada válida (dejando
    libre el 3x3 alrededor de la celda tocada), flood-fill iterativo, detecta victoria/derrota,
    calcula puntaje. Nada de esto hace I/O ni yields — corre entero de un tirón.
- **`ServerScriptService.BuscaminasServidor`**:
  - `remotes.NuevaPartida.OnServerInvoke` — resuelve la dificultad contra `PRESETS` (mismos valores
    que usa la automatización: facil 8×8/10, medio 12×12/24, dificil 16×16/45), llama a
    `Endpoints.NuevaPartida` y arma `s.partida = Motor.Nueva(...)` con el código/dimensiones que
    devuelve Praxsuite (o generados local si la llamada falla). Una sola llamada HTTP por partida.
  - `jugar()` — sigue llamando `Motor.Jugar(s.partida, ...)` directo, sin red. Si `datos.terminada`,
    dispara `validarResultado()` (fire-and-forget) y limpia `s.partida`.
  - `aplanar0a1(t, filas, columnas)` — convierte una grilla 0-indexada (como las arma
    `BuscaminasMotor`) a un array Lua 1-indexado secuencial. Necesario porque
    `HttpService:JSONEncode` sólo serializa como array JSON una tabla 1-indexada; una tabla con
    clave `0` se codifica como objeto (`{"0": ...}`), y `buscaminas-validar-resultado` rechaza esa
    forma.
  - `validarResultado(jugador, s, partida, datos)` — si `partida.registrada`, manda el resultado
    final (matriz/revelado/banderas aplanados, estado, puntaje, segundos) a
    `Endpoints.Validar`, en `task.spawn` para no bloquear nada. Si Praxsuite rechaza el resultado,
    sólo queda un `warn` en el output — el jugador ya vio su resultado local, lo único que se
    pierde es esa fila del leaderboard cruzado.
  - `Praxsuite.Schema.Register("Demos Leaderboard", "...")` — se registra a mano una vez al
    arrancar el servidor, porque el SDK necesita resolver el nombre de tabla a su UUID en algún
    punto y `autoFetchSchema` está apagado.
- **`ServerScriptService.BuscaminasEndpoints`** — sumó `NuevaPartida` (abrir partida) y `Validar`
  (cerrar partida) a los cuatro que ya estaban (`Leaderboard`, `Canjear`, `MisCosmeticos`,
  `Equipar`). `Jugar` (el endpoint de la automatización vieja, por click) sigue sin usarse.

## El trade-off que esto acepta

`buscaminas-jugar` era, y sigue siendo, una automatización **agnóstica de motor** — el mismo
código resuelve la partida sin importar si el pedido viene de Roblox, Unity o un navegador. Roblox
tiene su propia copia de esa lógica en Luau (`BuscaminasMotor` para jugar, y una segunda copia del
cálculo de puntaje dentro de `buscaminas-validar-resultado` para verificar). Si el día de mañana
se cambia la fórmula de puntaje o el algoritmo de siembra del lado de Praxsuite, hay que replicar
el cambio en ambos lugares a mano — no hay una sola fuente de verdad entre motores para *cómo se
juega*, y ahora tampoco para *cómo se valida*. Lo que sí es una sola fuente de verdad, y por eso
vale la pena la doble llamada por partida: *contra qué se compara* (la fila que abrió
`Nueva Partida`) y *dónde termina* (el mismo leaderboard, compartido entre los tres motores).
