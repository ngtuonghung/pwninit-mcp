import os
import shutil
import tarfile
import tempfile

import requests
import tqdm
import zstandard

import utils


class DebPackage:
    def __init__(self, url, cache_dir=None):
        self.tar = None
        self.tempdir = tempfile.mkdtemp()  # always needed for tar extraction
        self.error = None
        urls = [url] if isinstance(url, str) else list(url)
        debname = urls[0].split("/")[-1]

        # Add fallback URL for ubuntu archive packages if not already present
        if any("archive.ubuntu.com" in u for u in urls):
            lp_fallback = f"https://launchpad.net/ubuntu/+archive/primary/+files/{debname}"
            if lp_fallback not in urls:
                urls.append(lp_fallback)

        # Use cached deb if available (check passed cache_dir first, then global cache)
        candidate_cache_dirs = []
        if cache_dir:
            candidate_cache_dirs.append(cache_dir)
        global_cache = os.path.expanduser("~/.cache/pwninit")
        if global_cache not in candidate_cache_dirs:
            candidate_cache_dirs.append(global_cache)

        for cdir in candidate_cache_dirs:
            try:
                os.makedirs(cdir, exist_ok=True)
                cached_path = os.path.abspath(os.path.join(cdir, debname))
                if os.path.isfile(cached_path):
                    import log as _log
                    _log.info(f"Using cached {debname!r} from {cdir!r}")
                    self.tar = self._get_data_tar(cached_path)
                    return
            except OSError:
                continue

        # Save downloaded deb to primary cache dir or tempdir
        try:
            debpath = os.path.abspath(os.path.join(candidate_cache_dirs[0], debname))
        except Exception:
            debpath = os.path.join(self.tempdir, debname)

        # Download
        resp = None
        for u in urls:
            try:
                r = requests.get(u, stream=True)
                if r.status_code == 200:
                    resp = r
                    break
                else:
                    self.error = f"GET request returned {r.status_code}"
            except Exception as exception:
                self.error = str(exception)
                continue
        if resp is None or resp.status_code != 200:
            return
        total = int(resp.headers.get("Content-Length", 0)) or None
        with open(debpath, "wb+") as f, tqdm.tqdm(
            total=total, unit="B", unit_scale=True, unit_divisor=1024,
            desc=debname, leave=False
        ) as bar:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
                bar.update(len(chunk))
        # extract data.tar from deb to the tempdir
        self.tar = self._get_data_tar(debpath)

    def _extract_file_deb(self, deb, name, folder="."):
        # args = ["x", "--output", folder, deb, name] (binutils >= 2.34)
        _, stderr = utils.run_ar(["x", deb, name], cwd=folder)
        if not stderr:
            return os.path.join(folder, name)
        return None

    def _get_data_tar(self, debpath):
        folder = self.tempdir
        for ext in ("gz", "xz"):
            tar_name = f"data.tar.{ext}"
            tar_path = self._extract_file_deb(debpath, tar_name, folder=folder)
            if tar_path:
                return tarfile.open(tar_path, f"r:{ext}")
        # tarfile doesn't support .zst
        # do it ourselves with zstandard
        tar_zst_name = "data.tar.zst"
        tar_zst_path = self._extract_file_deb(debpath, tar_zst_name, folder=folder)
        if not tar_zst_path:
            self.error = "Failed to find data.tar"
            return None
        dctx = zstandard.ZstdDecompressor()
        tar_path = os.path.join(folder, "data.tar")
        with open(tar_zst_path, "rb") as ifh, open(tar_path, "wb+") as ofh:
            dctx.copy_stream(ifh, ofh)
        return tarfile.open(tar_path, "r:")

    def close(self):
        if self.tar:
            self.tar.close()
            self.tar = None
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
