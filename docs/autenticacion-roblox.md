# Autenticación: login directo con la cuenta de Roblox

Este documento es el mapa de "qué archivo hace qué" para el login de este place. Complementa al
`README.md` (que da la vista general de arquitectura) con el detalle línea por línea: qué
instancia, qué función, qué responsabilidad.

> Nota: el place es un `.rbxl` binario — no hay filesystem de texto, así que "archivo" acá
> significa instancia de Studio (Script / LocalScript / ModuleScript), direccionada con notación
> de punto (`game.ServerScriptService.X`). Los números de línea son una foto del momento en que se
> escribió esto; si el script se edita después van a correrse. Para la mecánica general del
> gateway (qué es un "proveedor", por qué una clave necesita estar "marcada para una plataforma"),
> ver `Praxsuite-SDK-Lua/docs/game-platforms-api-gateway.md` en el repo del SDK — esta página sólo
> cubre cómo se usa **acá adentro**.
>
> Esto es el punto de partida. Cuando se implemente el bus de eventos para las integraciones de
> plataforma es esperable que el flujo de login cambie — no lo tomes como diseño final.

---

## El recorrido completo, en orden

1. **`game.ServerScriptService.PraxsuiteConfig`** — de dónde sale la clave.

   ```lua
   apiKeySecret = "PraxsuiteKey",
   ```

   Antes del login de Roblox esto era un relleno (`apiKey = "los-endpoints-no-piden-clave"`),
   porque el juego sólo llamaba endpoints de automatización, que no piden autenticación. Ahora
   `Auth.LoginPlayer` llama directo al gateway (`auth/roblox/assert`), que sí la exige — por eso
   pasó a ser un `apiKeySecret` real, resuelto en runtime desde el Secrets Store de Roblox
   (Game Settings → Security → Secrets Store, mismo nombre: `PraxsuiteKey`).

2. **`game.ServerScriptService.PraxsuiteSDK.Auth`** — el módulo que hace el pedido.

   `Auth.LoginPlayer(player)` es la única función que le importa a este juego. Lee
   `player.UserId` (que el jugador no puede falsificar), llama
   `POST auth/{provider}/assert` con ese id, y cachea la sesión resultante en memoria del
   servidor (`_sessions[player.UserId]`), renovándola sola 60s antes de expirar. `provider` sale
   de `Config._authProvider`, que por defecto es `"roblox"`.

   También expone `GetSession`, `GetTokenFor` (usado internamente por `Data`/`Endpoints` cuando
   se pasa `asPlayer`), `Forget` y `ForgetAll` — este juego sólo usa `LoginPlayer` y `Forget`.

3. **`game.ServerScriptService.BuscaminasServidor`** — dónde se decide cuándo loguear.

   | Qué | Función / línea aprox. | Qué hace |
   |---|---|---|
   | Login en sí | `iniciarSesion(jugador)`, ~L68-88 | Llama `Praxsuite.Auth.LoginPlayer(jugador)` en un `pcall`, y si sale bien arma la fila de sesión local: `{ alias, endUserId, codigo, dificultad, estilo }`. El `endUserId` es la cuenta de Praxsuite — es lo que después identifica al jugador ante los endpoints de cosméticos. Si ya hay una sesión con `endUserId` cacheado, devuelve esa sin pegarle de nuevo al gateway. |
   | Login temprano | `Players.PlayerAdded`, ~L351-354 | Dispara `task.spawn(iniciarSesion, jugador)` apenas el jugador entra al server, sin esperar al cliente — para cuando el HUD lo pida, la sesión suele estar lista. |
   | Login bajo demanda | `remotes.Login.OnServerInvoke`, ~L203-212 | Lo que el cliente invoca. Sin argumentos — antes recibía `email, password`. Llama `iniciarSesion` (que devuelve la cacheada si ya existe) y responde `{ ok, alias }` o `{ ok = false, mensaje }`. |
   | Logout | `Players.PlayerRemoving`, ~L365-371 | Además de limpiar la sesión local y el tablero, llama `Praxsuite.Auth.Forget(jugador)` para no dejar la sesión cacheada de un jugador que ya se fue. |

   El resto del script (`NuevaPartida`, `Jugar`, `Canjear`, `Equipar`, `Leaderboard`) no cambió de
   lógica — sólo cambió **de dónde sale** `s.endUserId` (antes: la respuesta de la automatización
   `Login`/`Registro`; ahora: `Auth.LoginPlayer`).

4. **`game.ReplicatedStorage.BuscaminasRemotes.Login`** (`RemoteFunction`) — el único remote de
   acceso que queda activo. Sigue llamándose `Login` en el árbol (no se renombró a algo como
   `IniciarSesion` para no tocar la jerarquía de Studio sin querer), pero ya no recibe
   credenciales: es un `InvokeServer()` sin argumentos. `Registrar` sigue existiendo como
   instancia pero quedó sin handler del lado del servidor — es candidato a borrar a mano si
   molesta verlo en el Explorer.

5. **`game.StarterPlayer.StarterPlayerScripts.BuscaminasCliente`** — el gate de conexión.

   | Qué | Función / línea aprox. | Qué hace |
   |---|---|---|
   | Panel de acceso | construcción de `acceso`/`estadoAcceso`, ~L67-105 | Ya no tiene pestañas Entrar/Crear cuenta ni campos de email/clave/alias — sólo título, una bajada de texto y un estado ("Conectando con tu cuenta de Roblox…"). |
   | Disparo del login | `conectar()`, ~L654-682 | Llama `remotes.Login:InvokeServer()` sin argumentos. Si `resp.ok`, pasa a `entrarAlJuego(resp.alias)`, que oculta el velo y muestra el HUD. Se dispara sola al final del script (`conectar()`, última línea) — no hay botón que apretar. |

---

## Configurar esto en un workspace nuevo

Clonar este place a otro workspace de Praxsuite necesita, además de lo que ya dice el `README.md`
(workspace ID, UUIDs de endpoints):

1. Un proveedor con slug `roblox` (u otro, pasado como `authProvider` en `Init`) registrado y
   activo en **Settings → API Gateway** del workspace nuevo.
2. Un rol por defecto asignado a ese proveedor — si no, el login abre sesión pero la cuenta no
   alcanza ninguna tabla.
3. Una API Key `sk_live_...` del workspace nuevo, **marcada para esa plataforma** desde el portal
   (esto no es configurable por API/MCP), cargada en el Secrets Store de Roblox Studio bajo el
   nombre que diga `apiKeySecret` en `PraxsuiteConfig` (`PraxsuiteKey` por defecto).

El detalle de cada paso, y los mensajes de error exactos si falta alguno, están en
`Praxsuite-SDK-Lua/docs/game-platforms-api-gateway.md`.
