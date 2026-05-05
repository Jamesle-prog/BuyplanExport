"""Folder scanning and versioned filenames."""
import os


def scan_pdfs(paths: list[str], recursive: bool = True) -> list[str]:
    out = []
    for p in paths:
        if os.path.isfile(p) and p.lower().endswith(".pdf"):
            out.append(p)
        elif os.path.isdir(p):
            if recursive:
                for root, _, files in os.walk(p):
                    out.extend(os.path.join(root, f) for f in files if f.lower().endswith(".pdf"))
            else:
                out.extend(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".pdf"))
    return out


def versioned_path(directory: str, base_name: str, extension: str) -> str:
    """Return directory/base_name.ext, or _v2/_v3/... if taken."""
    path = os.path.join(directory, base_name + extension)
    if not os.path.exists(path):
        return path
    v = 2
    while True:
        path = os.path.join(directory, f"{base_name}_v{v}{extension}")
        if not os.path.exists(path):
            return path
        v += 1
