#!/usr/bin/env python3
from pwn import *
import shutil
sla = lambda p, d, x: p.sendlineafter(d, x)
sa = lambda p, d, x: p.sendafter(d, x)
sl = lambda p, x: p.sendline(x)
s = lambda p, x: p.send(x)
slan = lambda p, d, n: p.sendlineafter(d, str(n).encode())
ru = lambda p, x: p.recvuntil(x)
rl = lambda p: p.recvline()
rn = lambda p, n: p.recvn(n)
rr = lambda p, t: p.recvrepeat(timeout=t)
ra = lambda p, t: p.recvall(timeout=t)
ia = lambda p: p.interactive()
lg = lambda t, addr: print(t, '->', hex(addr))
binsh = lambda libc: next(libc.search(b"/bin/sh\0"))
leak_bytes = lambda r, offset=0: (u64(r.ljust(8, b"\0")) if context.bytes == 8 else u32(r.ljust(4, b"\0"))) - offset
leak_hex = lambda r, offset=0: int(r, 16) - offset
leak_dec = lambda r, offset=0: int(r, 10) - offset
pad = lambda l, c: c * l
z = lambda l: l * b'\0'
A = lambda l: l * b'A'

{bindings}

TERMINAL = 0
USE_PTY = False
GDB_ATTACH_DELAY = 1
ALLOW_MEM = 0

_wsl_distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
terms = {{
    1: ["/usr/bin/tilix", "-a", "session-add-right", "-e", "bash", "-c"],
    2: ["tmux", "split-window", "-h"],
    3: ["/mnt/c/Windows/system32/cmd.exe", "/c", "start", "wt.exe",
        "-w", "0", "split-pane", "-V", "-s", "0.5",
        "wsl.exe", "-d", _wsl_distro, "bash", "-c"],
    4: ["gnome-terminal", "--", "bash", "-c"],
    5: ["kitty", "bash", "-c"],
    6: ["alacritty", "-e", "bash", "-c"],
    7: ["xterm", "-e"],
}}

if TERMINAL == 0:
    if shutil.which("tilix"):
        context.terminal = terms[1]
    elif os.path.exists("/proc/version") and "microsoft" in open("/proc/version").read().lower() and os.path.exists("/mnt/c/Windows/system32/cmd.exe"):
        context.terminal = terms[3]
    elif shutil.which("tmux") and "TMUX" in os.environ:
        context.terminal = terms[2]
    elif shutil.which("gnome-terminal"):
        context.terminal = terms[4]
    elif shutil.which("kitty"):
        context.terminal = terms[5]
    elif shutil.which("alacritty"):
        context.terminal = terms[6]
    elif shutil.which("xterm"):
        context.terminal = terms[7]
elif TERMINAL in terms:
    context.terminal = terms[TERMINAL]
else:
    log.warning(f"Unknown terminal index: {{TERMINAL}}, using pwntools default")

gdbscript = '''
cd ''' + os.getcwd() + '''
set solib-search-path ''' + os.getcwd() + '''
set sysroot /
set follow-fork-mode parent
set detach-on-fork on

continue
'''

def attach(p):
    if args.GDB:
        gdb.attach(p, gdbscript=gdbscript)
        sleep(GDB_ATTACH_DELAY)

def _mem_limit():
    if ALLOW_MEM > 0:
        import resource
        limit = int(ALLOW_MEM * 1024 ** 3)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

def conn():
    if args.REMOTE:
        host = "localhost"
        port = 1337
        return remote(host, port)
    else:
        if USE_PTY:
            p = process([e.path], stdin=PTY, stdout=PTY, stderr=PTY, preexec_fn=_mem_limit)
        else:
            p = process([e.path], preexec_fn=_mem_limit)
        sleep(0.25)
        attach(p)
        return p

attempt = 0
while True:
    attempt += 1
    print("\n----------> Attempt", attempt)
    
    p = conn()



    ia(p)
    p.close()
    break