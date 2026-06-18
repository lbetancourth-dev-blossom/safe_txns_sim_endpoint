---
title: Codemap Index
aliases: [Catalog, Page List, Vault Index]
tags: [overview, index]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Codemap Index

Catálogo alfabético de todas las páginas del vault. Para el entry point narrativo, ver [[README]].

## Overview pages

| Page | One-liner |
|---|---|
| [[Architecture]] | Diagrama del sistema, request flow, deployment topology |
| [[Glossary]] | Términos del dominio (idOLBUserTxns, SAFE/RISKY, sim_score, etc.) |
| [[Graceful-Degradation]] | Contrato D1: procesos paralelos independientes |
| [[Index]] | Esta página |
| [[K-Means-Pipeline]] | Baseline obligatorio del endpoint |
| [[Module-Map]] | Directorio → módulo |
| [[README]] | MOC del codemap (entry point) |
| [[SDD-Workflow]] | Ciclo SDD+TDD de Blossom |
| [[Similarity-Athena]] | Cómo el endpoint consulta Athena con ventana sliding 6m |
| [[Statistical-Rules]] | Reglas v8 R1–R12 con scoring piecewise |
| [[Tech-Stack]] | Dependencias y versiones (pyathena, sklearn, etc.) |

## Modules

| Page | One-liner |
|---|---|
| [[01-endpoint/README\|Endpoint]] | Código del contenedor SageMaker (K-means + reglas + similitud) |
| [[01-endpoint/Public-API\|Endpoint · Public API]] | model_fn, predict_fn, output schema |
| [[02-deploy/README\|Deploy]] | Scripts SageMaker SDK para empaquetar y desplegar |
| [[03-test/README\|Test]] | Tests pytest + scripts manuales (process_endpoint.py) |
| [[04-data-eng/README\|Data Engineering]] | Pipeline ETL Bronze→Silver (offline) |

## File counts

- Overview pages: 11
- Module pages: 5
- **Total codemap pages:** 16
- **Per-module CLAUDE.md:** 4 (endpoint, deploy, test, data_eng)
- **Root meta files:** 2 (CLAUDE.md, AGENTS.md)
- **Grand total:** 22 archivos generados por `/blossom-codemap`

## Legacy docs (no codemap, en `docs/` raíz)

Documentación temática preexistente que sigue siendo útil para detalles tácticos. Lista en [[Agent-Memory]] sección "Capa 5".

#index #catalog
