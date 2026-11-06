"""Compatibility is a release contract: updates must not reset user state or OAuth."""
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'helper'))
import desktop
spec=importlib.util.spec_from_file_location('upgrade_helper',ROOT/'helper/main.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


class MemorySecrets:
    COLLECTION_DEFAULT='default'
    def __init__(self): self.values={};self.fail_hash=False;self.clear_calls=[]
    def password_lookup_sync(self,schema,attrs,cancel):return self.values.get(attrs['account'])
    def password_store_sync(self,schema,attrs,collection,label,value,cancel):
        if self.fail_hash and attrs['account']!='work@example.invalid':return False
        self.values[attrs['account']]=value;return True
    def password_clear_sync(self,schema,attrs,cancel):
        self.clear_calls.append(attrs['account']);return self.values.pop(attrs['account'],None) is not None


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        for key,value in {'APP_DIR':self.directory,'CONFIG_PATH':self.directory/'config.json',
                          'SNAPSHOT_PATH':self.directory/'snapshot.json','SNAPSHOT_LOCK_PATH':self.directory/'snapshot.lock',
                          'OAUTH_CLIENT_PATH':self.directory/'oauth-client.json','CACHE_DIR':self.directory/'cache'}.items():
            p=patch.object(h,key,value);p.start();self.addCleanup(p.stop)
        self.config=json.loads((ROOT/'tests/fixtures/config-v020.json').read_text())
        h.CONFIG_PATH.write_text(json.dumps(self.config))
        self.oauth='{"installed":{"client_id":"synthetic-client","client_secret":"synthetic-secret"}}\n'
        h.OAUTH_CLIENT_PATH.write_text(self.oauth)
        self.secrets=MemorySecrets()
        @contextlib.contextmanager
        def api():yield self.secrets,'schema',None
        p=patch.object(desktop,'secret_api',side_effect=api);p.start();self.addCleanup(p.stop)
        p=patch.object(desktop,'legacy_schema',return_value='legacy');p.start();self.addCleanup(p.stop)
        self.token={'refresh_token':'existing-refresh','access_token':'existing-access','expires_at':h.time.time()+3600}
        self.address='work@example.invalid'
        self.secrets.values[self.address]=json.dumps(self.token)

    def test_upgrade_restart_and_update_keep_all_settings_and_authorization(self):
        with patch.object(h,'authorize_account',side_effect=AssertionError('Update must not reauthorize')), \
                patch.object(h.webbrowser,'open',side_effect=AssertionError('Update must not open Google')), \
                patch.object(h,'token_request',side_effect=AssertionError('Fresh token must be reused')), \
                patch.object(h,'list_unread_ids',return_value=['abc123']):
            for _ in range(3):
                state=h.build_snapshot(force=True)
                self.assertTrue(state['ok'])
                self.assertEqual(h.token_lookup(self.address)['refresh_token'],'existing-refresh')
        persisted=json.loads(h.CONFIG_PATH.read_text())
        for key,value in self.config.items():
            if key!='accounts':self.assertEqual(persisted[key],value)
        for previous,current in zip(self.config['accounts'],persisted['accounts']):
            for field in ('id','email','initial','enabled','notifications'):
                self.assertEqual(previous[field],current[field])
        self.assertEqual(h.OAUTH_CLIENT_PATH.read_text(),self.oauth)
        self.assertEqual(self.secrets.clear_calls,[])
        # An old release still finds the exact attributes it used before upgrading.
        self.assertEqual(json.loads(self.secrets.values[self.address])['refresh_token'],'existing-refresh')

    def test_refresh_and_rotated_refresh_token_are_mirrored_for_rollback(self):
        old=dict(self.token,expires_at=0)
        self.secrets.values[self.address]=json.dumps(old)
        with patch.object(h,'token_request',return_value={'access_token':'renewed-access','refresh_token':'rotated-refresh','expires_in':3600}):
            h.refresh_access_token(self.address,old,'legacy')
        self.assertEqual(json.loads(self.secrets.values[self.address])['refresh_token'],'rotated-refresh')
        self.assertEqual(json.loads(self.secrets.values[desktop.key(self.address)])['refresh_token'],'rotated-refresh')
        self.assertEqual(self.secrets.clear_calls,[])

    def test_copy_failure_does_not_erase_or_invalidate_original_authorization(self):
        self.secrets.fail_hash=True
        self.assertEqual(h.token_lookup(self.address)['refresh_token'],'existing-refresh')
        self.assertEqual(json.loads(self.secrets.values[self.address])['refresh_token'],'existing-refresh')
        self.assertEqual(self.secrets.clear_calls,[])

    def test_partial_write_uses_fresh_legacy_copy_instead_of_stale_hash(self):
        self.secrets.values[desktop.key(self.address)]=json.dumps(self.token)
        fresh=dict(self.token,access_token='new-access')
        self.secrets.fail_hash=True
        with self.assertRaises(RuntimeError):desktop.store(self.address,fresh)
        self.assertEqual(desktop.lookup(self.address)['access_token'],'new-access')

    def test_hash_only_entry_from_earlier_candidate_restores_rollback_compatibility(self):
        self.secrets.values[desktop.key(self.address)]=self.secrets.values.pop(self.address)
        self.assertEqual(h.token_lookup(self.address),self.token)
        self.assertEqual(json.loads(self.secrets.values[self.address]),self.token)

    def test_new_account_keeps_a_credential_readable_by_older_releases(self):
        desktop.store('new@example.invalid',self.token)
        self.assertEqual(json.loads(self.secrets.values['new@example.invalid']),self.token)
        self.assertEqual(desktop.lookup('new@example.invalid'),self.token)

    def test_only_explicit_removal_clears_both_credential_formats(self):
        h.token_lookup(self.address)
        with patch.object(h,'emit'):self.assertEqual(h.remove_account(self.address),0)
        self.assertNotIn(self.address,self.secrets.values)
        self.assertNotIn(desktop.key(self.address),self.secrets.values)
        self.assertEqual(h.load_config()['accounts'][0]['email'],'home@example.invalid')

    def test_public_state_excludes_private_oauth_bookkeeping(self):
        state=h.snapshot_result(h.load_config(),None)
        for account in state['accounts']:
            for key in ('last_notification_ids','notification_baseline_set','generation','refresh_token','access_token'):
                self.assertNotIn(key,account)

    def test_existing_large_account_list_is_not_rejected_by_new_account_limit(self):
        config=copy.deepcopy(self.config)
        config['accounts']=[dict(config['accounts'][0],id=f'a{i}',email=f'a{i}@example.invalid') for i in range(33)]
        h.CONFIG_PATH.write_text(json.dumps(config))
        self.assertEqual(len(h.load_config()['accounts']),33)

    def test_long_label_saved_by_old_uppercase_expansion_is_preserved(self):
        config=copy.deepcopy(self.config);config['accounts'][0]['initial']='SS'*7
        h.CONFIG_PATH.write_text(json.dumps(config))
        self.assertEqual(h.load_config()['accounts'][0]['initial'],'SS'*7)


class StableStorageContractTests(unittest.TestCase):
    def test_persistent_identity_paths_and_scope_remain_stable(self):
        self.assertEqual(h.APP_DIR,Path.home()/'.config/omarchy/gmail-notifier')
        self.assertEqual(h.CONFIG_PATH,h.APP_DIR/'config.json')
        self.assertEqual(h.OAUTH_CLIENT_PATH,h.APP_DIR/'oauth-client.json')
        self.assertEqual(h.CACHE_DIR,Path.home()/'.cache/omarchy/gmail-notifier')
        self.assertEqual(h.TOKEN_APP,'gmail-notifier')
        self.assertEqual(h.GMAIL_SCOPE,'https://www.googleapis.com/auth/gmail.metadata')
        self.assertEqual(json.loads((ROOT/'manifest.json').read_text())['id'],'eprom.gmail-notifier')
