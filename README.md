# Praxsuite AppSource — Roblox Game

Experiencia de demostración en Roblox que usa **Praxsuite como infraestructura de plataforma**:
cuentas de jugador, tienda de cosméticos y ranking cruzado con otros motores — todo consumido con
el **SDK de Lua**. El *gameplay* en sí (la partida de Buscaminas) es autoridad de Roblox: corre
local en `ServerScriptService`, sin ninguna llamada de red por jugada. Es el patrón de un juego
real que ya tiene su propio backend — Roblox aporta la seguridad servidor-cliente de la partida,
Praxsuite aporta lo que un motor solo no puede: identidad compartida entre plataformas, comercio y
métricas. El porqué de esa división está en [`docs/motor-local.md`](docs/motor-local.md).

Este repositorio contiene el place de Roblox Studio listo para abrir:

```text
RobloxSDKDemo.rbxl
```

---

## Enlaces

| Recurso | Enlace |
| --- | --- |
| Implementación del SDK genérico (Lua) | https://learn.praxsuite.com/examples/lua/lua-sdk-implementation |
| Ejemplo actual de Roblox (caso de uso) | https://learn.praxsuite.com/examples/lua/lua-sdk-use-case |
| Documentación de Praxsuite | https://learn.praxsuite.com |
| Workspace de prueba | ffd80539-a1e2-4a9e-8b33-f716bf690281 |

---

## Qué hace la experiencia

Es un **Buscaminas multijugador**: la partida corre local en Roblox, y Praxsuite hace de
infraestructura compartida (cuenta, cosméticos, ranking) alrededor.

- **La cuenta es tu cuenta de Roblox.** No hay pantalla de registro ni contraseña: el servidor lee
  `player.UserId` con `Praxsuite.Auth.LoginPlayer` y Praxsuite crea o reconoce la cuenta la primera
  vez que te ve. La identidad vive en Praxsuite, así que el progreso es del jugador y no del place:
  la misma cuenta sirve para cualquier otro cliente (Unity, navegador) que hable con el mismo
  workspace y tenga el proveedor `roblox` — o el que corresponda — registrado.
- **El tablero es geometría real.** No es una interfaz: es una grilla de partes en el `Workspace`,
  con un `ClickDetector` por celda. Clic izquierdo revela, clic derecho pone o saca bandera. Al ser
  geometría del servidor, el cliente no puede inventar una jugada — solo puede tocar una celda que
  realmente existe.
- **La partida corre local, en el servidor de Roblox.** La matriz de minas, el *flood fill* de
  celdas vacías y el cálculo de puntaje son responsabilidad de `BuscaminasMotor.lua` — sin ninguna
  llamada a Praxsuite por click, así que un click se resuelve en milisegundos, no en la vuelta de
  red que tomaba antes. El cliente se ocupa del acceso, el HUD y el marcador, nada más.
- **Ranking persistente, cruzado y validado.** Al abrir la partida, Praxsuite genera el código y las
  dimensiones (una llamada, no por click) — ese es el punto de comparación. Al terminar, el
  resultado se manda a validar contra esa fila antes de escribir el leaderboard: sólo si es
  consistente entra a `Demos Leaderboard`, el mismo marcador que leen Unity y la web.
- **Tienda de cosméticos.** Con los puntos ganados se canjean accesorios (`Canjear`), se listan los
  propios (`MisCosmeticos`) y se equipan sobre el avatar (`Equipar`).

---

## Arquitectura

```text
Cliente (LocalScript)          Servidor (Script)              Praxsuite
─────────────────────          ─────────────────              ─────────
BuscaminasCliente              BuscaminasServidor             gateway
  · gate de conexión     ──▶     · login de Roblox       ──▶    Auth.LoginPlayer
  · HUD y marcador       RemoteFunction/Event                    Endpoints
  · clic sobre celdas            BuscaminasMotor (local)           · Nueva Partida (al abrir)
                                 · matriz de minas                 · Validar Resultado (al cerrar)
                                 · flood fill                      · Leaderboard (lectura)
                                 · puntaje                         · Canjear / MisCosmeticos / Equipar
                                 sin red por click
```

**Regla de oro:** el único lado que habla con Praxsuite es el servidor — eso no cambió. La jugada
en sí (cada click) no necesita hablarle a Praxsuite para resolverse: `BuscaminasMotor` es la
autoridad, corriendo en el mismo proceso de confianza, y ahí no hay red. Lo que sí vuelve a hablar
con Praxsuite es la partida como un todo — abrirla y cerrarla, una vez cada una, nunca por click —
para que el resultado final se pueda validar contra algo que Praxsuite generó de antemano en vez
de aceptarse a ciegas. El cliente sigue sin tener forma de pedir una jugada falsa, porque el
tablero es geometría del servidor y no existe un remote que acepte una jugada sin pasar por él. Ver
[`docs/motor-local.md`](docs/motor-local.md) para el detalle de la validación.

### Contenido del place

| Ubicación | Instancia | Rol |
| --- | --- | --- |
| `ServerScriptService` | `PraxsuiteSDK` | El SDK de Lua (`Config`, `Http`, `PraxQL`, `Data`, `Endpoints`, `Players`, `Schema`, `Auth`) |
| `ServerScriptService` | `BuscaminasServidor` | Sesión, orquestación, y la única parte que habla con Praxsuite |
| `ServerScriptService` | `BuscaminasMotor` | La partida en sí — siembra, flood-fill, puntaje. Sin Praxsuite adentro |
| `ServerScriptService` | `Tablero`, `Estilo`, `Accesorio` | Módulos de apoyo: construcción de la grilla, tema visual, cosméticos |
| `ReplicatedStorage` | `BuscaminasRemotes` | `Login` (sin credenciales — login de Roblox), `NuevaPartida`, `Jugar`, `Leaderboard`, `Canjear`, `MisCosmeticos`, `Equipar` |
| `StarterPlayerScripts` | `BuscaminasCliente` | Acceso, HUD y marcador |

`Login`, `Leaderboard`, `Canjear`, `MisCosmeticos` y `Equipar` tienen su endpoint espejo en
Praxsuite (automatizaciones en modo *Sync*, o la ruta `auth/roblox/assert` para el login).
`Jugar` (cada click) ya no llama a Praxsuite — lo resuelve `BuscaminasMotor` local. `NuevaPartida`
sí vuelve a llamar a Praxsuite, pero una sola vez por partida (al abrirla), y al cerrarla se suma
una llamada más a un endpoint de validación (`Validar`) antes de escribir el leaderboard — ver
[`docs/motor-local.md`](docs/motor-local.md) para el porqué y el detalle.

Para el detalle línea por línea de cómo funciona el login (qué archivo hace qué, y cómo
configurarlo en un workspace nuevo), ver [`docs/autenticacion-roblox.md`](docs/autenticacion-roblox.md).
Además, cada partida publica `game.started`/`jugada` al Event Bus para quien quiera espectarla
desde otra plataforma — ver [`docs/bus-eventos.md`](docs/bus-eventos.md), que incluye un bug de
backend pendiente que vale la pena conocer antes de tocar esa parte.

---

## Cómo ejecutarlo

1. Abre `RobloxSDKDemo.rbxl` en Roblox Studio.
2. Habilita el acceso HTTP: **Game Settings → Security → Allow HTTP Requests**.
3. Carga tu API Key en **Game Settings → Security → Secrets Store** con el nombre `PraxsuiteKey`.
   Para pruebas locales rápidas se puede pasar la clave directamente en `Init`, pero nunca así en
   producción. A diferencia de los endpoints (que no piden clave porque la valida la automatización
   del otro lado), `Auth.LoginPlayer` sí llama directo al gateway — la clave tiene que ser una
   `sk_live_` real, marcada para la plataforma `roblox` en **Settings → API Gateway** del workspace,
   con al menos un rol por defecto configurado (si no, la cuenta se crea pero no alcanza ninguna
   tabla).
4. En `BuscaminasServidor`, ajustá el `workspaceId`; en `BuscaminasEndpoints`, los UUID de los
   seis endpoints que quedan (`NuevaPartida`, `Validar`, `Leaderboard`, `Canjear`,
   `MisCosmeticos`, `Equipar`) a los de tu workspace. `Jugar` no necesita UUID — cada click lo
   resuelve `BuscaminasMotor` local.
5. Presiona **Play**. No hay pantalla de registro: el servidor te loguea solo contra tu cuenta de
   Roblox apenas entrás, y pasás directo al tablero.

> **Nunca** llames al SDK desde un `LocalScript`. Cualquier cosa que un cliente pueda leer, un
> jugador la puede extraer.

---

## Configuración

El servidor inicializa el SDK una sola vez:

```lua
local Praxsuite = require(game:GetService("ServerScriptService").PraxsuiteSDK)

Praxsuite.Init({
    workspaceId     = "tu-workspace-uuid",              -- Para este ejemplo hay que utilizar este worksapce que tiene todas las tablas
    apiKeySecret    = "PraxsuiteKey",                   -- nombre en el Secrets Store de Roblox
    baseUrl         = "https://gateway.praxsuite.com",  -- obligatorio: sin esto el SDK no arranca
    autoFetchSchema = false,                            -- endpoints y tablas se registran a mano
})
```

Los UUID de los seis endpoints que siguen pasando por Praxsuite (`NuevaPartida`, `Validar`,
`Leaderboard`, `Canjear`, `MisCosmeticos`, `Equipar`) están en `BuscaminasEndpoints`, junto al
`workspaceId` en `BuscaminasServidor`. Al clonar el workspace de la demo hay que reemplazarlos
por los del workspace nuevo — y registrar `Demos Leaderboard` (o la tabla que uses) con
`Praxsuite.Schema.Register` para que `Data.Insert` pueda resolverla.

---

## Licencia

Consulta el repositorio del SDK de Lua para los términos de la licencia Praxsuite Open SDK.
