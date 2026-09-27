"""
Phase 1 — Download the FLNET2023 dataset (CSV files only).

FLNET2023 (Kumar et al., MILCOM 2023) is published as a public SharePoint
folder. Each attack folder has a CSV/ and a PCAP/ subfolder; we only need the
CICFlowMeter CSVs (~3.2 GB). The raw PCAPs are ~136 GB and are skipped.

Files are saved under data/FLNET2023/ keeping the original folder layout,
e.g. data/FLNET2023/DDoS/CSV/Dataset-10-TCP.csv. Files that already exist
with the right size are skipped, and interrupted downloads resume, so the
script can simply be re-run.

Run: venv\\Scripts\\python.exe src\\download_flnet2023.py
"""

import http.client
import http.cookiejar
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "FLNET2023")

SHARE_LINK = (
    "https://eltnmsu-my.sharepoint.com/:f:/g/personal/pratyay_nmsu_edu/"
    "ErDns0cRITtEsawkCgfqYTIB7BGJ_YDfp9r-p_80v3GxIQ?e=UimpBG"
)
SITE = "https://eltnmsu-my.sharepoint.com/personal/pratyay_nmsu_edu"
ROOT = "/personal/pratyay_nmsu_edu/Documents/Dataset"
MAX_ATTEMPTS = 20
PARALLEL_DOWNLOADS = 4


def make_opener():
    # Opening the share link sets the anonymous guest-access cookie that the
    # SharePoint REST API needs for every later request.
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    opener.open(SHARE_LINK, timeout=60).read()
    return opener


def api_path(path):
    return urllib.parse.quote(path.replace("'", "''"))


def list_csvs(opener, path):
    url = (f"{SITE}/_api/web/GetFolderByServerRelativeUrl('{api_path(path)}')"
           "?$expand=Folders,Files")
    req = urllib.request.Request(url, headers={"Accept": "application/json;odata=nometadata"})
    folder = json.load(opener.open(req, timeout=60))
    files = [(f["ServerRelativeUrl"], int(f["Length"]))
             for f in folder["Files"] if f["Name"].lower().endswith(".csv")]
    for sub in folder["Folders"]:
        if sub["Name"] not in ("Forms", "PCAP"):
            files += list_csvs(opener, sub["ServerRelativeUrl"])
    return files


def download(opener, server_path, size):
    rel = server_path[len(ROOT) + 1:]
    dest = os.path.join(OUT_DIR, *rel.split("/"))
    if os.path.exists(dest) and os.path.getsize(dest) == size:
        print(f"  skip  {rel} (already downloaded)")
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    # download.aspx honours Range requests; the REST /$value endpoint does not,
    # and connections tend to be cut after ~200 MB, so resuming matters.
    url = f"{SITE}/_layouts/15/download.aspx?SourceUrl={urllib.parse.quote(server_path)}"
    print(f"  get   {rel} ({size / 1e6:.1f} MB)", flush=True)
    tmp = dest + ".part"
    # SharePoint connections drop now and then on large files; resume from
    # the bytes already in the .part file with an HTTP Range request.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if done >= size:
            break
        req = urllib.request.Request(url, headers={"Range": f"bytes={done}-"})
        try:
            with opener.open(req, timeout=120) as resp:
                # 206 = server honoured the Range; 200 = whole file, restart.
                mode = "ab" if resp.status == 206 else "wb"
                with open(tmp, mode) as fh:
                    while chunk := resp.read(1 << 20):
                        fh.write(chunk)
        except (OSError, http.client.HTTPException) as err:
            print(f"        interrupted at {done / 1e6:.1f} MB ({err}); "
                  f"retry {attempt}/{MAX_ATTEMPTS}", flush=True)
            time.sleep(min(60, 5 * attempt))
    if os.path.getsize(tmp) != size:
        raise IOError(f"size mismatch for {rel}")
    os.replace(tmp, dest)


def main():
    opener = make_opener()
    files = list_csvs(opener, ROOT)
    total = sum(size for _, size in files)
    print(f"FLNET2023: {len(files)} CSV files, {total / 1e9:.2f} GB -> {OUT_DIR}")
    # The server throttles each connection (~1 MB/s), so fetch several files
    # at once.
    with ThreadPoolExecutor(max_workers=PARALLEL_DOWNLOADS) as pool:
        jobs = [pool.submit(download, opener, path, size) for path, size in sorted(files)]
        for job in jobs:
            job.result()
    print("Done.")


if __name__ == "__main__":
    main()
