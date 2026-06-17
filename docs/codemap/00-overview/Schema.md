---
title: Codemap Schema
aliases: [Conventions, Rules, How the Codemap Works]
tags: [overview, schema, meta]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Codemap Schema

Convenciones que sigue `docs/codemap/`. Leelo antes de editar una página a mano.

## Tres capas

1. **Raw sources** — el código de este repo. Inmutable para el codemap. El codemap lee, nunca modifica.
2. **El vault** — `docs/codemap/`. Propiedad del LLM. Creado y mantenido por `/blossom-codemap`. Podés editar a mano si marcás las ediciones (ver "User edits" abajo).
3. **El schema** — este archivo. Convención humano-LLM. Cuando se decide una nueva regla, va acá.

## Folder layout

```
docs/codemap/
├── log.md                            (append-only history)
├── 00-overview/
│   ├── README.md                     (master MOC)
│   ├── Index.md                      (catálogo alfabético)
│   ├── Schema.md                     (este archivo)
│   ├── Architecture.md
│   ├── Tech-Stack.md
│   ├── Module-Map.md
│   ├── Glossary.md
│   ├── Similarity-Athena.md          (concepto cross-cutting)
│   ├── K-Means-Pipeline.md
│   ├── Statistical-Rules.md
│   ├── Graceful-Degradation.md
│   ├── SDD-Workflow.md               (Blossom-specific)
│   └── Agent-Memory.md               (Blossom-specific)
├── 01-endpoint/
│   ├── README.md
│   └── Public-API.md
├── 02-deploy/
│   └── README.md
├── 03-test/
│   └── README.md
└── 04-data-eng/
    └── README.md
```

## Frontmatter rules

Cada página DEBE tener YAML frontmatter:

| Key | Requerido | Propósito |
|---|---|---|
| `title` | sí | Nombre human-readable |
| `aliases` | sí (puede ser vacío) | Alt names para búsqueda |
| `tags` | sí | Kebab-case, sin espacios |
| `type` | sí | Uno de: `overview`, `module`, `concept`, `api`, `guide` |
| `last_mapped_at` | sí | ISO 8601 |
| `last_commit` | sí | Git short SHA |

## Wiki-link rules

- `[[Page-Name]]` para hermanas, `[[01-endpoint/Public-API]]` para cross-folder.
- Case-sensitive. Slug = nombre del archivo sin `.md`.
- Si una página menciona otro módulo/concepto, DEBE linkear.
- Bidireccional: si A linkea B, el `## Backlinks` de B lista A. El lint pass lo enforza.

## Tag rules

- Tags inline `#kebab-case` en el body, además de los frontmatter tags.
- Un tag por concepto. No tagear de relleno.

## User edits

Si editás una página a mano, marcá la sección autogenerada para que el próximo `--update` la preserve:

```
<!-- codemap:auto-generated:start -->
(lo que está acá se reemplaza en update)
<!-- codemap:auto-generated:end -->

## Mis notas
(esto queda intacto en update)
```

## Mermaid

- `Architecture.md` DEBE tener diagrama de sistema.
- Module READMEs deberían tener sequence o component diagram si son no-triviales.

## Tres operaciones

| Modo | Trigger | Qué hace |
|---|---|---|
| fresh | No existe `docs/codemap/` | Mapea desde cero |
| update | `--update` o auto-detect | Re-explora solo módulos cuyos archivos cambiaron desde `last_mapped_at` |
| lint | `--lint` | Health check: broken links, orphans, frontmatter stale, missing pages |

## Backlinks

- [[Index]]

#schema #meta
