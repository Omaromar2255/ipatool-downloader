import uuid
import json
import plistlib
import urllib.request
import subprocess

mac = '94659C755502'
with open(r'C:\Users\pc5\.ipatool\cookies', 'r', encoding='utf-8') as f:
    cookies = json.load(f)

cookie_parts = []
for c in cookies:
    val = c.get('Value')
    name = c.get('Name')
    if val and name:
        cookie_parts.append(f"{name}={val}")

cookie_header = '; '.join(cookie_parts)
dsid = next((str(c.get('Value')) for c in cookies if c.get('Name') == 'X-Dsid' and c.get('Value')), '18672625286')

payload = {
    'creditDisplay': '',
    'guid': mac,
    'salableAdamId': 544007664,
    'serialNumber': '0',
    'appExtVrsId': '892063802'
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
    res_plist = plistlib.loads(resp.read())
    metadata = res_plist['songList'][0]['metadata']
    ver_ids = metadata['softwareVersionExternalIdentifiers']
    print('Total YouTube versions:', len(ver_ids))
    
# Let's sample every 10th version in the last 100 to find June 2025 (or version 19.x - 20.x)
last_100 = ver_ids[-100:]
sample_indices = list(range(0, 100, 10))
for idx in sample_indices:
    vid = last_100[idx]
    cmd = [r'C:\DRIVERS\ipatool.exe', 'get-version-metadata', '--app-id', '544007664', '--external-version-id', str(vid), '--keychain-passphrase', '2211']
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=r'C:\DRIVERS')
    print(f"Index -{100-idx} (ID {vid}): {res.stdout.strip()}")
