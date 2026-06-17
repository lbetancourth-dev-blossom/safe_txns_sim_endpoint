---
title: Codemap Overview
aliases: [MOC, Map of Content, Index]
tags: [overview, moc]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# safe_txns_sim_endpoint — Codemap

> SageMaker ML endpoint para scoring de riesgo de transacciones financieras en credit unions. Combina K-Means clustering + reglas estadísticas + similarity matching contra historial Athena (ventana sliding 6 meses) para clasificar cada transacción como Accept / User Auth / Admin Review / Reject.

## Modules

| # | Module | Path | Purpose |
|---|---|---|---|
| 01 | [[01-endpoint/README\|Endpoint]] | `endpoint/` | Código que vive en el contenedor SageMaker. K-means + reglas + similitud. |
| 02 | [[02-deploy/README\|Deploy]] | `deploy/` | Scripts de empaquetado y despliegue del endpoint vía SageMaker SDK. |
| 03 | [[03-test/README\|Test]] | `test/` | Tests de integración (pytest) + scripts manuales para invocar el endpoint real. |
| 04 | [[04-data-eng/README\|Data Engineering]] | `data_eng/` | Pipeline Bronze→Silver. Extrae transacciones del datalake y produce Parquet/CSV. |

## Cross-cutting concepts

- [[Architecture]] — diagrama del sistema completo, request flow, deployment topology
- [[Tech-Stack]] — dependencias y versiones (pyathena, sklearn, sagemaker SDK, boto3)
- [[Module-Map]] — directorio → módulo (un solo lugar)
- [[Glossary]] — términos del dominio (idOLBUserTxns, SAFE/RISKY, sliding window, sim_score, etc.)
- [[Similarity-Athena]] — cómo el endpoint consulta Athena en cada inferencia con ventana sliding 6m
- [[K-Means-Pipeline]] — preprocesamiento, clustering, distancia al centroide
- [[Statistical-Rules]] — reglas v8 que escoran señales de riesgo (R1–R12)
- [[Graceful-Degradation]] — qué pasa cuando Athena falla o falta `idOLBUserTxns`/`createdAtTxns`
- [[SDD-Workflow]] — cómo se hacen los cambios en este repo (Blossom SDD+TDD cycle)
- [[Agent-Memory]] — convención para que un agente de IA entienda este repo

## How to use this codemap

- **¿Querés saber qué hace un módulo?** Empezá en la tabla de arriba.
- **¿Querés entender la arquitectura?** Leé [[Architecture]].
- **¿Cambio en flight (DATA-XXXX)?** Mirá `changes/<TICKET>/` para el plan + spec + threats + preflight.
- **Sos un agente de IA trabajando dentro de un módulo?** Leé el `CLAUDE.md` del módulo (`endpoint/CLAUDE.md`, `deploy/CLAUDE.md`, etc.).
- **Agregaste un módulo nuevo o refactorizaste?** Re-corré `/blossom-codemap --update` para actualizar.

## How features ship in this repo

Este repo sigue el ciclo SDD+TDD de Blossom — ver [[SDD-Workflow]] para el detalle. En corto: cada feature pasa por refine → plan → security → preflight → execute (TDD) → scan → review → pr → done, con artefactos persistentes en `changes/<TICKET>/`. La memoria del agente vive en [[Agent-Memory]].

## Backlinks

_None yet — este es el entry point del vault._

#overview #moc #safe-transactions #ml-endpoint
