# Praxsuite AppSource — Roblox Game

Experiencia de demostración en Roblox que usa **Praxsuite** como backend completo: cuentas de
jugador, partidas, puntajes, tienda de cosméticos y ranking. No hay ningún otro servidor de por
medio — todo lo que persiste vive en un workspace de Praxsuite y se consume desde Roblox con el
**SDK de Lua**.

Este repositorio contiene el place de Roblox Studio listo para abrir:

```text
RobloxSDKDemo.rbxl
```

---

## Enlaces

| Recurso | Enlace |
| --- | --- |
| Implementación del SDK genérico (Lua) | <!-- TODO: URL del repo/paquete del SDK de Lua --> `PENDIENTE` |
| Guía de implementación del SDK genérico | <!-- TODO: URL del doc "Lua SDK Implementation" --> `PENDIENTE` |
| Ejemplo actual de Roblox (caso de uso) | <!-- TODO: URL del doc "Praxsuite Integration with Roblox" --> `PENDIENTE` |
| Documentación de Praxsuite | <!-- TODO: URL de docs --> `PENDIENTE` |
| Workspace de Praxsuite de la demo | <!-- TODO: URL del workspace --> `PENDIENTE` |

> Los enlaces de arriba son marcadores. Reemplaza `PENDIENTE` por la URL definitiva cuando el SDK
> y los documentos estén publicados.

---

## Qué hace la experiencia

Es un **Buscaminas multijugador** construido enteramente sobre Praxsuite.

- **Cuenta propia, no la de Roblox.** El jugador se registra e inicia sesión dentro del juego
  (`Registrar` / `Login`). La identidad vive en Praxsuite, así que el progreso es del jugador y no
  del place: la misma cuenta sirve para cualquier otro cliente que hable con el mismo workspace.
- **El tablero es geometría real.** No es una interfaz: es una grilla de partes en el `Workspace`,
  con un `ClickDetector` por celda. Clic izquierdo revela, clic derecho pone o saca bandera. Al ser
  geometría del servidor, el cliente no puede inventar una jugada — solo puede tocar una celda que
  realmente existe.
- **La lógica corre en el servidor.** La matriz de minas, el *flood fill* de celdas vacías, el
  cálculo de puntaje y el guardado son responsabilidad del script de servidor. El cliente se ocupa
  del acceso, el HUD y el marcador, nada más.
- **Ranking persistente.** Los puntajes de todas las partidas se acumulan en Praxsuite y el
  leaderboard se lee de ahí, así que sobrevive a cerrar el juego y se comparte entre sesiones.
- **Tienda de cosméticos.** Con los puntos ganados se canjean accesorios (`Canjear`), se listan los
  propios (`MisCosmeticos`) y se equipan sobre el avatar (`Equipar`).

---

## Arquitectura

```text
Cliente (LocalScript)          Servidor (Script)              Praxsuite
─────────────────────          ─────────────────              ─────────
BuscaminasCliente              BuscaminasServidor             Endpoints
  · pantalla de acceso   ──▶     · sesión y rate limit   ──▶    · Registrar / Login
  · HUD y marcador       RemoteFunction/Event                   · NuevaPartida / Jugar
  · clic sobre celdas            · matriz de minas              · Leaderboard
                                 · flood fill                   · Canjear / MisCosmeticos
                                 · puntaje y persistencia       · Equipar
```

**Regla de oro:** el único lado que habla con Praxsuite es el servidor. La API Key nunca baja al
cliente, y cada jugada se valida antes de escribirse. El cliente no tiene forma de pedir una jugada
falsa porque no existe un remote que la acepte sin pasar por el servidor.

### Contenido del place

| Ubicación | Instancia | Rol |
| --- | --- | --- |
| `ServerScriptService` | `PraxsuiteSDK` | El SDK de Lua (`Config`, `Http`, `PraxQL`, `Data`, `Endpoints`, `Players`, `Schema`, `Auth`) |
| `ServerScriptService` | `BuscaminasServidor` | Toda la lógica de juego y la única llamada a Praxsuite |
| `ServerScriptService` | `Tablero`, `Estilo`, `Accesorio` | Módulos de apoyo: construcción de la grilla, tema visual, cosméticos |
| `ReplicatedStorage` | `BuscaminasRemotes` | `Registrar`, `Login`, `NuevaPartida`, `Jugar`, `Leaderboard`, `Canjear`, `MisCosmeticos`, `Equipar` |
| `StarterPlayerScripts` | `BuscaminasCliente` | Acceso, HUD y marcador |

Cada remote del cliente tiene su endpoint espejo en Praxsuite. Los endpoints son automatizaciones
en modo *Sync*: el servidor las llama y recibe la respuesta en la misma llamada.

---

## Cómo ejecutarlo

1. Abre `RobloxSDKDemo.rbxl` en Roblox Studio.
2. Habilita el acceso HTTP: **Game Settings → Security → Allow HTTP Requests**.
3. Carga tu API Key en **Game Settings → Security → Secrets Store** con el nombre `PraxsuiteKey`.
   Para pruebas locales rápidas se puede pasar la clave directamente en `Init`, pero nunca así en
   producción.
4. En `BuscaminasServidor`, ajusta el `workspaceId` y los UUID de endpoints a los de tu workspace.
5. Presiona **Play**. La primera vez verás la pantalla de registro; después de eso, login.

> **Nunca** llames al SDK desde un `LocalScript`. Cualquier cosa que un cliente pueda leer, un
> jugador la puede extraer.

---

## Configuración

El servidor inicializa el SDK una sola vez:

```lua
local Praxsuite = require(game:GetService("ServerScriptService").PraxsuiteSDK)

Praxsuite.Init({
    workspaceId     = "<!-- TODO: UUID del workspace -->",
    apiKeySecret    = "PraxsuiteKey",  -- nombre en el Secrets Store de Roblox
    autoFetchSchema = false,           -- endpoints y tablas se registran a mano
})
```

Los UUID de los ocho endpoints están declarados como constantes al principio del script, junto al
`workspaceId`. Al clonar el workspace de la demo hay que reemplazarlos por los del workspace nuevo.

---

## Licencia

Consulta el repositorio del SDK de Lua para los términos de la licencia Praxsuite Open SDK.
