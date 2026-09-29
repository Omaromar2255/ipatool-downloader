import uuid
import json
import plistlib
import urllib.request
import zipfile
import io

class RemoteZipReader(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-0'})
        with urllib.request.urlopen(req) as resp:
            cr = resp.headers.get('Content-Range')
            self.size = int(cr.split('/')[-1])
        self.pos = 0

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        return self.pos

    def tell(self):
        return self.pos

    def read(self, size=-1):
        if size == -1 or self.pos + size > self.size:
            size = self.size - self.pos
        if size <= 0:
            return b""
        end = self.pos + size - 1
        req = urllib.request.Request(self.url, headers={'Range': f'bytes={self.pos}-{end}'})
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        self.pos += len(data)
        return data

def get_version_info(app_id, external_version_id):
    mac = '94659C755502'
    with open(r'C:\Users\pc5\.ipatool\cookies', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    cookie_parts = []
    for c in cookies:
        if c.get('Value') and c.get('Name'):
            cookie_parts.append(f"{c['Name']}={c['Value']}")
    cookie_header = '; '.join(cookie_parts)
    dsid = '20912319274'

    payload = {
        'creditDisplay': '',
        'guid': mac,
        'salableAdamId': int(app_id),
        'serialNumber': '0',
        'appExtVrsId': str(external_version_id)
    }
    plist_bytes = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
    url = f'https://downloaddispatch.itunes.apple.com/up/updateProduct?guid={mac}'
    headers = {
        'Content-Type': 'application/x-apple-plist',
        'iCloud-DSID': dsid,
        'X-Dsid': dsid,
        'User-Agent': 'Configurator/2.17 (Macintosh; OS X 15.2; 24C5089c) AppleWebKit/0620.1.16.11.6',
        'Cookie': cookie_header
    }

    req = urllib.request.Request(url, data=plist_bytes, headers=headers, method='POST')
    with urllib.request.urlopen(req) as resp:
        res = plistlib.loads(resp.read())
        items = res.get('songList', [])
        if not items:
            return None
        metadata = items[0].get('metadata', {})
        dl_url = items[0].get('URL')
        
    # Read Info.plist from remote zip without downloading whole file
    rz = RemoteZipReader(dl_url)
    zf = zipfile.ZipFile(rz)
    for name in zf.namelist():
        if name.startswith('Payload/') and name.endswith('.app/Info.plist'):
            with zf.open(name) as pf:
                plist_data = plistlib.loads(pf.read())
                return {
                    'CFBundleShortVersionString': plist_data.get('CFBundleShortVersionString'),
                    'MinimumOSVersion': plist_data.get('MinimumOSVersion'),
                    'CFBundleVersion': plist_data.get('CFBundleVersion'),
                    'externalVersionId': external_version_id
                }
    return None

if __name__ == '__main__':
    import sys
    app_id = sys.argv[1] if len(sys.argv) > 1 else '544007664'
    ext_id = sys.argv[2] if len(sys.argv) > 2 else '875034940'
    print(f"Checking app {app_id}, version {ext_id}...")
    info = get_version_info(app_id, ext_id)
    print("Result:", info)
