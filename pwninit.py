#!/usr/bin/python3
import os
import re
import shutil
import tempfile

from elftools.elf.elffile import ELFFile

import config
import deb
import elfutils
import log
import templates
import utils


class LibcVersion:
    def __init__(self, line, arch):
        # line is what comes after "GNU C Library " and is of the form:
        # ([PKGVERSION])? [stable/development] release version X.YZ.
        self.raw = line.strip()
        self.arch = arch

        self.pkgversion = None
        self.release = None
        self.version_string = None
        self.version = None     # tuple of numbers
        # split up pkgversion
        self.flavour = None
        self.pkgname = None

        match = re.match(r"(?:GNU C Library )?(?:\((.+?)\) )?([a-z]+) release version (\d+(?:\.\d+)+)", self.raw)
        if match is None:
            return
        # release = "stable", "development" or "release"
        self.release = match.group(2)
        # Ex. version_string = "2.27", version = (2,27)
        self.version_string = match.group(3)
        self.version = tuple(int(x) for x in self.version_string.split("."))
        # PKGVERSION
        if match.group(1):
            self.pkgversion = match.group(1)
            words = self.pkgversion.split()
            if words[-1].startswith(self.version_string):
                self.pkgname = words.pop(-1)
            self.flavour = " ".join(words)

    @property
    def is_custom(self):
        # default pkgversion is "GNU libc" when compiling
        return self.pkgversion == "GNU libc"

    @property
    def is_stable(self):
        return self.release in ("stable", "release")

    @property
    def os(self):
        if self.pkgversion is None:
            return None
        os = self.pkgversion.split()[0]
        if os in ("Ubuntu", "Debian", "GNU"):
            return os
        return None

    @property
    def is_eglibc(self):
        return "EGLIBC" in self.flavour

    @property
    def is_glibc(self):
        return "GLIBC" in self.flavour and not self.is_eglibc

    @property
    def glibc_type(self):
        if self.is_glibc:
            return "GLIBC"
        if self.is_eglibc:
            return "EGLIBC"
        return None

    @property
    def libc_debname(self):
        if self.pkgname and self.arch:
            return f"libc6_{self.pkgname}_{self.arch}.deb"
        return None

    @property
    def libc_dbg_debname(self):
        # for multiarch ones:
        # e.g. libc6-i386-dbgsym_2.35-0ubuntu3.10_amd64.ddeb
        if self.pkgname and self.arch:
            return f"libc6-dbg_{self.pkgname}_{self.arch}.deb"
        return None

    @property
    def libc_src_debname(self):
        if self.pkgname:
            return f"glibc-source_{self.pkgname}_all.deb"
        return None

    @property
    def base_pkgurl(self):
        if self.os == "Ubuntu":
            # works for both glibc and eglibc
            return "https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/"
        if self.os == "Debian":
            if self.is_glibc:
                return "https://deb.debian.org/debian/pool/main/g/glibc/"
            # for unstable releases:
            # https://deb.sipwise.com/debian/pool/main/g/glibc/
        return None

    def _format_pkgurl(self, debname):
        base = self.base_pkgurl
        if base is None or debname is None:
            return None
        return base + debname

    @property
    def libc_pkgurl(self):
        return self._format_pkgurl(self.libc_debname)

    @property
    def libc_dbg_pkgurl(self):
        urls = []
        if self.libc_dbg_debname:
            main_url = self._format_pkgurl(self.libc_dbg_debname)
            if main_url:
                urls.append(main_url)
        if self.os == "Ubuntu" and self.pkgname and self.arch:
            ddeb_name = f"libc6-dbgsym_{self.pkgname}_{self.arch}.ddeb"
            urls.append(f"http://ddebs.ubuntu.com/pool/main/g/glibc/{ddeb_name}")
            urls.append(f"https://launchpad.net/ubuntu/+archive/primary/+files/{ddeb_name}")
        return urls[0] if len(urls) == 1 else (urls if urls else None)

    @property
    def libc_src_pkgurl(self):
        if self.os == "Ubuntu" and self.libc_src_debname:
            return f"https://archive.ubuntu.com/ubuntu/pool/universe/g/glibc/{self.libc_src_debname}"
        return self._format_pkgurl(self.libc_src_debname)

    @property
    def arch_linux_gnu(self):
        return {
            "amd64": "x86_64-linux-gnu",
            "i386": "i386-linux-gnu",
            "arm64": "aarch64-linux-gnu",
            "armel": "arm-linux-gnueabi",
            "armhf": "arm-linux-gnueabihf",
            "mipsel": "mipsel-linux-gnu",
            "mips64el": "mips64el-linux-gnuabi64",
            "pp64el": "powerpc64le-linux-gnu",
            "s390x": "s390x-linux-gnu",
            "riscv64": "riscv64-linux-gnu",
        }.get(self.arch, None)

    def get_libc6_pkg_paths(self, name):
        arch_gnu = self.arch_linux_gnu or ""
        paths = []
        if arch_gnu:
            paths.append(f"./lib/{arch_gnu}/{name}")
            paths.append(f"./usr/lib/{arch_gnu}/{name}")
        paths.extend([
            f"./lib64/{name}",
            f"./usr/lib64/{name}",
            f"./lib/{name}",
            f"./usr/lib/{name}",
        ])
        return paths
    
    @property
    def supported_architectures(self):
        if self.os == "Ubuntu":
            # supports libc6-armel_armhf not armel
            return ["amd64", "i386", "arm64", "armhf", "ppc64el", "riscv64", "s390x"]
        if self.os == "Debian":
            return ["amd64", "i386", "arm64", "armel", "armhf", "mipsel", "mips64el", "ppc64el", "riscv64", "s390x"]
        return []

    def __str__(self):
        return self.raw


# Library names that ship inside the libc6 (glibc) debian package.
# libcrypto, libssl, libz, etc. are NOT here and must be provided manually.
LIBC6_LIB_NAMES = frozenset({
    "ld", "libc", "libm", "libpthread", "libdl", "libresolv",
    "librt", "libanl", "libutil", "libcrypt", "libBrokenLocale",
    "libthread_db", "libnsl",
})

def is_libc6_lib(lib_name):
    """Return True if lib_name is expected to be part of the libc6 package."""
    return lib_name in LIBC6_LIB_NAMES or lib_name.startswith("libnss_")

# Maps glibc version tuple (major, minor) to Ubuntu / Debian codename.
GLIBC_VERSION_TO_CODENAME = {
    (2, 17): "saucy",
    (2, 19): "trusty",
    (2, 21): "vivid",
    (2, 23): "xenial",
    (2, 24): "stretch",  # Debian
    (2, 26): "artful",
    (2, 27): "bionic",
    (2, 28): "focal",    # or buster for Debian
    (2, 29): "disco",
    (2, 30): "eoan",
    (2, 31): "focal",
    (2, 32): "groovy",
    (2, 33): "hirsute",
    (2, 34): "impish",
    (2, 35): "jammy",
    (2, 36): "kinetic",  # or bookworm for Debian
    (2, 37): "lunar",
    (2, 38): "mantic",
    (2, 39): "noble",
    (2, 40): "oracular", # or trixie for Debian
    (2, 41): "plucky",
    (2, 42): "questy",
    (2, 43): "resolute",
}

# Maps lib name (from get_lib_name()) to Ubuntu package name that ships it.
# The value is a list of candidate package names to try, in order.
EXTERNAL_LIB_TO_PACKAGE = {
    # libcrypto.so.1.1 and libssl.so.1.1 come from libssl1.1
    # libcrypto.so.3 and libssl.so.3 come from libssl3
    # libcrypto.so.1.0.0 and libssl.so.1.0.0 come from libssl1.0.0
    "libcrypto":  ["libssl3", "libssl1.1", "libssl1.0.0"],
    "libssl":     ["libssl3", "libssl1.1", "libssl1.0.0"],
    "libseccomp": ["libseccomp2"],
    "libcap":     ["libcap2"],
    "libffi":     ["libffi8", "libffi7", "libffi6"],
    "libsqlite3": ["libsqlite3-0"],
    "libcurl":    ["libcurl4", "libcurl3-gnutls", "libcurl3"],
    "libevent":   ["libevent-2.1-7", "libevent-2.1-6"],
    "libprotobuf":["libprotobuf32", "libprotobuf23", "libprotobuf17", "libprotobuf10", "libprotobuf-c1"],
    "libbsd":     ["libbsd0"],
    "libjansson": ["libjansson4"],
    "libyaml":    ["libyaml-0-2"],
    "libmsgpack": ["libmsgpack-c2", "libmsgpackc2"],
    "libuv":      ["libuv1"],
    "libz":       ["zlib1g"],
    "libgmp":     ["libgmp10"],
    "libgcc_s":   ["libgcc-s1", "libgcc1"],
    "libstdc++":  ["libstdc++6"],
}

# Directory where downloaded .deb packages are cached to avoid re-downloading.
# Default to global ~/.cache/pwninit with fallback to local ./lib
def get_deb_cache_dir():
    global_cache = os.path.expanduser("~/.cache/pwninit")
    try:
        os.makedirs(global_cache, exist_ok=True)
        return global_cache
    except OSError:
        return "lib"

DEB_CACHE_DIR = get_deb_cache_dir()


# takes the form: libname.so.XXX, libname.so, libname-2.27.so, libname_2.27.so
# also accepts: libcXXX, ld-XXX, ld
def query_launchpad_pkg_url(pkgname, codename, arch):
    """Query the Launchpad REST API to get the latest .deb download URL."""
    import requests as _requests
    api = "https://api.launchpad.net/devel"
    headers = {"Accept": "application/json"}
    try:
        r = _requests.get(
            f"{api}/ubuntu/+archive/primary",
            params={
                "ws.op": "getPublishedBinaries",
                "binary_name": pkgname,
                # must be a full absolute URL, not a relative path
                "distro_arch_series": f"{api}/ubuntu/{codename}/{arch}",
                "status": "Published",
                "ordered_by_date": "true",  # correct param; ws.orderby causes 400
                "ws.size": "1",
            },
            headers=headers,
            timeout=20,
        )
        r.raise_for_status()
        entries = r.json().get("entries", [])
    except Exception as e:
        return None, str(e)
    if not entries:
        return None, f"No published binary for {pkgname!r} in {codename}/{arch}"
    self_link = entries[0]["self_link"]
    try:
        r2 = _requests.get(
            self_link,
            params={"ws.op": "binaryFileUrls"},
            headers=headers,
            timeout=20,
        )
        r2.raise_for_status()
        urls = r2.json()
    except Exception as e:
        return None, str(e)
    for u in urls:
        if isinstance(u, str) and u.endswith(".deb"):
            return u, None
    return None, f"No .deb URL in binaryFileUrls for {pkgname!r}"


def extract_from_deb(url, pkg_paths, dst_filename, cache_dir=None):
    """Download (or use cached) deb and extract a single file from it.
    pkg_paths: list of in-archive paths to try in order.
    Returns True on success, False on failure."""
    with deb.DebPackage(url, cache_dir=cache_dir) as pkg:
        tar = pkg.tar
        if tar is None:
            log.error(f"Failed to open package: {pkg.error!r}")
            return False
        for path in pkg_paths:
            try:
                fsrc = tar.extractfile(path)
                if fsrc is None:
                    continue
                log.info(f"Extracting {path!r} -> {dst_filename!r}")
                with open(dst_filename, "wb+") as fdst, fsrc:
                    shutil.copyfileobj(fsrc, fdst)
                return True
            except KeyError:
                log.info(f"Path {path!r} not found in archive, trying next")
                continue
    log.error(f"None of the candidate paths were found in the archive for {dst_filename!r}")
    return False


def fetch_lib_libc6(needed_lib, version, cache_dir=None):
    """Fetch a single libc6 library from the libc6 deb. Returns local filename or None."""
    if version is None:
        log.warning(f"Skipping fetch of {needed_lib!r}: libc version is unknown")
        return None
    if not version.pkgname:
        log.warning(f"Skipping fetch of {needed_lib!r}: libc package name not available")
        return None
    if version.arch not in version.supported_architectures:
        log.warning(f"Skipping fetch of {needed_lib!r}: arch {version.arch!r} not supported for {version.os!r}")
        return None
    name = os.path.basename(needed_lib)
    pkg_paths = version.get_libc6_pkg_paths(name)
    url = version.libc_pkgurl
    log.info(f"Fetching {name!r} from libc6 package: {url}")
    log.info(f"  Trying archive paths: {pkg_paths}")
    if extract_from_deb(url, pkg_paths, name, cache_dir=cache_dir):
        log.success(f"Successfully fetched {name!r}")
        return name
    log.error(f"Failed to fetch {name!r} from libc6")
    return None


def fetch_lib_external(needed_lib, lib_name, version, cache_dir=None):
    """Fetch a non-libc6 library from its matching Ubuntu package via Launchpad.
    Returns local filename on success, None on failure."""
    if version is None or not version.version:
        return None
    codename = GLIBC_VERSION_TO_CODENAME.get(version.version[:2])
    if codename is None:
        return None
    ubuntu_arch = version.arch
    candidate_pkgs = EXTERNAL_LIB_TO_PACKAGE.get(lib_name)
    if not candidate_pkgs:
        return None
    lib_filename = os.path.basename(needed_lib)
    arch_linux_gnu = version.arch_linux_gnu
    paths = []
    if arch_linux_gnu:
        paths += [
            f"./usr/lib/{arch_linux_gnu}/{lib_filename}",
            f"./lib/{arch_linux_gnu}/{lib_filename}",
        ]
    paths += [f"./usr/lib/{lib_filename}", f"./lib/{lib_filename}"]
    for pkgname in candidate_pkgs:
        deb_url, err = query_launchpad_pkg_url(pkgname, codename, ubuntu_arch)
        if deb_url is None:
            log.warning(f"Launchpad query for {pkgname!r} ({codename}/{ubuntu_arch}) failed: {err}")
            continue
        print()
        log.info(f"Fetching {lib_filename!r} from {deb_url}")
        if extract_from_deb(deb_url, paths, lib_filename, cache_dir=cache_dir):
            log.success(f"Successfully fetched {lib_filename!r}")
            return lib_filename
        log.warning(f"Couldn't find {lib_filename!r} in package {pkgname!r}")
    log.error(f"Could not fetch {lib_filename!r}: tried {candidate_pkgs} on {codename}/{ubuntu_arch}")
    return None


def resolve_lib(needed_lib, version, libraries, cache_dir, visited, failed):
    """Recursively resolve a single library and all its transitive dependencies.
    Fetches missing libs, then recurses into their NEEDED entries.
    Updates `libraries` in place. Returns local path or None.
    Unresolvable libs are added to `failed` (a set)."""
    lib_name = get_lib_name(needed_lib)
    if lib_name in visited:
        existing = libraries.get(lib_name)
        if existing:
            log.info(f"Already resolved {needed_lib!r} -> {existing!r}, skipping")
        else:
            log.info(f"Already attempted {needed_lib!r} (previously failed), skipping")
        return existing
    visited.add(lib_name)

    log.info(f"Resolving {needed_lib!r} (lib_name={lib_name!r})")

    # Already have it?
    local_path = libraries.get(lib_name)
    if local_path is not None:
        log.info(f"  Already in libraries: {local_path!r}")
    else:
        # Check if user placed it in the current directory
        local_candidate = os.path.join(".", os.path.basename(needed_lib))
        if os.path.isfile(local_candidate) and elfutils.is_elf(local_candidate):
            log.info(f"  Found locally at {local_candidate!r}")
            local_path = local_candidate
        elif is_libc6_lib(lib_name):
            log.info(f"  Identified as libc6 library, fetching from libc6 deb")
            local_path = fetch_lib_libc6(needed_lib, version, cache_dir=cache_dir)
            if local_path:
                utils.chmod_x(local_path)
        else:
            log.info(f"  Identified as external library, fetching from Ubuntu package")
            local_path = fetch_lib_external(needed_lib, lib_name, version, cache_dir=cache_dir)
            if local_path:
                utils.chmod_x(local_path)

    if local_path is None:
        log.error(f"  Failed to resolve {needed_lib!r}")
        failed.add(needed_lib)
        return None

    libraries[lib_name] = local_path
    log.info(f"  Resolved {needed_lib!r} -> {local_path!r}")

    # Recurse into this library's own NEEDED entries
    try:
        with open(local_path, "rb") as f:
            elf = ELFFile(f)
            dyn = elfutils.get_dynamic(elf)
            if dyn:
                transitive = elfutils.get_needed_from_dynamic(dyn)
                if transitive:
                    log.info(f"  {local_path!r} needs: {transitive}")
                for transitive_lib in transitive:
                    resolve_lib(transitive_lib, version, libraries, cache_dir, visited, failed)
    except Exception as e:
        log.warning(f"  Could not read NEEDED entries from {local_path!r}: {e}")

    return local_path


def resolve_all_deps(initial_needed, requested_linker, libraries, version, cache_dir):
    """Recursively resolve all shared library dependencies starting from the
    binary's NEEDED list. Fetches missing libs, recurses into their deps,
    then patches all external libs so their NEEDED entries point to local copies."""
    os.makedirs(cache_dir, exist_ok=True)
    # Seed visited with libs we already have so we don't re-process them
    visited = set(libraries.keys())
    failed = set()  # all unresolvable libs (at any depth)

    all_needed = list(initial_needed)
    if requested_linker and get_lib_name(requested_linker) not in visited:
        all_needed.append(requested_linker)

    log.info(f"Libraries already present: {list(libraries.keys()) or 'none'}")
    log.info(f"Direct NEEDED entries to resolve: {all_needed}")

    direct_failed = []
    for needed_lib in all_needed:
        lib_name = get_lib_name(needed_lib)
        if lib_name in visited:
            log.info(f"Skipping {needed_lib!r}: already provided")
            continue
        result = resolve_lib(needed_lib, version, libraries, cache_dir, visited, failed)
        if result is None:
            direct_failed.append(needed_lib)

    log.info(f"Resolved libraries: {list(libraries.keys())}")

    # Transitive failures: warn but don't fatal — user can place them manually
    transitive_failed = failed - set(direct_failed)
    if transitive_failed:
        print()
        log.warning("Could not automatically fetch some transitive dependencies:")
        for lib in sorted(transitive_failed):
            local_path = os.path.join(".", os.path.basename(lib))
            log.warning(f"  {lib!r} -> place manually at {local_path!r} and re-run")

    # Direct binary deps failing is fatal
    if direct_failed:
        print()
        log.error("Could not automatically fetch the following required libraries:")
        for lib in direct_failed:
            local_path = os.path.join(".", os.path.basename(lib))
            log.error(f"  {lib!r} -> please place it manually at {local_path!r}")
        log.fatal("Provide the missing libraries and re-run pwninit")

    # Patch external libs (e.g. libcrypto) so their transitive NEEDED entries
    # resolve to local copies instead of system libs
    external_libs = [(n, p) for n, p in libraries.items() if not is_libc6_lib(n)]
    if external_libs:
        print()
        log.info(f"Patching NEEDED entries in {len(external_libs)} external lib(s): {[p for _, p in external_libs]}")
        for lib_name, lib_path in external_libs:
            log.info(f"Patching transitive deps in {lib_path!r}")
            patch_binary(lib_path, libraries, output=lib_path)


def get_lib_name(lib, strict=False):
    basename = os.path.basename(lib)
    # ld names are more complex than other libraries
    if basename.startswith("ld-") or basename == "ld":
        return "ld"
    # this is for greater compatibility with pwninit libc detection
    if basename.startswith("libc") and not basename[4:5].isalpha():
        return "libc"
    match = re.match(r"(.+?)(?:[-_]\d+\.\d+)?\.so", basename)
    if not match:
        if strict:
            return None
        return basename
    name = match.group(1)
    #if strict and not name.startswith("lib"):
    #    return None
    return name

def is_patched(file):
    if not config.PATCHED_BINARY_SUFFIX:
        return False
    return file.endswith(config.PATCHED_BINARY_SUFFIX)

def replace_link(old, new):
    return os.path.islink(old) and not os.path.islink(new)

def find_binaries(binary=None, libc=None, ld=None, folder=".", libraries=None):
    if libraries is None:
        libraries = {}
    if ld:
        libraries["ld"] = ld
    if libc:
        libraries["libc"] = libc
    binary_provided = binary is not None
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if not elfutils.is_elf(path):
            continue
        # check if file is a library
        lib_name = get_lib_name(filename, strict=True)
        if lib_name is None:
            if binary_provided:
                continue
            # if the current binary:
            # * hasn't been found
            # * was already patched
            # * is a symlink
            # see if we can replace it
            if binary is None or is_patched(binary) or replace_link(binary, path):
                # ensure that this isn't a file we know about already
                # (samefile() returns true for a file and symlink to the file)
                for path2 in libraries.values():
                    if os.path.samefile(path, path2):
                        break
                else:
                    binary = path
            continue
        # if ld or libc were supplied, never overwrite them
        # or add any other libcs or lds
        # and by extension check for duplicates
        # since we know which one to use
        if lib_name == "ld" and ld is not None:
            continue
        elif lib_name == "libc" and libc is not None:
            continue
        # check duplicate
        path2 = libraries.get(lib_name, None)
        if path2:
            if replace_link(path2, path):
                # prioritise non-symlink files
                libraries[lib_name] = path
                path, path2 = path2, path
            log.warning(f"Duplicate libraries {path!r} and {path2!r}, defaulting to {path2!r}")
            continue
        libraries[lib_name] = path
    return binary, libraries


def fetch_missing_libraries(missing, libraries, version, cache_dir=None):
    """Batch-fetch multiple libc6 libraries from the libc6 deb in one pass.
    Uses cache_dir to avoid re-downloading the deb."""
    missing_list = ', '.join(repr(m) for m in missing)
    if version is None:
        log.error(f"Can't fetch {missing_list} without knowing the libc version")
        return False
    if version.arch not in version.supported_architectures:
        log.error(f"Architecture {version.arch!r} not supported by {version.os!r}")
        return False
    if not version.pkgname:
        log.error(f"Can't fetch {missing_list} as libc doesn't have a package name")
        return False
    dsts = []
    for i, needed_lib in enumerate(missing):
        name = os.path.basename(needed_lib)
        missing[i] = version.get_libc6_pkg_paths(name)
        dsts.append(name)
    url = version.libc_pkgurl
    print()
    dsts_list = ', '.join(repr(d) for d in dsts)
    log.info(f"Fetching {dsts_list} from {url}")
    successes = []
    with deb.DebPackage(url, cache_dir=cache_dir) as pkg:
        tar = pkg.tar
        if tar is None:
            log.error(f"Failed to fetch files: {pkg.error!r}")
            return False
        for files, dst in zip(missing, dsts):
            fsrc = None
            for file in files:
                try:
                    fsrc = tar.extractfile(file)
                    break
                except KeyError:
                    pass
            else:
                log.error(f"Failed to fetch {dst!r}")
                continue
            with open(dst, "wb+") as fdst, fsrc:
                shutil.copyfileobj(fsrc, fdst)
            successes.append(dst)
            log.success(f"Successfully fetched {dst!r}")
    for lib in successes:
        libraries[get_lib_name(lib)] = lib
    return len(dsts) == len(successes)


def get_stripped_libraries(libraries):
    unstrip_libs = []
    for lib in libraries.values():
        with open(lib, "rb") as f:
            elf = ELFFile(f)
            if elf.get_dwarf_info().has_debug_info:
                continue
            out = elfutils.get_debug_link(elf)
            if out is None:
                log.error(f"Couldn't find .debug_link in {lib!r}, skipping")
                continue
            debug_link, crc32 = out
            unstrip_libs.append((lib, debug_link, crc32))
    return unstrip_libs


def unstrip_libraries(libraries, version, cache_dir=None):
    tempdir = tempfile.mkdtemp()
    debug_syms = {}
    url = version.libc_dbg_pkgurl
    log.info(f"Fetching debug symbols from {url}")
    with deb.DebPackage(url, cache_dir=cache_dir) as pkg:
        tar = pkg.tar
        if tar is None:
            log.error(f"Failed to fetch files: {pkg.error!r}")
            shutil.rmtree(tempdir)
            return False
        for name in tar.getnames():
            basename = os.path.basename(name)
            for lib, debug_link, crc32 in libraries:
                if debug_link != basename:
                    continue
                fileobj = tar.extractfile(name)
                if utils.crc32_fileobj(fileobj) != crc32:
                    continue
                fileobj.seek(0)
                debug_sym = os.path.join(tempdir, basename)
                with open(debug_sym, "wb+") as f, fileobj:
                    shutil.copyfileobj(fileobj, f)
                debug_syms[lib] = debug_sym
                break
    for lib, _, _ in libraries:
        debug_sym = debug_syms.get(lib, None)
        if debug_sym:
            # NOTE: it's also possible to keep the debug symbols separate
            # and in gdb change the directory where debug symbols are loaded from
            # if you wanted to keep the libraries unpatched
            # however unlike patchelf, it seems that the new sections added
            # aren't loaded into memory, and so don't affect how it's loaded
            _, stderr = utils.run_eu_unstrip(lib, debug_sym, output=lib)
            if not stderr:
                log.success(f"Successfully unstripped {lib!r}")
            else:
                log.error(f"Failed to unstrip {lib!r}: {stderr!r}")
        else:
            log.error(f"Failed to get debug symbols for {lib!r}")
    shutil.rmtree(tempdir)
    return True


def patch_binary(path, libraries, output=None, dont_patch=None):
    if dont_patch is None:
        dont_patch = set()
    patches = []
    with open(path, "rb") as f:
        elf = ELFFile(f)
        interp_patch = elfutils.get_interp_patch(elf)
        if interp_patch is not None:
            patches.append(interp_patch)
        patches += elfutils.get_needed_patches(elf)

    with open(path, "rb") as f:
        contents = bytearray(f.read())

    successful_patches = 0
    for needed, i in patches:
        if needed in dont_patch:
            log.warning(f"{needed!r} already fulfilled, skipping")
            continue
        lib_name = get_lib_name(needed)
        if lib_name not in libraries:
            log.error(f"Couldn't find library for {needed!r}, skipping")
            continue
        symlink = "./" + lib_name
        if len(needed) < len(symlink):
            log.error(f"Patch {symlink!r} is longer than the existing needed library {needed!r}, skipping")
            continue
        patch = symlink.encode() + b"\x00"
        contents[i:i+len(patch)] = patch
        target = libraries[lib_name]
        if os.path.abspath(symlink) != os.path.abspath(target):
            log.info(f"Symlinking {symlink!r} -> {target!r}")
            try:
                os.symlink(target, symlink)
            except FileExistsError:
                log.warning(f"{symlink!r} already exists, skipping")
            except OSError as exception:
                log.error(f"Failed to make symlink: {exception!r}")
        successful_patches += 1
    # if no patches were made, no point creating a new binary
    if successful_patches == 0:
        log.warning(f"No patches were made, using original binary {path!r}")
        return path
    if output is None:
        output = path + config.PATCHED_BINARY_SUFFIX
    with open(output, "wb+") as f:
        f.write(bytes(contents))
    missing_patches = len(patches) - successful_patches
    if missing_patches == 0:
        log.success(f"Successfully wrote patched binary to {output!r}")
    else:
        word = "patch"
        if missing_patches > 1:
            word += "es"
        log.warning(f"Wrote patched binary to {output!r}, with {missing_patches} missing {word}")
    return output


def patch_binary_patchelf(path, libraries, output=None, dont_patch=None):
    if dont_patch is None:
        dont_patch = set()
    if output is None:
        output = path + config.PATCHED_BINARY_SUFFIX
    with open(path, "rb") as f:
        elf = ELFFile(f)
        needed = elfutils.get_needed(elf)
        requested_linker = elfutils.get_interp(elf)
    number_of_patches = len(needed)
    successful_patches = 0
    # if outputting to a different file, make a copy
    if not os.path.exists(output) or not os.path.samefile(path, output):
        shutil.copyfile(path, output)
    ld = libraries.get("ld", None)
    if ld:
        if requested_linker not in dont_patch:
            number_of_patches += 1
            ld = utils.basename_to_relpath(ld)
            _, stderr = utils.run_patchelf(output, ["--set-interpreter", ld])
            if stderr:
                log.error(f"Failed to patch interpreter: {stderr!r}")
            else:
                successful_patches += 1
        else:
            log.warning(f"{requested_linker!r} already fulfilled, skipping")
    for lib in needed:
        if lib in dont_patch:
            log.warning(f"{lib!r} already fulfilled, skipping")
            continue
        lib_name = get_lib_name(lib)
        if lib_name not in libraries:
            log.error(f"Couldn't find library for {lib!r}, skipping")
            continue
        patch = utils.basename_to_relpath(libraries[lib_name])
        _, stderr = utils.run_patchelf(output, ["--replace-needed", lib, patch])
        if stderr:
            log.error(f"Failed to replace {lib!r} with {patch!r}: {stderr!r}")
        else:
            successful_patches += 1

    # Set RPATH to ensure libraries in binary/current directory are resolved
    _, rpath_err = utils.run_patchelf(output, ["--set-rpath", "$ORIGIN:."])
    if rpath_err:
        log.warning(f"Could not set RPATH: {rpath_err!r}")
    else:
        log.info("Set RPATH to '$ORIGIN:.'")

    missing_patches = number_of_patches - successful_patches
    if successful_patches == 0:
        log.warning(f"No patches were made")
    elif missing_patches == 0:
        log.success(f"Successfully wrote patched binary to {output!r}")
    else:
        word = "patch"
        if missing_patches > 1:
            word += "es"
        log.warning(f"Wrote patched binary to {output!r}, with {missing_patches} missing {word}")
    return output


def write_solvepy(binary, libraries, template=None):
    if template is None:
        template = config.DEFAULT_TEMPLATE
    script = templates.get_template(template)
    if script is None:
        log.error("Failed to get template")
        return False
    bindings = []
    binary_name = config.TEMPLATE_BINARY_NAME
    bindings.append(f"{binary_name} = context.binary = ELF({binary!r}, checksec=False)")
    # these may not exist if the binary is static
    libc = libraries.get("libc", None)
    ld = libraries.get("ld", None)
    if libc:
        libc_name = config.TEMPLATE_LIBC_NAME
        bindings.append(f"{libc_name} = ELF({libc!r}, checksec=False)")
    if ld:
        ld_name = config.TEMPLATE_LD_NAME
        bindings.append(f"{ld_name} = ELF({ld!r}, checksec=False)")
    with open("solve.py", "w+") as f:
        f.write(script.format(bindings="\n".join(bindings)))
    utils.chmod_x("solve.py")
    log.success("Successfully written solve.py")
    return True


def get_libc_version(libc, arch=None):
    try:
        f = open(libc, "rb")
    except OSError as exception:
        log.fatal(f"Can't open libc for reading: {exception!r}")

    with f:
        for line in f:
            parts = line.split(b"GNU C Library ", 1)
            if len(parts) == 2:
                # Safely split on null byte or newline and decode with error replacement
                raw_str = parts[1].split(b"\x00")[0].split(b"\n")[0].decode("utf-8", errors="ignore")
                version = LibcVersion(raw_str, arch)
                if version.version_string is not None:
                    log.info(f"libc version: {version}")
                    if version.is_custom:
                        # pkgname is None here as well
                        # but the reason for it here is custom compilation
                        log.warning("Libc appears to be custom-compiled")
                    elif version.pkgname is None:
                        log.warning("Name of package not present in libc version string")
                    return version
    log.error("Failed to find libc version")
    return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
        description=("Automates the initialization of a pwn challenge.\n"
            f"The config.py file is located at {config.__file__}"))
    ap.add_argument("-b", "--bin", default=None, dest="binary",
        help="Path of binary to patch")
    ap.add_argument("--libc", default=None, dest="libc",
        help="Path of libc")
    ap.add_argument("--ld", default=None, dest="ld",
        help="Path of interpreter")
    ap.add_argument("-nu", "--no-unstrip", default=False, action="store_true",
        help="Disable unstripping of libraries (ignored if binary is static)")
    ap.add_argument("-np", "--no-patch", default=False, action="store_true",
        help="Disable patching of binary (ignored if binary is static)")
    ap.add_argument("-ns", "--no-solvepy", default=False, action="store_true",
        help="Disable writing solve.py")
    ap.add_argument("--use-patchelf", default=config.USE_PATCHELF,
        action="store_true",
        help="Use patchelf for patching the binary")
    ap.add_argument("-l", "--libs", default=None, dest="libs",
        help="Path of folder to store libraries in (ignored if binary is static)")
    ap.add_argument("-t", "--template", default=config.DEFAULT_TEMPLATE,
        dest="template", choices=templates.get_available_templates(),
        help=("Template of solve script. "
            f"Templates are stored in {templates.get_templates_folder()}"))
    ap.add_argument("-o", "--output", default=None, dest="output",
        help=("Place patched binary into OUTPUT "
            f"(defaults to BINARY{config.PATCHED_BINARY_SUFFIX})"))

    args = ap.parse_args()
    do_unstrip = not args.no_unstrip
    do_patch = not args.no_patch
    do_solvepy = not args.no_solvepy
    binary, libraries = find_binaries(binary=args.binary, libc=args.libc, ld=args.ld)
    if binary is None:
        log.fatal("No binary was supplied or found!")
    with open(binary, "rb") as f:
        elf = ELFFile(f)
        arch = elfutils.get_arch(elf)
        requested_linker = elfutils.get_interp(elf)
        dynamic = elfutils.get_dynamic(elf)
        log.info(f"bin: {binary} ({arch = })")
        if dynamic:
            needed = elfutils.get_needed_from_dynamic(dynamic)
            runpath = elfutils.get_runpath_from_dynamic(dynamic)
            if runpath:
                log.info(f"RUNPATH: {runpath}")
            runpath_libs = {}
            for path in runpath:
                if not os.path.isdir(path):
                    continue
                find_binaries(binary=binary, folder=path, libraries=runpath_libs)
            dont_patch = set()
            for needed_lib in needed:
                lib_name = get_lib_name(needed_lib)
                if not utils.is_basename(needed_lib) and elfutils.is_elf(needed_lib):
                    dont_patch.add(needed_lib)
                    libraries[lib_name] = needed_lib
                if utils.is_basename(needed_lib) and lib_name in runpath_libs:
                    dont_patch.add(needed_lib)
            # check if this exists?
            if requested_linker and not os.path.isabs(requested_linker) and elfutils.is_elf(requested_linker):
                # normally an absolute path, so this means it's definitely patched
                dont_patch.add(requested_linker)
                libraries["ld"] = requested_linker
            #if not any(lambda x: requested_linker.startswith(x), ["/lib/", "/lib64/"]):
            #    dont_patch.add(requested_linker)
            libraries = runpath_libs | libraries

    if dynamic is None:
        libraries = {}
        do_patch = False
        log.warning("Binary is statically linked, not patching the binary")
    elif not libraries:
        do_patch = False
        log.warning("No libraries were found, not patching the binary")
    elif libraries.get("libc", None):
        libc = libraries["libc"]
        log.info(f"libc: {libc}")
        if arch == "arm":
            # Determine armhf vs armel using e_flags in ELF header
            try:
                with open(libc, "rb") as f_libc:
                    libc_elf = ELFFile(f_libc)
                    e_flags = libc_elf.header.get("e_flags", 0)
                    # EF_ARM_ABI_FLOAT_HARD = 0x400
                    if e_flags & 0x400:
                        arch = "armhf"
                    else:
                        arch = "armel"
                log.info(f"Refined arm architecture to {arch!r} from libc e_flags")
            except Exception as e:
                log.warning(f"Could not refine arm architecture from libc: {e}")
        version = get_libc_version(libc, arch=arch)

        print()
        log.info(f"Resolving library dependencies recursively (cache: {DEB_CACHE_DIR!r})...")
        resolve_all_deps(needed, requested_linker, libraries, version, DEB_CACHE_DIR)

        # it's possible that fetching the interpreter failed
        ld = libraries.get("ld", None)
        if ld is None:
            log.error("Interpreter not found")
        else:
            log.info(f"ld: {ld}")
            try:
                open(ld, "rb").close()
                utils.chmod_x(ld)
            except OSError as exception:
                log.error(f"Can't open {ld!r}: {exception!r}")

        if do_unstrip and version and version.pkgname and arch in version.supported_architectures:
            print()
            log.info("Finding stripped libraries to unstrip")
            unstrip_libs = get_stripped_libraries(libraries)
            if unstrip_libs:
                unstrip_libs_list = ', '.join(map(lambda x: repr(x[0]), unstrip_libs))
                log.info(f"Unstripping {unstrip_libs_list}")
                unstrip_libraries(unstrip_libs, version, cache_dir=DEB_CACHE_DIR)
            else:
                log.warning("No libraries to unstrip")

        if args.libs:
            folder = args.libs
            exception = None
            print()
            log.info(f"Moving libraries to {folder!r}")
            try:
                os.mkdir(folder)
            except OSError as e:
                # don't print error here because it could error
                # due to the folder already existing
                exception = str(e)

            if os.path.isdir(folder):
                for name, lib in list(libraries.items()):
                    src = lib
                    dst = os.path.join(folder, os.path.basename(lib))
                    try:
                        shutil.move(src, dst)
                        libraries[name] = dst
                    except OSError as exception:
                        log.error(f"Failed to move {src} to {dst}: {str(exception)!r}")
            else:
                log.error(f"Failed to create folder {folder!r}: {exception!r}")

    if do_patch:
        print()
        if args.use_patchelf:
            log.info("Patching binary using patchelf")
            binary = patch_binary_patchelf(binary, libraries, output=args.output, dont_patch=dont_patch)
        else:
            log.info("Patching binary manually")
            binary = patch_binary(binary, libraries, output=args.output, dont_patch=dont_patch)

    utils.chmod_x(binary)
    if do_solvepy:
        print()
        log.info("Writing solve.py")
        try:
            open("solve.py", "r").close()
            log.warning("solve.py already exists")
        except OSError:
            write_solvepy(binary, libraries, template=args.template)
