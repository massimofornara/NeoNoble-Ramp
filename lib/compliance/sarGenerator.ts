import { query, writeQuery } from '@/lib/exchange/db';

export async function generateSarReport(caseId: string) {
  const complianceCase = (await query<{ id: string; user_id: string; case_type: string; severity: string; score: number; payload: unknown }>(
    'select id::text, user_id, case_type, severity, score, payload from compliance_cases where id = $1',
    [caseId],
  ))[0];
  if (!complianceCase) throw new Error('Compliance case not found');

  const transactions = await query(
    `select lt.id::text, lt.transaction_type, lt.state::text, lt.created_at
     from ledger_transactions lt
     where exists (
       select 1 from journal_entries je
       join accounts a on a.id = je.account_id
       where je.ledger_transaction_id = lt.id and a.owner_id = $1
     )
     order by lt.created_at desc
     limit 100`,
    [complianceCase.user_id],
  );

  const report = {
    schema: 'NeoNobleSAR/v1',
    case: complianceCase,
    transactions,
    generatedAt: new Date().toISOString(),
    narrative: `Automated SAR draft for ${complianceCase.case_type} severity ${complianceCase.severity} score ${complianceCase.score}.`,
  };

  const row = await writeQuery<{ id: string }>(
    'insert into sar_reports(case_id, user_id, report) values ($1, $2, $3) returning id::text',
    [caseId, complianceCase.user_id, JSON.stringify(report)],
  );
  return { id: row[0].id, report };
}
