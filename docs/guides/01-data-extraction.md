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
tx_final AS (
 SELECT
   b.*,
   (CASE WHEN b."TransactionCategory" IN ('SEND_MONEY_PAYROLL_ACH','SEND_MONEY_BATCH_PAYMENT_ACH') THEN 1 ELSE 0 END)::int AS is_batch,
   CASE WHEN b."TransactionCategory" IN ('SEND_MONEY_PAYROLL_ACH','SEND_MONEY_BATCH_PAYMENT_ACH')
        THEN bi.totalAmountBatch ELSE NULL END AS total_amount_batch,
   CASE WHEN b."TransactionCategory" IN ('SEND_MONEY_PAYROLL_ACH','SEND_MONEY_BATCH_PAYMENT_ACH')
        THEN bi.numRecipients ELSE NULL END AS num_recipients_batch,
   CASE
     WHEN b."AccountNumberTo" IS NOT NULL AND COALESCE(b."RoutingNumberTo",'') <> ''
       THEN concat_ws('-', b."AccountNumberTo"::text, b."RoutingNumberTo")
     WHEN b."GA_To_Type" IN ('EXTERNAL','EXTERNAL_CONTACT','EXTERNAL_CONTACT_TEMP','ACH_INFORMATION')
          AND b."GA_To" IS NOT NULL
       THEN b."GA_To"::text
     WHEN b."AccountNumberTo" IS NOT NULL
       THEN b."AccountNumberTo"::text
     ELSE COALESCE(b."GA_To"::text, b."AccountNumberTo"::text)
   END AS recipient_key
 FROM tx_base b
 LEFT JOIN batch_info bi ON bi.tx_id = b."TransactionID"
),
tx_train AS (
 SELECT f.*
 FROM tx_final f
 WHERE NOT EXISTS (SELECT 1 FROM blocked_users bu WHERE bu.username = f.username)
   AND f.amount > 0.01::numeric
   AND COALESCE(f."TransactionGroup",'') NOT IN ('WIRE','M2M','INTERNAL')
   AND COALESCE(f."TransactionCategory",'') NOT IN ('BATCH_COLLECTION_ACH','BATCH_COLLECTION_ACH_SWEEP')
   AND f."createdAtTxns" >= (SELECT start_local FROM params)
   AND f."createdAtTxns" <  (SELECT end_local   FROM params)
),
fraud_flags AS (
 SELECT otc."idOLBTraceSubAccountTransaction" AS txn_id,
        MAX((otc.description ILIKE '%fraud%')::int)::int AS is_potential_fraud
 FROM "OLBTransferCancelation" otc
 GROUP BY otc."idOLBTraceSubAccountTransaction"
),
users_in_scope AS (
 SELECT DISTINCT "idOLBUserTxns" AS id FROM tx_train
),
recipients_raw AS (
 SELECT
   u.id AS "idOLBUser",
   br."createdAt"::date AS "createdAtRecipient",
   bm2m."idOLBGenericAccount"::text AS key_bm2m_ga,
   ach."idOLBGenericAccount"::text   AS key_ach_ga,
   oga_bm2m."accountNumber"::text    AS key_bm2m_acct,
   oga_ach."accountNumber"::text     AS key_ach_acct,
   concat_ws('-', oga_ach."accountNumber"::text, ach."ACHRoutingNumber") AS key_ach_acct_rn
 FROM "BlossomRecipient" br
 JOIN "BlossomUserRecipient" bur ON bur."idBlossomRecipient"=br.id AND bur."deletedAt" IS NULL
 JOIN "OLBUser" u ON u."idBlossomUser"=bur."idBlossomUser" AND u."deletedAt" IS NULL
 JOIN users_in_scope s ON s.id = u.id
 LEFT JOIN "BlossomMemberToMemberInformation" bm2m ON bm2m."idBlossomRecipient"=br.id
 LEFT JOIN "OLBGenericAccount" oga_bm2m ON oga_bm2m.id=bm2m."idOLBGenericAccount"
 LEFT JOIN "BlossomACHInformation" ach ON ach."idBlossomRecipient"=br.id
 LEFT JOIN "OLBGenericAccount" oga_ach ON oga_ach.id=ach."idOLBGenericAccount"
 WHERE br."createdAt"::date <= (SELECT end_local::date FROM params)
),
recipients_keys AS (
 SELECT r."idOLBUser", v.recipient_key, r."createdAtRecipient"
 FROM recipients_raw r
 CROSS JOIN LATERAL (VALUES
   (r.key_bm2m_ga),(r.key_ach_ga),(r.key_bm2m_acct),(r.key_ach_acct),(r.key_ach_acct_rn)
 ) AS v(recipient_key)
 WHERE v.recipient_key IS NOT NULL
),
recipients_map AS (
 SELECT "idOLBUser", recipient_key, MIN("createdAtRecipient") AS "createdAtRecipient"
 FROM recipients_keys
 GROUP BY 1,2
),
base AS (
 SELECT
   t.*,
   EXTRACT(HOUR FROM t."createdAtTxns")::int AS hh,
   EXTRACT(DOW  FROM t."createdAtTxns")::int AS dow,
   DATE(t."createdAtTxns") AS day_key,
   COALESCE(ff.is_potential_fraud,0)::int AS is_potential_fraud,
   rm."createdAtRecipient"
 FROM tx_train t
 LEFT JOIN fraud_flags ff ON ff.txn_id = t."TransactionID"
 LEFT JOIN recipients_map rm
   ON rm."idOLBUser"   = t."idOLBUserTxns"
  AND rm.recipient_key = t.recipient_key
),
user_roll AS (
 SELECT
   b."TransactionID",
   COUNT(*) OVER (PARTITION BY b."idOLBUserTxns" ORDER BY b."createdAtTxns"
                  RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND INTERVAL '1 microsecond' PRECEDING) AS count_all_txn_last_5m,
   SUM(b.amount) OVER (PARTITION BY b."idOLBUserTxns" ORDER BY b."createdAtTxns"
                       RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND INTERVAL '1 microsecond' PRECEDING) AS total_amount_all_txn_last_5m
 FROM base b
),
user_rec_roll AS (
 SELECT
   b."TransactionID",
   COUNT(*) OVER (PARTITION BY b."idOLBUserTxns", b.recipient_key ORDER BY b."createdAtTxns"
                  RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND INTERVAL '1 microsecond' PRECEDING) AS count_txn_to_recipient_account_last_5m,
   SUM(b.amount) OVER (PARTITION BY b."idOLBUserTxns", b.recipient_key ORDER BY b."createdAtTxns"
                       RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND INTERVAL '1 microsecond' PRECEDING) AS total_amount_txn_to_recipient_account_last_5m
 FROM base b
),
l1 AS (
 SELECT
   p.*,
   CASE WHEN p.hh < 6 OR p.hh > 22 THEN 1 ELSE 0 END AS is_night,
   SIN(2*PI()*p.hh/24.0) AS hour_sin,
   COS(2*PI()*p.hh/24.0) AS hour_cos,
   CASE WHEN p.dow IN (0,6) THEN 1 ELSE 0 END AS weekend,
   SUM(CASE WHEN p."TransactionStatus" ILIKE '%cancel%' THEN 1 ELSE 0 END) OVER w7d  AS count_cancelled_txn_lst1w,
   SUM(CASE WHEN p."TransactionStatus" ILIKE '%cancel%' THEN 1 ELSE 0 END) OVER w30d AS count_cancelled_txn_lst1m,
   SUM(p.is_potential_fraud) OVER w60d AS count_potentialfraud_txn_lst2m,
   COUNT(*) OVER w6m AS total_count_6m,
   SUM(p.amount) OVER w6m AS sum_amt_6m,
   STDDEV_POP(p.amount) OVER w6m AS std_amt_6m,
   (AVG(CASE WHEN p.amount < 100  THEN 1 ELSE 0 END) OVER w6m)::double precision AS pct_txns_under_100_lst6m,
   (AVG(CASE WHEN p.amount > 1000 THEN 1 ELSE 0 END) OVER w6m)::double precision AS pct_txns_over_1k_lst6m,
   SIN(2*PI()*(((EXTRACT(DOW FROM p."createdAtTxns")::int + 6) % 7)/7.0)) AS day_of_week_sin,
   COS(2*PI()*(((EXTRACT(DOW FROM p."createdAtTxns")::int + 6) % 7)/7.0)) AS day_of_week_cos,
   SIN(2*PI()*((EXTRACT(MONTH FROM p."createdAtTxns")::int - 1)/12.0)) AS month_sin,
   COS(2*PI()*((EXTRACT(MONTH FROM p."createdAtTxns")::int - 1)/12.0)) AS month_cos,
   COUNT(*) OVER r7d  AS count_txn_to_recipient_lst1w,
   COUNT(*) OVER r60d AS count_txn_to_recipient_lst2m
 FROM base p
 WINDOW
   w6m  AS (PARTITION BY p."idOLBUserTxns" ORDER BY p."createdAtTxns" RANGE BETWEEN INTERVAL '6 months'  PRECEDING AND INTERVAL '1 microsecond' PRECEDING),
   w7d  AS (PARTITION BY p."idOLBUserTxns" ORDER BY p."createdAtTxns" RANGE BETWEEN INTERVAL '7 days'    PRECEDING AND INTERVAL '1 microsecond' PRECEDING),
   w30d AS (PARTITION BY p."idOLBUserTxns" ORDER BY p."createdAtTxns" RANGE BETWEEN INTERVAL '30 days'   PRECEDING AND INTERVAL '1 microsecond' PRECEDING),
   w60d AS (PARTITION BY p."idOLBUserTxns" ORDER BY p."createdAtTxns" RANGE BETWEEN INTERVAL '60 days'   PRECEDING AND INTERVAL '1 microsecond' PRECEDING),
   r7d  AS (PARTITION BY p."idOLBUserTxns", p.recipient_key ORDER BY p."createdAtTxns" RANGE BETWEEN INTERVAL '7 days'  PRECEDING AND INTERVAL '1 microsecond' PRECEDING),
   r60d AS (PARTITION BY p."idOLBUserTxns", p.recipient_key ORDER BY p."createdAtTxns" RANGE BETWEEN INTERVAL '60 days' PRECEDING AND INTERVAL '1 microsecond' PRECEDING)
),
recipient_hist AS (
 SELECT
   l1.*,
   SUM(CASE WHEN l1."createdAtRecipient" IS NOT NULL
             AND l1."createdAtTxns"::date >= l1."createdAtRecipient" THEN 1 ELSE 0 END)
   OVER (PARTITION BY l1."idOLBUserTxns", l1.recipient_key
         ORDER BY l1."createdAtTxns" ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
   AS txn_after_recipient_creation
 FROM l1
),
first_ts AS (
 SELECT t."idOLBUserTxns", t.recipient_key, MIN(t."createdAtTxns") AS first_ts_user_recipient
 FROM tx_train t GROUP BY t."idOLBUserTxns", t.recipient_key
),
first_ts_acct AS (
 SELECT t."idOLBUserTxns", t."AccountNumberFrom", t.recipient_key, MIN(t."createdAtTxns") AS first_ts_account_recipient
 FROM tx_train t WHERE t."AccountNumberFrom" IS NOT NULL
 GROUP BY t."idOLBUserTxns", t."AccountNumberFrom", t.recipient_key
),
first_flags AS (
 SELECT
   t.*,
   CASE WHEN ft.first_ts_user_recipient = t."createdAtTxns" THEN 1 ELSE 0 END AS is_first_user_recipient_ever,
   CASE WHEN fta.first_ts_account_recipient IS NOT NULL AND fta.first_ts_account_recipient = t."createdAtTxns" THEN 1 ELSE 0 END AS is_first_account_recipient_ever,
   CASE WHEN ft.first_ts_user_recipient <= t."createdAtTxns" - INTERVAL '6 hours' THEN 1 ELSE 0 END AS is_first_user_recipient_q_6h,
   CASE WHEN fta.first_ts_account_recipient IS NOT NULL AND fta.first_ts_account_recipient <= t."createdAtTxns" - INTERVAL '72 hours' THEN 1 ELSE 0 END AS is_first_account_recipient_q_72h
 FROM tx_train t
 JOIN first_ts ft ON ft."idOLBUserTxns" = t."idOLBUserTxns" AND ft.recipient_key = t.recipient_key
 LEFT JOIN first_ts_acct fta
   ON fta."idOLBUserTxns" = t."idOLBUserTxns"
  AND fta."AccountNumberFrom" = t."AccountNumberFrom"
  AND fta.recipient_key = t.recipient_key
),
financial_dim AS (
 SELECT
   u.id::bigint AS "idOLBUser",
   COUNT(DISTINCT CASE WHEN aa.account_type='CHECKING'    THEN aa.account_id END) AS num_checking_accounts,
   COUNT(DISTINCT CASE WHEN aa.account_type='SAVING'      THEN aa.account_id END) AS num_savings_accounts,
   COUNT(DISTINCT CASE WHEN aa.account_type='LOAN'        THEN aa.account_id END) AS num_loan_accounts,
   COUNT(DISTINCT CASE WHEN aa.account_type='CREDIT_CARD' THEN aa.account_id END) AS num_credit_card_accounts,
   COUNT(DISTINCT CASE WHEN aa.account_type='OPEN_ENDED_LOANS' THEN aa.account_id END) AS num_open_ended_loans_accounts,
   COUNT(DISTINCT aa.account_id) AS total_accounts
 FROM "OLBUser" u
 LEFT JOIN "BlossomUser" bu ON u."idBlossomUser"=bu.id
 LEFT JOIN (
   SELECT u2.id AS "idOLBUser", sa.id AS account_id, at.value AS account_type
   FROM "OLBUser" u2
   LEFT JOIN "OLBUserAccount" ua ON ua."idOLBUser"=u2.id AND ua."deletedAt" IS NULL
   LEFT JOIN "OLBSubAccountUser" su ON su."idOLBUserAccount"=ua.id
   LEFT JOIN "OLBSubAccount" sa     ON sa.id=su."idSubAccount" AND sa."deletedAt" IS NULL
   LEFT JOIN "OLBAccountType" at    ON at.id=sa."idOLBAccountType"
   WHERE u2."deletedAt" IS NULL
   UNION ALL
   SELECT u3.id, l.id, at2.value
   FROM "OLBUser" u3
   LEFT JOIN "OLBUserAccount" ua2 ON ua2."idOLBUser"=u3.id AND ua2."deletedAt" IS NULL
   LEFT JOIN "OLBUserLoan" ul ON ul."idOLBUserAccount"=ua2.id AND ul."deletedAt" IS NULL
   LEFT JOIN "OLBLoan" l ON l.id=ul."idOLBLoan" AND l."deletedAt" IS NULL
   LEFT JOIN "OLBAccountType" at2 ON at2.id=l."idOLBAccountType"
   WHERE u3."deletedAt" IS NULL
 ) aa ON aa."idOLBUser" = u.id
 WHERE bu."deletedAt" IS NULL AND u."deletedAt" IS NULL
 GROUP BY u.id
),
update_latest AS (
 SELECT ui."idBlossomUser",
        MAX(CASE WHEN ui."UpdatedField"='Phone' THEN ui."UpdatedDate" END) AS phone_updated_date,
        MAX(CASE WHEN ui."UpdatedField"='Email' THEN ui."UpdatedDate" END) AS email_updated_date
 FROM (
   SELECT DISTINCT "idBlossomUser", "updatedAt"::date AS "UpdatedDate", 'Phone' AS "UpdatedField"
   FROM "BlossomUserPhone"
   WHERE "primary"=TRUE AND verifed=TRUE AND ("updatedAt"::date - "createdAt"::date) > 1
   UNION ALL
   SELECT DISTINCT "idBlossomUser", "updatedAt"::date, 'Email'
   FROM "BlossomUserEmail"
   WHERE "primary"=TRUE AND verifed=TRUE AND ("updatedAt"::date - "createdAt"::date) > 1
 ) ui
 GROUP BY ui."idBlossomUser"
),
users_dim AS (
 SELECT DISTINCT
   u.id::bigint AS "idOLBUser",
   u."idBlossomUser",
   u."createdAt"::date AS "createdAtUser",
   CASE
     WHEN 'MEMBER'  = ANY(ur.role_names) AND NOT 'BUSINESS' = ANY(ur.role_names) THEN 'personal'
     WHEN 'BUSINESS'= ANY(ur.role_names) AND NOT 'MEMBER'   = ANY(ur.role_names) THEN 'business'
     WHEN 'MEMBER'  = ANY(ur.role_names) AND     'BUSINESS' = ANY(ur.role_names) THEN 'mixed'
     ELSE 'unknown'
   END AS "user_type",
   EXTRACT(YEAR FROM age(bup."birthDay")) AS "user_age"
 FROM "BlossomUser" bu
 JOIN "OLBUser" u ON u."idBlossomUser" = bu.id AND u."deletedAt" IS NULL
 LEFT JOIN (
   SELECT bu2.id AS "idBlossomUser", array_agg(DISTINCT r."type") AS role_names
   FROM "BlossomUser" bu2
   JOIN "OLBUser" uu ON uu."idBlossomUser"=bu2.id AND uu."deletedAt" IS NULL
   JOIN "OLBFiSubRole" sr ON sr.id = uu."idOLBFiSubRole"
   JOIN "OLBUserRole" r   ON r.id = sr."idOLBUserRole"
   WHERE bu2."deletedAt" IS NULL
   GROUP BY bu2.id
 ) ur ON ur."idBlossomUser" = bu.id
 LEFT JOIN "BlossomUserProfile" bup ON bup."idBlossomUser" = bu.id
 WHERE bu."deletedAt" IS NULL
),
session_activity AS (
 SELECT
   ml."idOLBUser",
   ml."idBlossomUserSession",
   (ARRAY_AGG(CASE WHEN ml."deviceInfo"::jsonb ? 'mobile'  THEN 'MOBILE'
                   WHEN ml."deviceInfo"::jsonb ? 'desktop' THEN 'DESKTOP'
                   ELSE NULL END ORDER BY ml."createdAt" DESC))[1] AS access,
   SUM(CASE WHEN ml.action IN (
     'ACCESS_FROM_BLOCKED_IP','FAILED_LOGIN_ATTEMPT_DUE_TO_INCORRECT_PASSWORD',
     'LOCKED_ACCOUNT','UNSUCCESSFUL_LOGIN_ATTEMPT') THEN 1 ELSE 0 END) AS failed_actions_session,
   SUM(CASE WHEN ml.action IN (
     'EXTERNAL_ACCOUNT_ADDED','RECIPIENT_UPDATED','EXISTING_CONTACT_EDITED',
     'CHANGE_PASSWORD','EMAIL_DELETED','DEBIT_CARD_UNFROZEN') THEN 1 ELSE 0 END) AS suspected_actions_session,
   COUNT(*) AS total_actions_session,
   MAX(CASE WHEN ml.action IN ('EMAIL_VERIFICATION_-1_DAYS','EMAIL_VERIFICATION_30_DAYS','EMAIL_VERIFICATION_365_DAYS') THEN 1 ELSE 0 END) AS is_auth_email_session,
   MAX(CASE WHEN ml.action IN ('PHONE_NUMBER_VERIFICATION','PHONE_NUMBER_VERIFICATION_30_DAYS','PHONE_NUMBER_VERIFICATION_365_DAYS') THEN 1 ELSE 0 END) AS is_auth_phone_session
 FROM "OLBMembersLog" ml
 JOIN "OLBUser" u ON u.id = ml."idOLBUser"
 JOIN fi_bounds fb ON fb."idFi" = u."idFi"
 WHERE ml."createdAt" >= fb.lower_utc AND ml."createdAt" < fb.upper_utc
 GROUP BY 1,2
),
preagg_all AS (
 SELECT
   p."TransactionID", p."idOLBUserTxns", p."createdAtTxns",
   COUNT(*) OVER w6m AS all_txns_total_6m,
   SUM(CASE WHEN p.rn_day_all=1 THEN 1 ELSE 0 END) OVER w6m AS all_active_days_6m,
   SUM(p.amount) OVER w6m AS all_sum_amt_6m,
   COUNT(*) FILTER (WHERE p.is_ach=1) OVER w6m AS ach_txns_total_6m,
   SUM(CASE WHEN p.is_ach=1 AND p.rn_day_ach=1 THEN 1 ELSE 0 END) OVER w6m AS ach_active_days_6m,
   SUM(p.amount) FILTER (WHERE p.is_ach=1) OVER w6m AS ach_sum_amt_6m
 FROM (
   SELECT t.*, DATE(t."createdAtTxns") AS day_key,
          (CASE WHEN t."TransactionGroup"='ACH' THEN 1 ELSE 0 END) AS is_ach,
          ROW_NUMBER() OVER (PARTITION BY t."idOLBUserTxns", DATE(t."createdAtTxns") ORDER BY t."createdAtTxns") AS rn_day_all,
          ROW_NUMBER() OVER (PARTITION BY t."idOLBUserTxns", DATE(t."createdAtTxns"), (CASE WHEN t."TransactionGroup"='ACH' THEN 1 ELSE 0 END) ORDER BY t."createdAtTxns") AS rn_day_ach
   FROM (SELECT id AS "TransactionID", "idOLBUserFrom" AS "idOLBUserTxns", "createdAt" AS "createdAtTxns",
                amount::numeric, status AS "TransactionStatus", tcat."group" AS "TransactionGroup"
         FROM "OLBTraceSubAccountTransaction" otsat
         JOIN "OLBUser" u ON u.id = otsat."idOLBUserFrom" AND u."deletedAt" IS NULL
         JOIN fi_bounds fb ON fb."idFi" = u."idFi"
         LEFT JOIN "OLBTraceSubAccountTransactionCategory" tcat ON tcat.id = otsat."idOLBTraceSubAccountTransactionCategory"
         WHERE otsat."createdAt" >= fb.lower_utc AND otsat."createdAt" < fb.upper_utc
           AND EXISTS (SELECT 1 FROM users_in_scope s WHERE s.id = u.id)
        ) t
 ) p
 WINDOW w6m AS (PARTITION BY p."idOLBUserTxns" ORDER BY p."createdAtTxns"
                RANGE BETWEEN INTERVAL '6 months' PRECEDING AND INTERVAL '1 microsecond' PRECEDING)
),
final AS (
 SELECT
   e."TransactionID", e."idOLBUserTxns", e."createdAtTxns", e."idFi", e.recipient_key,
   e.amount, e.is_night, e.hour_sin, e.hour_cos, e.day_of_week_cos, e.month_cos,
   ur.count_all_txn_last_5m, ur.total_amount_all_txn_last_5m,
   urr.count_txn_to_recipient_account_last_5m, urr.total_amount_txn_to_recipient_account_last_5m,
   e.count_txn_to_recipient_lst2m::int AS count_txn_to_recipient_account_in_last_2_months,
   ff.is_first_user_recipient_q_6h     AS is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h,
   ff.is_first_account_recipient_q_72h AS is_first_txn_from_this_account_to_recipient_account_q_72h,
   (e.std_amt_6m / NULLIF(e.sum_amt_6m / NULLIF(e.total_count_6m,0),0)) AS amount_coef_var_lst6m,
   e.pct_txns_under_100_lst6m, e.pct_txns_over_1k_lst6m,
   (pa.all_txns_total_6m::numeric/NULLIF(pa.all_active_days_6m,0)) AS user_avg_count_txn_per_active_day_last_6_months,
   (pa.all_sum_amt_6m/NULLIF(pa.all_active_days_6m,0)) AS user_avg_amount_txn_per_active_day_last_6_months,
   pa.all_txns_total_6m AS count_user_all_txn_in_last_6_months,
   e.count_cancelled_txn_lst1w AS count_user_cancelled_txn_in_last_week,
   e.count_cancelled_txn_lst1m AS count_user_cancelled_txn_in_last_month,
   e.count_potentialfraud_txn_lst2m AS count_user_potential_fraud_txn_in_last_2_months,
   CASE WHEN u."createdAtUser" IS NOT NULL
        THEN GREATEST((e."createdAtTxns"::date - u."createdAtUser"),0)::int END AS recency_user_created_days,
   COALESCE(sdf.is_access_from_remembered_device,0)::int AS is_access_from_remembered_device,
   sa.suspected_actions_session AS count_suspected_actions_in_current_session,
   sa.total_actions_session, sa.is_auth_email_session,
   f.total_accounts,
   (f.num_checking_accounts::numeric/NULLIF(f.total_accounts,0)) AS checking_ratio,
   (f.num_savings_accounts::numeric/NULLIF(f.total_accounts,0))  AS savings_ratio,
   ((f.num_loan_accounts + f.num_credit_card_accounts + f.num_open_ended_loans_accounts)::numeric/NULLIF(f.total_accounts,0)) AS credit_loan_ratio,
   u."user_age", e."TransactionProcessingType", e."TransactionOrigin", e."TransactionCategory",
   u."user_type", sa.access,
   cat.cu_avg_amount_ach_txn_in_last_6_months,
   CASE WHEN e.amount > cp95.cu_p95 THEN 1 ELSE 0 END AS is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months,
   (e.amount / NULLIF(cat.cu_avg_amount_ach_txn_in_last_6_months,0)) AS txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months,
   e.is_batch, e.num_recipients_batch,
   CASE WHEN e.is_batch=1 AND e.total_amount_batch > 0 THEN (e.amount / e.total_amount_batch) ELSE 0 END AS amount_share_in_batch,
   sa.failed_actions_session AS count_failed_actions_in_current_session,
   sa.is_auth_phone_session,
   e.count_txn_to_recipient_lst1w::int AS count_txn_to_recipient_account_in_last_week,
   e.txn_after_recipient_creation AS count_all_txn_after_recipient_account_creation,
   GREATEST(sa.is_auth_email_session, sa.is_auth_phone_session) AS is_any_auth_session,
   CASE WHEN ul.phone_updated_date IS NOT NULL THEN GREATEST((e."createdAtTxns"::date - ul.phone_updated_date),0)::int END AS days_since_phone_update,
   CASE WHEN ul.email_updated_date IS NOT NULL THEN GREATEST((e."createdAtTxns"::date - ul.email_updated_date),0)::int END AS days_since_email_update,
   (pa.ach_sum_amt_6m/NULLIF(pa.ach_active_days_6m,0)) AS user_avg_amount_ach_txn_per_active_day_last_6_months,
   (e.amount / NULLIF((pa.ach_sum_amt_6m/NULLIF(pa.ach_active_days_6m,0)),0)) AS amt_vs_user_ach_avg_day,
   (pa.ach_sum_amt_6m  / NULLIF(pa.all_sum_amt_6m,0))    AS ach_amount_share_6m,
   (pa.ach_txns_total_6m/ NULLIF(pa.all_txns_total_6m,0)) AS ach_count_share_6m,
   e.weekend,
   CASE WHEN ul.phone_updated_date IS NOT NULL
         AND ul.phone_updated_date > (e."createdAtTxns"::date - INTERVAL '7 days')
         AND ul.phone_updated_date <= e."createdAtTxns"::date THEN 1 ELSE 0 END AS is_personal_user_phone_primary_updated_last_week,
   CASE WHEN ul.email_updated_date IS NOT NULL
         AND ul.email_updated_date > (e."createdAtTxns"::date - INTERVAL '7 days')
         AND ul.email_updated_date <= e."createdAtTxns"::date THEN 1 ELSE 0 END AS is_personal_user_email_primary_updated_last_week
 FROM recipient_hist e
 JOIN first_flags ff ON ff."TransactionID" = e."TransactionID"
 LEFT JOIN users_dim u   ON u."idOLBUser" = e."idOLBUserTxns"
 LEFT JOIN update_latest ul ON ul."idBlossomUser" = u."idBlossomUser"
 LEFT JOIN financial_dim f  ON f."idOLBUser" = e."idOLBUserTxns"
 LEFT JOIN session_activity sa ON sa."idOLBUser" = e."idOLBUserTxns"
   AND sa."idBlossomUserSession" = (
     SELECT ml."idBlossomUserSession" FROM "OLBMembersLog" ml
     WHERE ml."idOLBUser" = e."idOLBUserTxns"
       AND (ml.affected->>'%a')::bigint = e."TransactionID"
     ORDER BY ml."createdAt" DESC LIMIT 1)
 LEFT JOIN (SELECT "idOLBUser", "TransactionID",
              CASE WHEN EXISTS (SELECT 1 FROM "RememberDevices" rd
                                JOIN "BlossomUser" bu2 ON bu2.id=rd."idBlossomUser"
                                JOIN "OLBUser" u2 ON u2."idBlossomUser"=bu2.id
                                WHERE u2.id = sa2."idOLBUser" AND rd."deletedAt" IS NULL) THEN 1 ELSE 0 END
              AS is_access_from_remembered_device
            FROM session_activity sa2, LATERAL (VALUES (NULL)) _) sdf
   ON sdf."idOLBUser" = e."idOLBUserTxns" AND sdf."TransactionID" = e."TransactionID"
 LEFT JOIN preagg_all pa ON pa."TransactionID" = e."TransactionID" AND pa."idOLBUserTxns" = e."idOLBUserTxns"
 LEFT JOIN LATERAL (SELECT cu_avg_amount_ach_txn_in_last_6_months FROM cu_day_roll
                    WHERE "idFi"=e."idFi" AND cu_day <= DATE(e."createdAtTxns")
                    ORDER BY cu_day DESC LIMIT 1) cat ON TRUE
 LEFT JOIN LATERAL (SELECT cu_p95_amount_ach_txn_in_last_6_months AS cu_p95 FROM cu_day_roll
                    WHERE "idFi"=e."idFi" AND cu_day <= DATE(e."createdAtTxns")
                    ORDER BY cu_day DESC LIMIT 1) cp95 ON TRUE
 LEFT JOIN user_roll ur   ON ur."TransactionID"  = e."TransactionID"
 LEFT JOIN user_rec_roll urr ON urr."TransactionID" = e."TransactionID"
)
SELECT
  "TransactionID", "idOLBUserTxns", "createdAtTxns", "idFi", recipient_key,
  amount, is_night, hour_sin, hour_cos, day_of_week_cos, month_cos,
  count_all_txn_last_5m, total_amount_all_txn_last_5m,
  count_txn_to_recipient_account_last_5m, total_amount_txn_to_recipient_account_last_5m,
  count_txn_to_recipient_account_in_last_2_months,
  is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h,
  is_first_txn_from_this_account_to_recipient_account_q_72h,
  amount_coef_var_lst6m, pct_txns_under_100_lst6m, pct_txns_over_1k_lst6m,
  user_avg_count_txn_per_active_day_last_6_months,
  user_avg_amount_txn_per_active_day_last_6_months,
  count_user_all_txn_in_last_6_months,
  count_user_cancelled_txn_in_last_week, count_user_cancelled_txn_in_last_month,
  count_user_potential_fraud_txn_in_last_2_months,
  recency_user_created_days, is_access_from_remembered_device,
  count_suspected_actions_in_current_session, total_actions_session,
  is_auth_email_session, total_accounts,
  checking_ratio, savings_ratio, credit_loan_ratio, user_age,
  "TransactionProcessingType", "TransactionOrigin", "TransactionCategory",
  user_type, access,
  cu_avg_amount_ach_txn_in_last_6_months,
  is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months,
  txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months,
  is_batch, num_recipients_batch, amount_share_in_batch,
  count_failed_actions_in_current_session, is_auth_phone_session,
  count_txn_to_recipient_account_in_last_week,
  count_all_txn_after_recipient_account_creation, is_any_auth_session,
  days_since_phone_update, days_since_email_update,
  amt_vs_user_ach_avg_day, ach_amount_share_6m, ach_count_share_6m,
  weekend,
  is_personal_user_phone_primary_updated_last_week,
  is_personal_user_email_primary_updated_last_week
FROM final
```

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
