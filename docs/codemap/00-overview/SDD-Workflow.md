---
title: SDD Workflow
aliases: [Spec Driven Development, Blossom Workflow, SDD+TDD]
tags: [concept, sdd, blossom, workflow, meta]
type: concept
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# SDD Workflow

Este repo sigue el ciclo **Spec-Driven Development + Test-Driven Development** del plugin `blossom-workflow`. Cada feature pasa por un pipeline determinista de fases, cada una con su artefacto persistente en `changes/<TICKET>/`.

## Pipeline

```mermaid
flowchart LR
    refine[/refine/]
    feature[/feature/]
    plan[/plan/]
    security[/security/]
    preflight[/preflight/]
    execute[/execute/]
    scan[/scan/]
    review[/review/]
    pr[/pr/]
    done[/done/]

    refine --> feature --> plan --> security --> preflight --> execute --> scan --> review --> pr --> done
```

| Fase | Comando | Artefacto principal | Quién lo produce |
|---|---|---|---|
| Refine | `/refine TICKET` | `refinement.md` | `blossom-refiner` subagent |
| Feature setup | `/feature TICKET` | (worktree + Draft PR) | scripts en `blossom-workflow` |
| Plan | `/plan TICKET` | `plan.md` (DCR + HLTC), `spec.md` | `blossom-planner` subagent |
| Security | `/security TICKET` (auto en `/plan`) | `threats.md` | `blossom-security` subagent |
| Preflight | (auto en `/plan`) | `preflight.md` | `blossom-reviewer` (preflight mode) |
| Execute | `/execute TICKET` | `testing-report.md`, commits TDD | `blossom-implementer` subagent |
| Scan | `/scan TICKET` | (en línea, output) | `blossom-reviewer` |
| Review | `/review TICKET` | `review-report.md` | `blossom-reviewer` (compliance) |
| PR | `/pr TICKET` | (GitHub PR) | scripts |
| Done | `/done TICKET` | (archivado a `changes/archive/`) | scripts |

Cada comando es **idempotente** y **resumable** — si una sesión se corta, `/blossom-workflow:next TICKET` reporta dónde estás.

## Artefactos en `changes/<TICKET>/`

| Archivo | Generado por | Propósito |
|---|---|---|
| `refinement.md` | refine | Audit trail del análisis pre-SDD, mirror del comment Jira |
| `plan.md` | plan | DCR + HLTC, decisiones cerradas, file manifest, risk matrix, approval stamp |
| `spec.md` | plan | TDD test contracts task-by-task (input para implementer) |
| `threats.md` | security | 10 categorías de threat analysis fintech, gate approval para High/Critical |
| `preflight.md` | preflight (auto) | Adversarial review del spec; bloquea CRITICAL findings |
| `testing-report.md` | execute | V-steps pass/fail por task |
| `review-report.md` | review | Compliance final spec ↔ código |
| `proposal-update.md` | execute halt | Si el spec era insuficiente, el implementer lo escribe y se vuelve a `/plan` |
| `.session-state.json` | varios | Resume state (gitignored) |
| `.execute-progress.log` | execute | Stream en tiempo real (gitignored) |

## Decision Closure Rule

En la fase `/plan`, las **decisiones humanas** (DCR) están capadas a **10 como máximo**, target 3–5. El planner auto-cierra todo lo que pueda groundear en código. El dev solo decide lo que requiere juicio humano.

Cada decisión se marca como `closed_by: <nombre>` con fecha. Ver [[changes/DATA-1264/plan.md]] como ejemplo (5 decisiones humanas D1–D5).

## Cómo identificar la fase actual

Si te perdés, corré:

```
/blossom-workflow:next [TICKET]
```

Te dice qué fase está activa y cuál es el próximo paso concreto.

## Cómo se mapea sobre este repo

- El worktree `feat/<TICKET>` vive en `.worktrees/<TICKET>/` (gitignored)
- Branch parent: `development` (decidido en DATA-1264 — el repo originalmente tenía `dev`/`main`, se migró)
- Default branch GitHub: `main` (producción)
- PRs van: `feat/<TICKET>` → `development` → `main` (este último paso aún no tiene comando dedicado en este repo)

## Cómo se compone con el codemap

- El codemap es la **memoria compartida de arquitectura** del repo (este vault).
- Las fases SDD lo **leen** (especialmente `blossom-planner` durante `/plan`) para entender el contexto sin tener que re-explorar.
- Los planes producen `changes/<TICKET>/` que documentan **trabajo en flight**.
- Cuando un ticket cierra con `/done`, los aprendizajes que afecten arquitectura deberían reflejarse en el codemap vía `/blossom-codemap --update`.

## See also

- [[Agent-Memory]] — qué archivos lee el agente IA al entrar al repo
- [[Architecture]] — la arquitectura del sistema (lo que el SDD opera)
- Plugin source: `~/.claude/plugins/cache/blossom-plugins/blossom-workflow/`

## Backlinks

- [[Agent-Memory]]
- [[Glossary]]
- [[Index]]
- [[Module-Map]]
- [[README]]

#sdd #blossom #workflow #meta
