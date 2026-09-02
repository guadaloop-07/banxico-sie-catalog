# Prueba Linux de la prerelease

Esta guía prueba el servidor MCP local con el snapshot validado `v0.1.0`.
No requiere una cuenta de Banxico ni `BMX_TOKEN`.

## Requisitos

- Linux con Python 3.11 o 3.12 (`python3 --version`).
- Una terminal Bash y acceso a GitHub.
- Codex sólo es necesario para la sección opcional de conexión MCP.

Instala `pipx` con el gestor de paquetes de tu distribución. Si ya tienes `pipx`,
omite este paso. Por ejemplo, en Debian/Ubuntu:

```bash
sudo apt install pipx
pipx ensurepath
```

Abre una nueva terminal después de `ensurepath`.

## Instalar y probar el catálogo

Instala el wheel adjunto a la prerelease que estás evaluando:

```bash
pipx install https://github.com/guadaloop-07/banxico-sie-catalog/releases/download/v0.1.1-rc.1/banxico_sie_catalog-0.1.1rc1-py3-none-any.whl
mkdir -p "$HOME/banxico-sie-mcp"
banxico-sie-catalog install-catalog v0.1.0 --output-dir "$HOME/banxico-sie-mcp/snapshot"
banxico-sie-catalog search "tipo de cambio" --database "$HOME/banxico-sie-mcp/snapshot/catalog.sqlite" --limit 3
```

La instalación imprime un JSON con checksum, número de sectores y número de
registros. La búsqueda debe devolver hasta tres series; conserva cualquier error
completo para reportarlo.

## Conexión opcional a Codex

```bash
codex mcp add banxico_sie_catalog -- \
  "$(command -v banxico-sie-catalog-mcp)" \
  --database "$HOME/banxico-sie-mcp/snapshot/catalog.sqlite"
```

Reinicia Codex, abre `/mcp` y prueba: “Usa `search_series` para encontrar tres
series sobre tipo de cambio”.

## Feedback solicitado

Comparte tu distribución Linux, versión de Python, si cada paso funcionó, las
preguntas realizadas y la salida completa de cualquier error. No compartas un
`BMX_TOKEN`.
