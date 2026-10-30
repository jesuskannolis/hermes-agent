import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile, os
from hermes_cli import changeover_standby as policy
from hermes_cli import kanban_db as kb

class StandbyTest(unittest.TestCase):
 def test_pause(self):
  with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'home', return_value=Path(folder)), patch.dict(os.environ, {'HERMES_HOME':folder}):
   root=Path(folder); conn=__import__('hermes_cli.kanban_db_connect',fromlist=['connect']).connect(root/'kanban.db')
   tid=kb.create_task(conn,title='Retained work',initial_status='blocked')
   marker=root/'.changeover/state/agent-execution-standby.json';marker.parent.mkdir(parents=True);marker.write_text(json.dumps({'kanban':'paused'}))
   with self.assertRaises(PermissionError):kb.create_task(conn,title='Must not exist')
   with self.assertRaises(PermissionError):kb.assign_task(conn,tid,'neo')
   result=__import__('hermes_cli.kanban_db_dispatch',fromlist=['dispatch_once']).dispatch_once(conn,spawn_fn=lambda *a,**k:self.fail('spawned'))
   self.assertEqual(result.spawned,[])
   self.assertEqual(kb.get_task(conn,tid).title,'Retained work')
   self.assertEqual(conn.execute('select count(*) from tasks').fetchone()[0],1)
   from tools.kanban_tools import _visible
   self.assertFalse(_visible(to_env_worker=True))
   from hermes_cli.kanban import kanban_command
   from argparse import Namespace
   with self.assertRaises(PermissionError):kanban_command(Namespace())
   marker.write_text('{bad');self.assertTrue(policy.paused())
   marker.unlink();self.assertFalse(policy.paused())
   kb.create_task(conn,title='Resumed work',initial_status='blocked');conn.close()
if __name__=='__main__': unittest.main()
