---
title: Agent Memory
aliases: [AI Agent Context, Agent Onboarding]
tags: [concept, agent, meta, memory]
type: concept
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Agent Memory

Qué archivos lee un agente de IA (Claude, Cursor, Aider, etc.) al entrar a este repo, y en qué orden.

## Capa 1 — Identidad y conventions globales

| Archivo | Cuándo lo lee |
|---|---|
| `~/.claude/projects/.../memory/MEMORY.md` | Cada sesión (auto memory de Claude Code) |
| `CLAUDE.md` (root del repo) | Cada sesión, da contexto del repo |
| `AGENTS.md` (root del repo) | Cada sesión, conventions específicas para agentes |

Estos 3 son creados/refrescados por `/blossom-codemap`.

## Capa 2 — Codemap (vault)

| Página | Para qué |
|---|---|
| `docs/codemap/00-overview/README.md` | MOC, entry point |
| `docs/codemap/00-overview/Architecture.md` | Diagrama del sistema, request flow |
| `docs/codemap/00-overview/Glossary.md` | Términos del dominio |
| `docs/codemap/01-endpoint/README.md` | Módulo crítico (el código del endpoint SageMaker) |
| `docs/codemap/00-overview/Similarity-Athena.md` | Concepto cross-cutting clave |
| `docs/codemap/00-overview/Graceful-Degradation.md` | Invariantes de robustez |

Un agente que llega a tocar `endpoint/similarity_matcher.py` debería leer `[[01-endpoint/README]]` + `[[Similarity-Athena]]` + `[[Graceful-Degradation]]` antes de modificar.

## Capa 3 — Per-module context

Cada módulo tiene su `CLAUDE.md` para agentes trabajando localmente:

- `endpoint/CLAUDE.md`
- `deploy/CLAUDE.md`
- `test/CLAUDE.md`
- `data_eng/CLAUDE.md`

Más compacto que el codemap. Foco en: dónde están las cosas, key files, dependencies, gotchas.

## Capa 4 — Trabajo en flight (SDD artifacts)

Cuando hay un ticket activo:

- `changes/<TICKET>/refinement.md` — pre-análisis del ticket
- `changes/<TICKET>/plan.md` — decisiones cerradas, file manifest
- `changes/<TICKET>/spec.md` — TDD test contracts (lo que ejecuta el implementer)
- `changes/<TICKET>/threats.md` — análisis de seguridad si aplica
- `changes/<TICKET>/preflight.md` — adversarial spec review

Estos son **transientes** (se archivan al cerrar el ticket). El codemap es **permanente**.

## Capa 5 — Legacy docs (existentes, no autogenerados)

Documentación temática que existía antes del codemap:

| Archivo | Cubre |
|---|---|
| `docs/ENDPOINT_FLOW_SEQUENCE.md` | Flujo detallado de inference |
| `docs/ENDPOINT_PROCESSING.md` | Cómo el endpoint procesa requests |
| `docs/SIMILARITY_INTEGRATION.md` | Integración del similarity matcher |
| `docs/SIMILARITY_USAGE.md` | Cómo usar similarity |
| `docs/SIMILARITY_NULL_VALUES.md` | Comportamiento en nulls |
| `docs/SIMILARITY_FORMAT.md` | Formato de la respuesta de similarity |
| `docs/GRACEFUL_DEGRADATION.md` | Detalle de la degradación graceful |
| `docs/PARQUET_MIGRATION.md` | Histórico de migración a Parquet |
| `docs/SILVER_LAYER_MIGRATION.md` | Migración a Silver |
| `docs/ATHENA_INTEGRATION.md` | Integración Athena (creado en DATA-1264 T6) |
| `docs/RISK_DECISION_BEHAVIOR.md` | Cómo se decide risk_decision |
| `docs/DATA_PREPARATION.md` | Cómo preparar datos para el modelo |
| `docs/DEPLOYMENT_SUMMARY.md` | Resumen del deploy |
| `docs/DYNAMIC_RELOAD.md` | Recarga dinámica de reference data |
| `docs/SCHEMA_VALIDATOR.md` | Validación de schema |
| `docs/ENDPOINT_INPUT_FORMAT.md` | Las 61 columnas del payload (creado en DATA-1264) |
| `docs/TEST_SCENARIOS.md` | 9 escenarios de prueba (creado en DATA-1264) |

El codemap (este vault) es **la fuente de verdad de arquitectura**. Los docs legacy siguen siendo útiles para detalles tácticos — son una capa de referencia complementaria, no contradictoria. Si hay conflicto entre uno y otro, gana el codemap (es más reciente y se actualiza con `--update`).

## Orden recomendado de lectura para un agente nuevo

1. `CLAUDE.md` (root) — qué es el repo
2. `AGENTS.md` (root) — reglas para no romper nada
3. `docs/codemap/00-overview/README.md` — MOC
4. `docs/codemap/00-overview/Architecture.md` — sistema
5. Si va a tocar un módulo específico → su page en el codemap + `CLAUDE.md` del módulo
6. Si hay un ticket activo → `changes/<TICKET>/spec.md` (lo que hay que hacer)
7. Si la tarea es heavy → `docs/codemap/00-overview/Glossary.md` antes de leer código

## See also

- [[SDD-Workflow]] — el proceso que produce los artefactos transient
- [[Architecture]] — la arquitectura que documentan estos archivos

## Backlinks

- [[Index]]
- [[README]]
- [[SDD-Workflow]]

#agent #meta #memory #onboarding
