import os
import subprocess
import sys


def load_allowed():
    allowed_apps = os.getenv("ALLOWED_APPS", "chrome,code").split(",")
    allowed_apps = [a.strip().lower() for a in allowed_apps if a.strip()]
    allowed_dirs_env = os.getenv("ALLOWED_DIRS", "")
    sep = ";" if ";" in allowed_dirs_env else ":"
    allowed_dirs = [p.strip() for p in allowed_dirs_env.split(sep) if p.strip()]
    return allowed_apps, allowed_dirs


def open_app(app: str, allowed_apps):
    aliases = {
        "chrome": "start chrome",
        "code": "start code",
        "notepad++": "start notepad++",
        "notepad": "start notepad",
    }
    if app.lower() not in allowed_apps:
        print("DENY: app not allowed")
        return
    cmd = aliases.get(app.lower())
    if not cmd:
        print("Unknown app alias")
        return
    subprocess.Popen(cmd, shell=True)
    print("OK: opened")


def make_dir(path: str, allowed_dirs):
    def is_safe(p):
        if not allowed_dirs:
            return False
        norm = os.path.abspath(p)
        system_roots = [
            os.path.abspath("C:/Windows"), os.path.abspath("C:/Program Files"), os.path.abspath("C:/Program Files (x86)"),
        ]
        for s in system_roots:
            if norm.lower().startswith(os.path.abspath(s).lower()):
                return False
        for base in allowed_dirs:
            try:
                if norm.lower().startswith(os.path.abspath(base).lower()):
                    return True
            except Exception:
                continue
        return False

    if not is_safe(path):
        print("DENY: path not allowed")
        return
    os.makedirs(path, exist_ok=True)
    print("OK: dir made")


def main():
    allowed_apps, allowed_dirs = load_allowed()
    print("Local agent ready. Type commands: open_app <alias> | make_dir <path> | run <cmd>")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line == "exit":
            break
        parts = line.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "open_app":
            open_app(arg, allowed_apps)
        elif cmd == "make_dir":
            make_dir(arg, allowed_dirs)
        elif cmd == "run":
            # very limited demo: just echo and safe commands
            wl = ["whoami", "ver", "dir", "ls", "python --version"]
            if all(not arg.lower().startswith(w) for w in wl):
                print("DENY: command not allowed")
            else:
                res = subprocess.run(arg, shell=True, capture_output=True, text=True)
                print(res.stdout or res.stderr or "OK")
        else:
            print("Unknown command")


if __name__ == "__main__":
    main()
