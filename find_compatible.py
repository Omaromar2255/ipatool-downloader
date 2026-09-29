import sys
import json
import uuid
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

def get_app_details(query, country="us"):
    url1 = f"https://itunes.apple.com/lookup?bundleId={query}&country={country}"
    try:
        req = urllib.request.Request(url1, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            if data.get("results"):
                app = data["results"][0]
                return app["trackId"], app["bundleId"], app.get("trackName", query)
    except Exception:
        pass

    url_search = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=software&limit=1&country={country}"
    try:
        req = urllib.request.Request(url_search, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            if data.get("results"):
                app = data["results"][0]
                return app["trackId"], app["bundleId"], app.get("trackName", query)
    except Exception:
        pass
    return None, None, None

def get_latest_ext_id(app_id, country="us"):
    url = f"https://uclient-api.itunes.apple.com/WebObjects/MZStorePlatform.woa/wa/lookup?version=2&id={app_id}&p=mdm-lockup&caller=MDM&platform=iphone&cc={country}&l=en"
    req = urllib.request.Request(url, headers={"User-Agent": "ipatool"})
    try:
        with urllib.request.urlopen(req) as res:
            plat_data = json.loads(res.read().decode('utf-8'))
            results = plat_data.get("results", {})
            if str(app_id) in results:
                offers = results[str(app_id)].get("offers", [])
                if offers:
                    v = offers[0].get("version", {})
                    return str(v.get("externalId"))
    except Exception:
        pass
    return None

def get_all_version_ids(app_id, latest_ext_id):
    mac = '94659C755502'
    with open(r'C:\Users\pc5\.ipatool\cookies', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    cookie_parts = [f"{c['Name']}={c['Value']}" for c in cookies if c.get('Value') and c.get('Name')]
    cookie_header = '; '.join(cookie_parts)
    dsid = '20912319274'

    payload = {
        'creditDisplay': '',
        'guid': mac,
        'salableAdamId': int(app_id),
        'serialNumber': '0',
        'appExtVrsId': str(latest_ext_id)
    }
    plist_bytes = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
    url = f"https://downloaddispatch.itunes.apple.com/up/updateProduct?guid={mac}"
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
        if items:
            return items[0].get('metadata', {}).get('softwareVersionExternalIdentifiers', [])
    return []

def get_version_info(app_id, external_version_id):
    mac = '94659C755502'
    with open(r'C:\Users\pc5\.ipatool\cookies', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    cookie_parts = [f"{c['Name']}={c['Value']}" for c in cookies if c.get('Value') and c.get('Name')]
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
    try:
        with urllib.request.urlopen(req) as resp:
            res = plistlib.loads(resp.read())
            items = res.get('songList', [])
            if not items:
                return None
            dl_url = items[0].get('URL')
            
        rz = RemoteZipReader(dl_url)
        zf = zipfile.ZipFile(rz)
        for name in zf.namelist():
            if name.startswith('Payload/') and name.endswith('.app/Info.plist'):
                with zf.open(name) as pf:
                    plist_data = plistlib.loads(pf.read())
                    return {
                        'displayVersion': plist_data.get('CFBundleShortVersionString', ''),
                        'minOS': plist_data.get('MinimumOSVersion', '1.0'),
                        'bundleVersion': plist_data.get('CFBundleVersion', ''),
                        'externalId': external_version_id
                    }
    except Exception:
        pass
    return None

def parse_os(os_str):
    try:
        return [int(x) for x in os_str.split('.') if x.isdigit()]
    except Exception:
        return [99]

def is_os_le(v1_str, v2_str):
    # returns True if v1 <= v2
    p1 = parse_os(v1_str)
    p2 = parse_os(v2_str)
    # pad with zeros
    while len(p1) < len(p2): p1.append(0)
    while len(p2) < len(p1): p2.append(0)
    return p1 <= p2

def find_last_compatible_version(app_id, target_os_str="15.8"):
    latest_ext = get_latest_ext_id(app_id)
    if not latest_ext:
        return None
    ver_ids = get_all_version_ids(app_id, latest_ext)
    if not ver_ids:
        return None

    # Check the latest first
    latest_info = get_version_info(app_id, latest_ext)
    if latest_info and is_os_le(latest_info['minOS'], target_os_str):
        return latest_info

    print(f"[*] Total releases in App Store: {len(ver_ids)}")
    print(f"[*] Searching for last version compatible with iOS {target_os_str}...")

    # Binary search
    low = 0
    high = len(ver_ids) - 1
    best = None

    while low <= high:
        mid = (low + high) // 2
        vid = ver_ids[mid]
        info = get_version_info(app_id, vid)
        if not info:
            # Try adjacent if failed
            high -= 1
            continue

        print(f"  Checking {info['displayVersion']} (ID: {vid}) -> requires iOS {info['minOS']}")
        if is_os_le(info['minOS'], target_os_str):
            best = info
            low = mid + 1  # Look for newer version still <= target_os
        else:
            high = mid - 1  # Too new, look older

    return best

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_compatible.py <bundle_id or app_name> [target_ios_version]")
        print("Example: python find_compatible.py com.burbn.instagram 15.8")
        print("Example: python find_compatible.py com.google.ios.youtube 15.0")
        return

    query = sys.argv[1]
    target_os = sys.argv[2] if len(sys.argv) > 2 else "15.8"

    print(f"[*] Looking up '{query}'...")
    app_id, bundle_id, app_name = get_app_details(query)
    if not app_id:
        print(f"[!] App '{query}' not found.")
        return

    print(f"[+] Found: {app_name} (ID: {app_id}, Bundle: {bundle_id})")
    compat = find_last_compatible_version(app_id, target_os)
    if compat:
        print("\n" + "="*60)
        print(f" SUCCESS! Last compatible version for iOS {target_os}:")
        print(f" App Name:         {app_name}")
        print(f" Display Version:  {compat['displayVersion']}")
        print(f" Minimum iOS:      {compat['minOS']}")
        print(f" Internal Build:   {compat['bundleVersion']}")
        print(f" External ID:      {compat['externalId']}")
        print("="*60)
        print(f"\nDownload command:")
        print(f"  ipatool.exe download -b {bundle_id} --external-version-id {compat['externalId']} --keychain-passphrase 2211 -o \"{app_name}_{compat['displayVersion']}.ipa\"")
    else:
        print(f"[!] Could not determine compatible version for iOS {target_os}.")

if __name__ == "__main__":
    main()
