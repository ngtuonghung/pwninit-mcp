# pwninit.py

Python tool to automate CTF pwn challenge setup, based on [pwninit](https://github.com/io12/pwninit).

## Features

- Downloads matching dynamic linkers (`ld.so`) and required libraries (`libpthread`, `libm`, etc.).
- Resolves library dependencies, including non-libc6 packages like `libcrypto`, `libssl`, `libseccomp`, `libcap`, and `libz`.
- Downloads debug symbols and unstrips libraries.
- Caches `.deb` archives in `~/.cache/pwninit/` and `./lib/`.
- Patches binaries with local library paths using direct byte replacement or `patchelf`.
- Generates exploit scripts (`solve.py`) from customizable templates.
- Fetches and extracts glibc source code via `pwnsrc.py` for source-level debugging in GDB.
- Supports Ubuntu and Debian glibc packages.

## Installation

Run the setup script:

```bash
./setup.sh
```

The script installs `binutils`, `elfutils`, and `patchelf`, creates a virtual environment at `.venv/`, installs Python requirements, creates `~/.cache/pwninit/`, and registers a `pwninit` alias in `~/.bashrc`.

Requires Python 3.10+.

## Usage

### pwninit.py

Run `pwninit.py` in the directory containing the target binary and libc:

```bash
pwninit
```

Specify inputs directly if needed:

```bash
pwninit --bin ./chall --libc ./libc.so.6 --ld ./ld-linux-x86-64.so.2
```

Options:
- `-b, --bin <file>`: Binary to patch.
- `--libc <file>`: Target libc.
- `--ld <file>`: Target interpreter.
- `-nu, --no-unstrip`: Skip unstripping debug symbols.
- `-np, --no-patch`: Skip patching the binary.
- `-ns, --no-solvepy`: Skip writing `solve.py`.
- `--use-patchelf`: Patch using `patchelf` instead of direct byte replacement.
- `-l, --libs <dir>`: Directory to store resolved libraries.
- `-t, --template <name>`: Template for `solve.py` (`default` or `static`).
- `-o, --output <file>`: Output path for patched binary (defaults to `<bin>_patched`).

### pwnsrc.py

Download and extract glibc source files for GDB source stepping:

```bash
# Download glibc source archive for the local libc
python3 pwnsrc.py

# Extract specific source files
python3 pwnsrc.py --files malloc.c
python3 pwnsrc.py --files glibc-2.31/malloc/malloc.c
```

### Solve Script Templates

Select templates with `-t <template_name>`. The tool loads templates from `templates/`:
- `default`: Pwntools template with terminal auto-detection, local/remote connectors, memory limit guards, and GDB attach logic.
- `static`: Minimal template for statically linked binaries.

Templates replace `{bindings}` with ELF initializers for the binary, libc, and loader.

### Configuration

Edit `config.py` to change defaults:
- `TEMPLATE_BINARY_NAME`: Variable name for binary in `solve.py` (default: `e`).
- `TEMPLATE_LIBC_NAME`: Variable name for libc (default: `libc`).
- `TEMPLATE_LD_NAME`: Variable name for loader (default: `ld`).
- `DEFAULT_TEMPLATE`: Default template (default: `default`).
- `USE_PATCHELF`: Set `True` to use `patchelf` by default.

### Patching Methods

`pwninit.py` provides two patching methods:

1. **Direct byte replacement (default)**: Overwrites `PT_INTERP` and `DT_NEEDED` entries in the ELF string table with shorter relative symlink paths (`./ld`, `./libc`). This preserves original section offsets and file layout.
2. **Patchelf (`--use-patchelf`)**: Uses `patchelf` to set the interpreter, replace library names, and inject `$ORIGIN:.` into `DT_RPATH`.

## Examples

### Initializing a standard challenge

```bash
$ ls
chall  libc.so.6
$ readelf -Wd ./chall | grep NEEDED
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libpthread.so.0]
$ pwninit
[*] bin: chall (arch = 'amd64')
[*] libc: libc.so.6
[*] libc version: (Ubuntu GLIBC 2.31-0ubuntu9.2) stable release version 2.31.

[*] Resolving library dependencies recursively (cache: '/home/user/.cache/pwninit')...
[*] Fetching 'libpthread.so.0' from https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/libc6_2.31-0ubuntu9.2_amd64.deb
[+] Successfully fetched 'libpthread.so.0'
[*] Fetching 'ld-linux-x86-64.so.2' from https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/libc6_2.31-0ubuntu9.2_amd64.deb (cached)
[+] Successfully fetched 'ld-linux-x86-64.so.2'

[*] Finding stripped libraries to unstrip
[*] Unstripping 'libc.so.6', 'libpthread.so.0', 'ld-linux-x86-64.so.2'
[*] Fetching debug symbols from https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/libc6-dbg_2.31-0ubuntu9.2_amd64.deb
[+] Successfully unstripped 'libc.so.6'
[+] Successfully unstripped 'libpthread.so.0'
[+] Successfully unstripped 'ld-linux-x86-64.so.2'

[*] Patching binary manually
[*] Symlinking './ld' -> 'ld-linux-x86-64.so.2'
[*] Symlinking './libc' -> 'libc.so.6'
[*] Symlinking './libpthread' -> 'libpthread.so.0'
[+] Successfully wrote patched binary to 'chall_patched'

[*] Writing solve.py
[+] Successfully written solve.py
$ ls
chall  chall_patched  ld  ld-linux-x86-64.so.2  libc  libc.so.6  libpthread  libpthread.so.0  solve.py
```

### Challenge requiring OpenSSL (`libcrypto.so.1.1`)

```bash
$ ls
chall  libc.so.6
$ readelf -Wd ./chall | grep NEEDED
 0x0000000000000001 (NEEDED)             Shared library: [libcrypto.so.1.1]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
$ pwninit
[*] bin: chall (arch = 'amd64')
[*] libc: libc.so.6
[*] libc version: (Ubuntu GLIBC 2.27-3ubuntu1) stable release version 2.27.

[*] Resolving library dependencies recursively (cache: '/home/user/.cache/pwninit')...

[*] Fetching 'libcrypto.so.1.1' from https://launchpadlibrarian.net/.../libssl1.1_1.1.1-1ubuntu2.1~18.04.23_amd64.deb
[+] Successfully fetched 'libcrypto.so.1.1'
[*] Fetching 'libdl.so.2' from https://archive.ubuntu.com/.../libc6_2.27-3ubuntu1_amd64.deb
[+] Successfully fetched 'libdl.so.2'
[*] Fetching 'libpthread.so.0' from https://archive.ubuntu.com/.../libc6_2.27-3ubuntu1_amd64.deb (cached)
[+] Successfully fetched 'libpthread.so.0'
[*] Fetching 'ld-linux-x86-64.so.2' from https://archive.ubuntu.com/.../libc6_2.27-3ubuntu1_amd64.deb (cached)
[+] Successfully fetched 'ld-linux-x86-64.so.2'

[*] Patching transitive deps in 'libcrypto.so.1.1'
[*] Symlinking './libdl' -> 'libdl.so.2'
[*] Symlinking './libpthread' -> 'libpthread.so.0'

[*] Finding stripped libraries to unstrip
[*] Unstripping 'libcrypto.so.1.1', 'libdl.so.2', 'libpthread.so.0', 'ld-linux-x86-64.so.2'
...

[*] Patching binary manually
[*] Symlinking './ld' -> 'ld-linux-x86-64.so.2'
[*] Symlinking './libcrypto' -> 'libcrypto.so.1.1'
[*] Symlinking './libc' -> 'libc.so.6'
[+] Successfully wrote patched binary to 'chall_patched'

[*] Writing solve.py
[+] Successfully written solve.py
```

### Fetching glibc source code

```bash
$ ls
dd1  libc-2.23.so
$ pwnsrc.py
[*] libc: libc-2.23.so
[*] libc version: (Ubuntu GLIBC 2.23-0ubuntu10) stable release version 2.23, by Roland McGrath et al.
[*] Fetching glibc source from https://archive.ubuntu.com/ubuntu/pool/universe/g/glibc/glibc-source_2.23-0ubuntu10_all.deb
[+] Successfully written glibc-source to 'glibc-source-2.23.tar.xz'
$ ls
dd1  glibc-source-2.23.tar.xz  libc-2.23.so
$ pwnsrc.py --files malloc.c
[*] libc: libc-2.23.so
[*] libc version: (Ubuntu GLIBC 2.23-0ubuntu10) stable release version 2.23, by Roland McGrath et al.

[*] glibc source: glibc-source-2.23.tar.xz
[*] Finding source code files
[+] Successfully extracted 'malloc.c'
$ ls
dd1  glibc-source-2.23.tar.xz  libc-2.23.so  malloc.c
```
![](assets/gdb_malloc_example.png)
