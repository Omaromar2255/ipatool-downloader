import uuid
import json
import plistlib
import urllib.request

mac = '%012X' % uuid.getnode()
print('MAC/GUID:', mac)

with open(r'C:\Users\pc5\.ipatool\cookies', 'r', encoding='utf-8') as f:
    cookies = json.load(f)

cookie_parts = []
for c in cookies:
    val = c.get('Value')
    name = c.get('Name')
    if val and name:
        cookie_parts.append(f"{name}={val}")

cookie_header = '; '.join(cookie_parts)
dsid = '20912319274'

# YouTube: 544007664, latest external: 892063802
payload = {
    'creditDisplay': '',
    'guid': mac,
    'salableAdamId': 544007664,
    'serialNumber': '0',
    'externalVersionId': '892063802'
}
plist_bytes = plistlib.dumps(payload, fmt=plistlib.FMT_XML)

url = f'https://p52-buy.itunes.apple.com/WebObjects/MZFinance.woa/wa/volumeStoreDownloadProduct?guid={mac}'
headers = {
    'Content-Type': 'application/x-apple-plist',
    'iCloud-DSID': dsid,
    'X-Dsid': dsid,
    'User-Agent': 'Configurator/2.17 (Macintosh; OS X 15.2; 24C5089c) AppleWebKit/0620.1.16.11.6',
    'Cookie': cookie_header
}

req = urllib.request.Request(url, data=plist_bytes, headers=headers, method='POST')
try:
    with urllib.request.urlopen(req) as resp:
        res_data = resp.read()
        res_plist = plistlib.loads(res_data)
        items = res_plist.get('songList', [])
        if items:
            metadata = items[0].get('metadata', {})
            ver_ids = metadata.get('softwareVersionExternalIdentifiers', [])
            print('Success! Total versions count:', len(ver_ids))
            print('First 5 versions:', ver_ids[:5])
            print('Last 10 versions:', ver_ids[-10:])
        else:
            print('No items:', list(res_plist.keys()), 'Message:', res_plist.get('customerMessage'), 'Failure:', res_plist.get('failureType'))
except Exception as e:
    print('Error:', e)
