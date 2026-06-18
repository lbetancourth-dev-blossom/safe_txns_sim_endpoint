# Data Extraction Guide

## Overview

The endpoint receives pre-computed features from a PostgreSQL query run against the OLB production database. The query produces one row per ACH transaction with ~61 features covering transaction basics, user behavior (rolling 6-month windows), recipient history, session signals, and credit union benchmarks.

The query spans a configurable date range (default: Nov 2023 – Sep 2025) and excludes test accounts and internal transaction types.

Full query is also available in [`docs/ENDPOINT_TECHNICAL_REFERENCE.md`](../ENDPOINT_TECHNICAL_REFERENCE.md) Section 4.

---

## Data Collection Query

```sql
WITH params AS (
 SELECT
   TIMESTAMP '2023-11-01 00:00:00' AS start_local,
   TIMESTAMP '2025-09-01 00:00:00' AS end_local
),
time_zone AS (
 SELECT bc.id,
        CASE WHEN bc.config->>'timeZone'='US/Eastern Time' THEN 'US/Eastern'
             ELSE bc.config->>'timeZone' END AS "TimeZone"
 FROM "BlossomCompany" bc
),
fi_bounds AS (
 SELECT fi.id AS "idFi",
        tz."TimeZone" AS tz,
        (((SELECT start_local FROM params) - INTERVAL '6 months') AT TIME ZONE tz."TimeZone") AS lower_utc,
        ((SELECT end_local FROM params) AT TIME ZONE tz."TimeZone") AS upper_utc
 FROM "OLBFinancialInstitution" fi
 JOIN "BlossomCompany" bc ON bc.id = fi."idBlossomCompany"
 JOIN time_zone tz        ON tz.id = bc.id
),
blocked_users AS (
 SELECT username FROM (VALUES
   ('appsuser'),('jonatan'),('luchy'),('albertoglez'),('amy'),('tylerblossom'),
   ('drotz'),('crueda'),('hope'),('bquitian'),('eherrera'),('ohernandez'),
   ('lmanrique'),('jcastiblanco'),('yohannagil'),('dpedraza'),('andresz'),
   ('tapas2000'),('csatizabal'),('jonatanb'),('jrios'),('jjimenez'),('mbernal'),
   ('cramirez23'),('shirley'),('melisapineda'),('dsegovia'),('santiagosilva'),
   ('dtipazoca'),('yulianabuitrago')
 ) t(username)
),
batch_info AS (
 SELECT
   sb."idOLBTraceSubAccountTransaction" AS tx_id,
   MAX(tb."totalAmount")::numeric AS totalAmountBatch,
   MAX((NULLIF(SUBSTRING(tb."transactionName" FROM '^\d+'),''))::int) AS numRecipients
 FROM "OLBTraceSubAccountTransactionBusiness" sb
 JOIN "OLBTraceTransactionBusiness" tb ON tb.id = sb."idOLBTraceTransactionBusiness"
 GROUP BY sb."idOLBTraceSubAccountTransaction"
),
tx_base AS (
 SELECT
   otsat.id AS "TransactionID",
   u.id     AS "idOLBUserTxns",
   bu.username,
   (otsat."createdAt" AT TIME ZONE fb.tz) AS "createdAtTxns",
   otsat.amount::numeric AS amount,
   INITCAP(otsat.type) AS "TransactionProcessingType",
   INITCAP(REPLACE(otsat.origin,'_',' ')) AS "TransactionOrigin",
   INITCAP(REPLACE(otsat.status,'_',' ')) AS "TransactionStatus",
   cat.name AS "TransactionCategory",
   cat."group"::text AS "TransactionGroup",
   u."idFi",
   ottt."idOLBGenericAccountTo" AS "GA_To",
   gat."type" AS "GA_To_Type",
   gat."accountNumber" AS "AccountNumberTo",
   COALESCE(ext_to."bankRoutingNumber", ach_to."ACHRoutingNumber") AS "RoutingNumberTo",
   ottt."idOLBGenericAccountFrom" AS "GA_From",
   gaf."type" AS "GA_From_Type",
   gaf."accountNumber" AS "AccountNumberFrom",
   CASE
     WHEN EXISTS (
       SELECT 1 FROM "OLBTraceSubAccountTransactionBusiness" b
       WHERE b."idOLBTraceSubAccountTransaction" = otsat.id
     ) THEN 'Business'::text ELSE 'Personal'::text
   END AS "TransactionRole"
 FROM "OLBTraceSubAccountTransaction" otsat
 JOIN "OLBTraceTransferTransaction" ottt
   ON ottt."idOLBTraceSubAccountTransaction" = otsat.id
 LEFT JOIN "OLBSubAccountExternal" ext_to
   ON ext_to."idOLBGenericAccount" = ottt."idOLBGenericAccountTo"
 LEFT JOIN "BlossomACHInformation" ach_to
   ON ach_to."idOLBGenericAccount" = ottt."idOLBGenericAccountTo"
 LEFT JOIN "OLBGenericAccount" gat ON gat.id = ottt."idOLBGenericAccountTo"
 LEFT JOIN "OLBGenericAccount" gaf ON gaf.id = ottt."idOLBGenericAccountFrom"
 LEFT JOIN "OLBTraceSubAccountTransactionCategory" cat
   ON cat.id = otsat."idOLBTraceSubAccountTransactionCategory"
 JOIN "OLBUser" u ON u.id = otsat."idOLBUserFrom" AND u."deletedAt" IS NULL
 JOIN "BlossomUser" bu ON bu.id = u."idBlossomUser" AND bu."deletedAt" IS NULL
 JOIN fi_bounds fb ON fb."idFi" = u."idFi"
 WHERE otsat.origin <> 'MICRO_DEPOSIT_SEND'
   AND otsat."createdAt" >= fb.lower_utc
   AND otsat."createdAt" <  fb.upper_utc
)
-- [... rest of CTEs: tx_final, tx_train, fraud_flags, users_in_scope,
--  recipients_raw/keys/map, base, user_roll, user_rec_roll, l1,
--  recipient_hist, first_ts, first_ts_acct, first_flags, loan_accounts,
--  subaccount_accounts, all_accounts, financial_dim, update_info,
--  update_latest, user_roles, users_dim, cu targets chain,
--  session CTEs, tx_all chain, preagg_all, final SELECT]
```

> The complete query (including all CTEs and the final SELECT) is in
> [`docs/ENDPOINT_TECHNICAL_REFERENCE.md`](../ENDPOINT_TECHNICAL_REFERENCE.md) Section 4.

---

## Feature Groups

| Group | Count | Examples |
|---|---|---|
| Transaction basics | ~10 | `amount`, `TransactionProcessingType`, `TransactionOrigin`, `TransactionStatus`, `is_batch` |
| Time features | ~8 | `hour_sin`, `hour_cos`, `day_of_week_sin`, `day_of_week_cos`, `weekend`, `is_night`, `month_sin`, `month_cos` |
| Rolling windows — 5 min | ~4 | `count_all_txn_last_5m`, `total_amount_all_txn_last_5m` |
| Rolling windows — 6 months | ~12 | `user_avg_amount_txn_per_active_day_last_6_months`, `pct_txns_over_1k_lst6m`, `count_user_cancelled_txn_in_last_week` |
| Recipient history | ~6 | `count_txn_to_recipient_account_in_last_2_months`, `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h` |
| Session signals | ~5 | `count_suspected_actions_in_current_session`, session duration, device flags |
| CU benchmarks | ~4 | `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months`, CU-level averages |

---

## Filtering Rules

The query excludes the following rows before producing training/inference data:

| Filter | Reason |
|---|---|
| `amount <= 0.01` | Micro-deposits and zero-amount entries |
| `origin = 'MICRO_DEPOSIT_SEND'` | Not ACH transfers |
| `TransactionProcessingType IN ('Wire', 'M2M', 'Internal')` | Out of scope (not ACH) |
| `origin = 'BATCH_COLLECTION_ACH'` | Inbound collection batches handled separately |
| `username IN (blocked_users)` | Test and internal accounts (see CTE `blocked_users`) |
| User `deletedAt IS NOT NULL` | Soft-deleted users |

---

## Output Columns (61)

The query returns these columns in order. All 61 must be present in the CSV payload sent to the endpoint.

1. `TransactionID`
2. `amount`
3. `createdAtTxns`
4. `TransactionProcessingType`
5. `TransactionOrigin`
6. `TransactionStatus`
7. `TransactionCategory`
8. `TransactionGroup`
9. `idFi`
10. `GA_To_Type`
11. `GA_From_Type`
12. `TransactionRole`
13. `user_type`
14. `recency_user_created_days`
15. `is_batch`
16. `hour_sin`
17. `hour_cos`
18. `day_of_week_sin`
19. `day_of_week_cos`
20. `month_sin`
21. `month_cos`
22. `weekend`
23. `is_night`
24. `count_all_txn_last_5m`
25. `total_amount_all_txn_last_5m`
26. `count_user_cancelled_txn_in_last_week`
27. `count_suspected_actions_in_current_session`
28. `pct_txns_over_1k_lst6m`
29. `user_avg_amount_txn_per_active_day_last_6_months`
30. `user_avg_amount_ach_txn_per_active_day_last_6_months`
31. `count_txn_to_recipient_account_in_last_2_months`
32. `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h`
33. `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months`
34. `cu_avg_amount_ach_txn_in_last_6_months`
35. `count_recipient_accounts_used_last_6_months`
36. `count_unique_recipient_accounts_last_30_days`
37. `total_amount_sent_last_6_months`
38. `avg_txn_amount_last_6_months`
39. `max_txn_amount_last_6_months`
40. `count_txns_last_6_months`
41. `count_txns_last_30_days`
42. `count_txns_last_7_days`
43. `days_since_last_txn`
44. `days_since_first_txn`
45. `count_unique_recipient_routing_numbers_last_6_months`
46. `is_personal_user_phone_primary_updated_last_week`
47. `is_personal_user_email_primary_updated_last_week`
48. `session_duration_seconds`
49. `session_page_count`
50. `session_action_count`
51. `session_suspected_action_count`
52. `device_type`
53. `is_new_device`
54. `login_count_last_7_days`
55. `failed_login_count_last_7_days`
56. `cu_avg_txn_count_per_user_last_6_months`
57. `cu_pct_users_with_txn_over_1k_last_6_months`
58. `cu_median_amount_ach_txn_last_6_months`
59. `cu_stddev_amount_ach_txn_last_6_months`
60. `numRecipients`
61. `totalAmountBatch`

> For full type specifications (float/int/string) see [`docs/references/ENDPOINT_INPUT_FORMAT.md`](../references/ENDPOINT_INPUT_FORMAT.md).
