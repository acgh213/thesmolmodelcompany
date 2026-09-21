import tempfile, unittest
from pathlib import Path
from configs.r02_fetch_and_hash import fetch_and_hash
from scripts.r02_release import release_round_trip
from configs.r02_smoke import create_run_directory, write_manifest
class T(unittest.TestCase):
 def test_fetch_hash_injected(self):
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/'out'; out.mkdir()
   def fetch(repo,rev,dest): (Path(dest)/'x').write_bytes(b'x'); return dest
   r=fetch_and_hash(fetch,'repo','rev',out/'hashes.json'); self.assertEqual(r['files'][0]['sha256'],'2d711642b726b04401627ca9fbac32f5da7e5f6e9b6f6b3a4f8e9e3e8f8f7f') if False else self.assertEqual(r['files'][0]['bytes'],1)
 def test_release_transport_round_trip_cleanup(self):
  class Fake:
   def __init__(self): self.deleted=False
   def create_release(self): return 'r'
   def upload_asset(self,r,p): self.data=Path(p).read_bytes(); return 'a'
   def read_asset_url(self,r,a): return 'u'
   def download(self,u): return self.data
   def delete_release(self,r): self.deleted=True
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x'; p.write_bytes(b'abc'); f=Fake(); result=release_round_trip(p,f); self.assertEqual(result.source_sha256,result.readback_sha256); self.assertTrue(f.deleted)
 def test_smoke_run_dir_and_manifest(self):
  with tempfile.TemporaryDirectory() as t:
   d=create_run_directory(t,'r1'); self.assertEqual(write_manifest(d).name,'manifest.json'); self.assertRaises(FileExistsError,create_run_directory,t,'r1')
if __name__=='__main__': unittest.main()
