import pytest
from app.service.research_lab_store import LabRecords,LabNotFound
from app.store.postgres import PostgresDecisionEventStore
from app.store.sqlite import StoreConflictError
from tests.integration.test_personal_workbench_postgres import isolated_postgres


def test_lab_portable_migration_cas_isolation_and_restart(isolated_postgres):
    store=PostgresDecisionEventStore(isolated_postgres)
    records=LabRecords(store)
    first=records.write('alice','goals','uses',0,{'name':'资金目标','config':{'amount':'10000'},'latest':None})
    assert first['revision']==1
    with pytest.raises(StoreConflictError):
        records.write('alice','goals','uses',0,{'name':'冲突'})
    records.write('alice','goals','uses',1,{'name':'修订目标','config':{'amount':'20000'}})
    assert records.get('alice','goals','uses',1)['payload']['config']['amount']=='10000'
    assert records.list('bob','goals')==[]
    with pytest.raises(LabNotFound):
        records.get('bob','goals','uses')
    assert 24 in {r['version'] for r in store._connection.execute('SELECT version FROM schema_migrations').fetchall()}
    store.close()
    reopened=PostgresDecisionEventStore(isolated_postgres)
    assert LabRecords(reopened).get('alice','goals','uses')['revision']==2
    reopened.close()
