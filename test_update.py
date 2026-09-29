import uuid
import json
import plistlib
import urllib.request

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
dsid = '20912319274'

# YouTube: 544007664, latest external: 892063802
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
try:
    with urllib.request.urlopen(req) as resp:
        res_plist = plistlib.loads(resp.read())
        items = res_plist.get('songList', [])
        if items:
            metadata = items[0].get('metadata', {})
            ver_ids = metadata.get('softwareVersionExternalIdentifiers', [])
            print('updateProduct Success! Version identifiers count:', len(ver_ids))
            print('First 5:', ver_ids[:5])
            print('Last 10:', ver_ids[-10:])
            print('Returned softwareVersionExternalIdentifier:', metadata.get('softwareVersionExternalIdentifier'))
            print('Download URL exists:', bool(items[0].get('URL')))
        else:
            print('No items:', list(res_plist.keys()), 'Message:', res_plist.get('customerMessage'), 'Failure:', res_plist.get('failureType'))
except Exception as e:
    print('Error:', e)
