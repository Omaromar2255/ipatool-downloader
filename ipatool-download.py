import sys
import os
import json
import urllib.request
import subprocess

def get_bundle_and_ext_id(query):
    # If query looks like a bundle id or app id
    country = "us"
    app_id = None
    bundle_id = None
    app_name = None

    # Try lookup by bundle ID
    url1 = f"https://itunes.apple.com/lookup?bundleId={query}&country={country}"
    try:
        req = urllib.request.Request(url1, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            if data.get("results"):
                app = data["results"][0]
                app_id = app["trackId"]
                bundle_id = app["bundleId"]
                app_name = app.get("trackName", bundle_id)
    except Exception:
        pass

    # If not found by bundle ID, try searching by name
    if not app_id:
        url_search = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=software&limit=1&country={country}"
        try:
            req = urllib.request.Request(url_search, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as res:
                data = json.loads(res.read().decode('utf-8'))
                if data.get("results"):
                    app = data["results"][0]
                    app_id = app["trackId"]
                    bundle_id = app["bundleId"]
                    app_name = app.get("trackName", bundle_id)
        except Exception as e:
            print(f"Error searching app: {e}")
            return None, None, None, None

    if not app_id:
        return None, None, None, None

    # Query MZStorePlatform for the external version ID
    url_platform = f"https://uclient-api.itunes.apple.com/WebObjects/MZStorePlatform.woa/wa/lookup?version=2&id={app_id}&p=mdm-lockup&caller=MDM&platform=iphone&cc={country}&l=en"
    ext_id = None
    version_str = ""
    try:
        req = urllib.request.Request(url_platform, headers={"User-Agent": "ipatool"})
        with urllib.request.urlopen(req) as res:
            plat_data = json.loads(res.read().decode('utf-8'))
            results = plat_data.get("results", {})
            if str(app_id) in results:
                offers = results[str(app_id)].get("offers", [])
                if offers:
                    v = offers[0].get("version", {})
                    ext_id = str(v.get("externalId"))
                    version_str = v.get("display", "")
    except Exception as e:
        print(f"Error fetching external version ID: {e}")

    return bundle_id, app_id, ext_id, app_name, version_str

def main():
    if len(sys.argv) < 2:
        print("Usage: python ipatool-download.py <bundle-id or app name> [output.ipa] [passphrase]")
        print("Example: python ipatool-download.py com.google.ios.youtube YouTube.ipa 2211")
        return

    query = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else None
    passphrase = sys.argv[3] if len(sys.argv) > 3 else "2211"

    print(f"[*] Resolving app details for '{query}'...")
    bundle_id, app_id, ext_id, app_name, version_str = get_bundle_and_ext_id(query)

    if not bundle_id or not ext_id:
        print(f"[!] Could not find app or external version ID for '{query}'.")
        return

    downloads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    if not output_name:
        # Default filename based on app name
        clean_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '_', '-')).strip()
        output_name = os.path.join(downloads_dir, f"{clean_name}.ipa")
    elif not os.path.isabs(output_name):
        output_name = os.path.join(downloads_dir, output_name)

    print(f"[+] Found App: {app_name}")
    print(f"    Bundle ID: {bundle_id}")
    print(f"    App ID: {app_id}")
    print(f"    Latest Version: {version_str} (External ID: {ext_id})")
    print(f"    Output File: {output_name}")
    print(f"[*] Starting download via ipatool...")

    cmd = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipatool.exe"),
        "download",
        "--bundle-identifier", bundle_id,
        "--external-version-id", ext_id,
        "--keychain-passphrase", passphrase,
        "--output", output_name,
        "--purchase"
    ]

    subprocess.run(cmd)

if __name__ == "__main__":
    main()
