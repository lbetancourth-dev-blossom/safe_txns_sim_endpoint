---
title: Module Map
aliases: [Directory Map, Module Directory]
tags: [overview, module-map]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Module Map

Mapeo directorio → módulo. Si tocás un archivo bajo cualquiera de estos paths, mirá primero el `README.md` del módulo correspondiente.

| Directorio | Módulo | Doc |
|---|---|---|
| `endpoint/` | Endpoint (código del contenedor SageMaker) | [[01-endpoint/README]] |
| `deploy/` | Deploy scripts | [[02-deploy/README]] |
| `test/` | Tests de integración + scripts manuales | [[03-test/README]] |
| `data_eng/` | Pipeline Bronze→Silver | [[04-data-eng/README]] |

## Directorios sin módulo (datos o trabajo en flight)

| Directorio | Propósito |
|---|---|
| `changes/` | Artefactos SDD por ticket (plan.md, spec.md, threats.md, preflight.md, refinement.md, testing-report.md) — ver [[SDD-Workflow]] |
| `changes/archive/` | Tickets completados, archivados al cerrar (ver `/blossom-workflow:done`) |
| `data/` | CSVs de referencia y test (no es código — datos de prueba y casos) |
| `data_eng/` | También funciona como módulo (ver [[04-data-eng/README]]) |
| `docs/` | Documentación. Subfolder `docs/codemap/` (este vault) + docs temáticas (`ENDPOINT_FLOW_SEQUENCE.md`, `SIMILARITY_INTEGRATION.md`, etc.) |
| `.worktrees/` | Git worktrees para tickets activos (gitignored) |
| `temp_artifacts/` | Modelo + artefactos descargados temporalmente durante deploy (gitignored) |

## Archivos fuera de módulos

| Archivo | Propósito |
|---|---|
| `CLAUDE.md` | Root context para agentes IA (autogenerado por `/blossom-codemap`) |
| `AGENTS.md` | Brief para agentes de coding (autogenerado por `/blossom-codemap`) |
| `README.md` | Front door del repo |
| `README_NEW.md` | (TBD — revisar si es duplicado de README.md) |
| `setup_sagemaker.sh` | Script de provisión inicial de la instancia SageMaker |
| `safe-txn-enpoint.ipynb`, `safe-txn-enpoint-test.ipynb` | Notebooks de desarrollo (entrenamiento + pruebas exploratorias) |

## Backlinks

- [[Index]]
- [[README]]

#module-map #directory
