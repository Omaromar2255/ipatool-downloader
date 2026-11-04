import sys
import json
import uuid
import plistlib
import urllib.request
import subprocess

def get_app_id_and_name(query, country="us"):
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

def get_latest_external_id(app_id, country="us"):
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
                    return str(v.get("externalId")), v.get("display", "")
    except Exception:
        pass
    return None, ""

def main():
    if len(sys.argv) < 2:
        print("Usage: python get_app_versions.py <bundle_id or app_name>")
        print("Example: python get_app_versions.py com.burbn.instagram")
        return

    query = sys.argv[1]
    app_id, bundle_id, app_name = get_app_id_and_name(query)
    if not app_id:
        print(f"[!] App '{query}' not found.")
        return

    latest_ext_id, latest_disp = get_latest_external_id(app_id)
    if not latest_ext_id:
        print(f"[!] Could not get latest version for '{app_name}'.")
        return

    print(f"[+] App: {app_name} ({bundle_id})")
    print(f"    App ID: {app_id}")
    print(f"    Latest Version: {latest_disp} (External ID: {latest_ext_id})")

    # Fetch all version IDs via updateProduct
    mac = '%012X' % uuid.getnode()
    cookie_path = r"C:\Users\pc5\.ipatool\cookies"
    with open(cookie_path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    cookie_parts = [f"{c['Name']}={c['Value']}" for c in cookies if c.get('Value') and c.get('Name')]
    cookie_header = '; '.join(cookie_parts)
    dsid = None
    for c in cookies:
        if c.get('Name') == 'X-Dsid' and c.get('Value'):
            dsid = str(c.get('Value'))
            break
    if not dsid:
        dsid = '18672625286'

    payload = {
        'creditDisplay': '',
        'guid': mac,
        'salableAdamId': app_id,
        'serialNumber': '0',
        'appExtVrsId': latest_ext_id
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
    try:
        with urllib.request.urlopen(req) as resp:
            res_plist = plistlib.loads(resp.read())
            items = res_plist.get('songList', [])
            if not items:
                print("[!] Could not retrieve version list.")
                return
            ver_ids = items[0].get('metadata', {}).get('softwareVersionExternalIdentifiers', [])
            print(f"[+] Found {len(ver_ids)} historical versions released by Apple.")
            print("\nRecent 15 External Version IDs (from oldest to newest):")
            for vid in ver_ids[-15:]:
                marker = " <- LATEST" if str(vid) == str(latest_ext_id) else ""
                print(f"  {vid}{marker}")
            print("\nTo inspect a version's details:")
            print(f"  ipatool.exe get-version-metadata --app-id {app_id} --external-version-id <ID> --keychain-passphrase 2211")
            print("\nTo download a specific version:")
            print(f"  ipatool.exe download --bundle-identifier {bundle_id} --external-version-id <ID> --keychain-passphrase 2211 --output app.ipa")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    main()
