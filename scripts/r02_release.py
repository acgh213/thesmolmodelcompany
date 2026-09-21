"""Forgejo release persistence procedure; gated and uninvoked by default."""
from __future__ import annotations
import hashlib, json, os, urllib.parse, urllib.request, uuid
from dataclasses import dataclass
from pathlib import Path
from scripts.r02_preflight import sha256_stream
@dataclass(frozen=True)
class ReleaseRoundTrip:
    source_sha256: str; readback_sha256: str; source_bytes: int; readback_bytes: int; release_id: str; asset_id: str
class ForgejoReleaseTransport:
    def __init__(self, api_base: str, owner: str, repo: str, token: str | None = None):
        self.base=api_base.rstrip('/'); self.owner=owner; self.repo=repo; self.token=token or os.environ.get('FORGEJO_TOKEN')
        if not self.token: raise PermissionError('FORGEJO_TOKEN is required only for an authorized live persistence check')
    def _request(self, method, path, data=None, headers=None):
        h={'Authorization': f'token {self.token}'}; h.update(headers or {})
        req=urllib.request.Request(self.base+path, data=data, headers=h, method=method)
        with urllib.request.urlopen(req) as r: return r.status, r.read(), dict(r.headers)
    def create_release(self):
        _, body, _=self._request('POST',f'/repos/{self.owner}/{self.repo}/releases',json.dumps({'tag_name':'r02-persistence-'+uuid.uuid4().hex,'name':'R02 persistence probe','body':'Temporary gated round-trip'}).encode(),{'Content-Type':'application/json'})
        return str(json.loads(body)['id'])
    def upload_asset(self, release_id, path):
        boundary='----r02'+uuid.uuid4().hex; data=Path(path).read_bytes(); name=Path(path).name
        payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
        _,body,_=self._request('POST',f'/repos/{self.owner}/{self.repo}/releases/{release_id}/assets?name={urllib.parse.quote(name)}',payload,{'Content-Type':f'multipart/form-data; boundary={boundary}'})
        return str(json.loads(body)['id'])
    def read_asset_url(self, release_id, asset_id):
        _,body,_=self._request('GET',f'/repos/{self.owner}/{self.repo}/releases/{release_id}/assets')
        for asset in json.loads(body):
            if str(asset['id'])==str(asset_id): return asset['browser_download_url']
        raise KeyError(asset_id)
    def download(self, url):
        req=urllib.request.Request(url,headers={'Authorization':f'token {self.token}'})
        with urllib.request.urlopen(req) as r: return r.read()
    def delete_release(self, release_id): self._request('DELETE',f'/repos/{self.owner}/{self.repo}/releases/{release_id}')
def release_round_trip(source: str | Path, transport) -> ReleaseRoundTrip:
    path=Path(source); rid=transport.create_release()
    try:
        aid=transport.upload_asset(rid,path); payload=transport.download(transport.read_asset_url(rid,aid))
        result=ReleaseRoundTrip(sha256_stream(path),hashlib.sha256(payload).hexdigest(),path.stat().st_size,len(payload),rid,aid)
        if result.source_sha256 != result.readback_sha256 or result.source_bytes != result.readback_bytes: raise ValueError('release round-trip mismatch')
        return result
    finally: transport.delete_release(rid)

def main():
    if os.environ.get('R02_APPROVED') != '1': raise SystemExit('explicit post-approval gate required: R02_APPROVED=1')
    raise SystemExit('invoke release_round_trip with ForgejoReleaseTransport from an authorized run')
if __name__=='__main__': main()
