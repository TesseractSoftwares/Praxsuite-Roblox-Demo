# Event Bus desde Roblox: qué se implementó y qué se descartó

Este documento cierra la investigación sobre usar el Event Bus de Praxsuite desde este place, y
la revisa después de un cambio de alcance. Léelo junto a [`motor-local.md`](motor-local.md) — la
partida ya no necesita el bus para nada (eso lo resolvió correr el motor local), así que todo lo
de acá es sobre **avisar hacia afuera** cosas puntuales del juego, no sobre la partida en sí.

> **Actualización — ya no es solo Roblox.** Todo lo de acá vive en `buscaminas-validar-resultado`
> y `buscaminas-anunciar-cosmetico`, dos automatizaciones de Praxsuite, agnósticas de motor. Desde
> que TypeScript (`Praxsuite-AppSource-TypescriptGame`) y Unity (proyecto `PraxsuiteSDKDemo`)
> migraron también a motor local + validar-resultado (mismo patrón que este place, ver sus propios
> `docs/motor-local.md`), **cualquier partida de cualquier motor que llame a Validar Resultado
> dispara el mismo aviso de top-3** si el puntaje entra — no hace falta que sea Roblox. La
> automatización ya lo hacía "gratis" para cualquier motor desde el día uno (el `Motor`/`SDK` que
> viajan en el payload son solo metadata para el leaderboard); lo que cambió es que ahora hay más
> de un cliente real ejercitando ese camino. Se confirmó en vivo (2026-09-10): partidas validadas
> desde Unity (`motor: unity, sdk: csharp`) y desde la demo web (`motor: web, sdk: typescript`)
> conviven en el mismo `Demos Leaderboard` junto a Roblox y a una cuarta integración
> (`motor: minecraft, sdk: java`) que tampoco se armó desde este repo. Cada demo documenta esto en
> su propio `docs/bus-eventos.md`, apuntando acá para el detalle completo; no hay nada que
> mantener sincronizado entre ellos porque ninguno tiene código propio del bus — todo vive en las
> dos automatizaciones.

---

## Estado actual

| Capacidad | Estado |
|---|---|
| Roblox **publica** al bus por HTTP, sin WebSocket | ✅ Implementado — `BuscaminasBus.lua` (mecanismo original) y, desde el backend, `EventBusPublishController` |
| Notificación de **top 3** al terminar una partida validada | ✅ Implementado en `buscaminas-validar-resultado`, para **cualquier motor** que la llame (Roblox, TypeScript, Unity, y ahora también un cliente Minecraft/Java) — ⚠️ no publica todavía, ver "El bloqueo actual" |
| Anuncio periódico de **código cosmético** canjeable | ✅ Implementado en `buscaminas-anunciar-cosmetico` (cada hora), agnóstico de motor — ⚠️ mismo bloqueo |
| Roblox **recibe** del bus (presencia, espectar en vivo) | ❌ Descartado — decisión de alcance, no una limitación técnica (ver abajo) |
| `game.started` / `jugada` publicados por click | ⚠️ El código sigue ahí y sigue corriendo, pero **nadie lo escucha** — ver "Qué quedó huérfano" |

---

## Cambio de alcance: se descartó el live-spectate

La idea original era que Roblox publicara cada `jugada` y otro cliente (web, Unity) se uniera al
bus con un WebSocket real para espectar la partida en vivo. Eso implicaba escribir un cliente
SignalR completo en Luau (handshake, `JoinBus`, parseo de mensajes entrantes, reconexión, pings de
keepalive) — mucho trabajo para un caso de uso que no era el prioritario. La decisión fue
explícita: **no vale la pena esa inversión**, y en cambio el bus se usa para dos cosas puntuales,
las dos *sólo publicar*, sin que Roblox necesite escuchar nada nunca:

1. **Aviso de puntaje top 3** — cuando `buscaminas-validar-resultado` valida un resultado y el
   puntaje entra en el top 3 del leaderboard, publica un evento. Para quien esté armando un
   dashboard o un bot que quiera destacar "nuevo récord", sin tener que hacer polling a la tabla.
2. **Anuncio de código cosmético** — cada una hora, `buscaminas-anunciar-cosmetico` toma un código
   activo y sin usar de `Codigos Cosmeticos` y lo publica. No lo consume ni lo marca usado — eso
   sigue pasando sólo cuando alguien lo canjea de verdad vía `Canjear`.

Ambos son **publish-only desde una automatización de Praxsuite**, no desde Roblox — Roblox no
está involucrado en ninguno de los dos. Por eso ninguno necesita el cliente WebSocket que se
había descartado: una automatización corre del lado del servidor de Praxsuite, así que un simple
nodo `HttpRequest` alcanza.

### Qué quedó huérfano

`BuscaminasServidor.lua` sigue llamando a `anunciar()` para publicar `game.started` (al abrir
partida) y `jugada` (en cada click) al bus — el mecanismo original, pensado para el live-spectate
que ya no existe. Sigue siendo inofensivo (`task.spawn`, fire-and-forget, un `warn` si falla) pero
hoy no le sirve a nadie: no hay ningún cliente uniéndose a `minesweeper:{codigo}` para recibirlo.
Queda como está hasta que se decida explícitamente sacarlo o encontrarle un uso real — no se tocó
en este pase para no mezclar una limpieza con el cambio de alcance.

---

## Corrección sobre un supuesto anterior: Roblox sí tiene WebSocket, y `JoinBus` ya funciona

Dos cosas que se investigaron y quedan documentadas por si alguien retoma la idea de espectar en
vivo más adelante:

**Roblox sí puede hablar WebSocket.** El método real es
`HttpService:CreateWebStreamClient(Enum.WebStreamClientType.WebSocket, { Url = ... })` — no
`CreateWebSocketAsync` ni `CreateWebSocket`, que no existen (esa fue la conclusión incorrecta de
una primera pasada).

**El bug que bloqueaba `JoinBus` está resuelto.** En su momento, invocar `JoinBus` sobre una
conexión WebSocket real devolvía el error genérico de SignalR
(`"Failed to invoke 'JoinBus' due to an error on the server"`) — una excepción sin manejar, no un
rechazo limpio. La causa nunca se confirmó contra logs de Azure, pero coincidía con el modo de
falla de un backplane Redis caído (documentado en
`Core/mdcontext/REALTIME_BACKPLANE_INFRA.md`). El fix (`TryBackplaneAsync` envolviendo las
llamadas al backplane en `EventBusHub`, más un endpoint HTTP nuevo para publicar sin WebSocket)
se implementó, se probó en vivo el 2026-09-09 contra el ambiente real de `development`
(`api.dev.praxsuite.com`) con dos conexiones WebSocket reales — `JoinBus` devuelve
`{"ok":true,"peers":[]}` limpio, y un peer recibe el `bus-event` del otro. **Funciona.** Sigue sin
haber un cliente Luau que lo use (se descartó, ver arriba), pero la vía ya no está rota.

---

## Los dos usos nuevos, en detalle

### Top 3 — dentro de `buscaminas-validar-resultado`

La automatización (ver [`motor-local.md`](motor-local.md) para el resto de lo que hace) ya
consulta el top 3 actual del leaderboard *antes* de insertar la partida nueva (para poder decidir
si el puntaje entra, sin tener que volver a consultar después del insert). Ese cálculo
(`esTop3`) es un output más del nodo Script. Después de cerrar la partida y registrar el
leaderboard, un `IfElse` revisa `esTop3`:

- **Si "no"** → responde directo, nada más.
- **Si "si"** → un nodo `Vault` resuelve la API key (`buscaminas_bus_publish_key`, secreto del
  workspace) y un `HttpRequest` publica:

```json
POST {baseUrl}/api/v1/gateway/{workspaceId}/bus/leaderboard/buscaminas/publish
x-api-key: {{vault.busKey}}

{ "event": "top_score", "payload": { "alias": "...", "puntaje": 1280, "dificultad": "facil", "motor": "roblox", "codigo": "..." } }
```

Bus key: `leaderboard:buscaminas` (topic `leaderboard`, `presence_enabled: false` — nadie necesita
unirse, sólo recibir publicaciones si algún día alguien escucha).

### Código cosmético — `buscaminas-anunciar-cosmetico` (automatización nueva)

Trigger por `ScheduleTrigger`, intervalo de 3600 segundos. Busca en `Codigos Cosmeticos` un
código con `Activo = true` y `Usado = false` (el primero por `POSITION` — no hay selección
aleatoria, es un límite aceptado del `QueryRows`, no un requisito). Si encuentra uno, lo publica
igual que el de arriba, contra `cosmeticos:buscaminas`:

```json
{ "event": "cosmetic_code", "payload": { "codigo": "PRAX-DEMO-ROMBO", "cosmeticoClave": "mina-diamante" } }
```

No marca el código como usado — el canje real sigue pasando sólo por `Canjear`, que sí lo hace.

### El bloqueo actual: apunta a producción, que todavía no tiene el endpoint

Ambos `HttpRequest` apuntan a `https://gateway.praxsuite.com/...` (producción) porque ahí es
donde vive de verdad el workspace de la demo (`ffd80539-...`) — sus automatizaciones corren en
producción, no en `development`. El endpoint que reciben (`EventBusPublishController`, el mismo
Frente 2 mencionado arriba) sólo llegó a `development` por ahora — el merge a `master` (producción)
es un paso separado, todavía pendiente.

Mientras tanto, **ambos nodos tienen `continueOnError: true`**: la llamada falla con `404`, pero
eso no rompe la respuesta al que llamó a `Validar` ni impide que el leaderboard ya se haya
escrito (eso pasa antes, en pasos previos). Probado explícitamente el 2026-09-09: sin
`continueOnError` un 404 ahí tumbaba la respuesta entera del endpoint aunque el cierre de partida
y el leaderboard ya se hubieran guardado bien — con `continueOnError` la respuesta vuelve limpia
y sólo el intento de publish queda registrado como fallido en el log del run. En cuanto el fix
llegue a producción, ambas ramas empiezan a publicar de verdad sin ningún cambio de código.

**Ojo con `list_node_types` para el nodo `HttpRequest`**: el catálogo devuelve `headers` como
objeto (`{}`) en su `defaultConfig`, pero el backend en runtime sólo acepta un array de
`{key, value}` — usar el formato objeto falla con
`"Invalid HttpRequest node config: ... List\`1[...HttpFormField]"`. Se descubrió probando en vivo,
no está documentado en el catálogo.

---

## Lo que sigue siendo cierto de la implementación original: publicar sin `JoinBus`

`BuscaminasBus.lua` (`ServerScriptService`) sigue existiendo y sigue siendo el mecanismo que usa
`BuscaminasServidor` para sus publicaciones huérfanas (`game.started`/`jugada`, ver arriba). Por
dentro es un POST a `.../api/v1/gateway/{workspaceId}/mcp` con un JSON-RPC `tools/call` →
`publish_bus_event` — un atajo pensado para agentes IA, no para juegos, que sigue funcionando
pero que ya no es la vía recomendada: las dos automatizaciones nuevas usan
`EventBusPublishController` directo (HTTP plano, sin la vuelta del protocolo JSON-RPC de MCP), que
es la ruta pública real para esto. Si algún día se quiere que Roblox mismo publique algo por su
cuenta (no desde una automatización), migrar `Bus.Publish` a `EventBusPublishController` es la
mejora natural — misma firma, sin la capa MCP de por medio.

**Requisito de permiso** (sigue aplicando a `BuscaminasBus.lua`, no a las automatizaciones
nuevas): la API key necesita el scope MCP "Gateway: Write" activado a mano en el portal — no hay
tool para concedérselo por API.
