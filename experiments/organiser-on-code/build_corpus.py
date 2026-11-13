# SPDX-License-Identifier: Apache-2.0
"""Corpus builder: one atom per function or method from six stdlib packages.

An atom is a top-level function or a direct method of a top-level class,
3 to 200 lines long (decorators count toward the span). Atoms whose exact
source text occurs more than once in the six-package corpus are dropped.
Labels are the enclosing package (l1), module (l2) and class-or-None (l3).

Reads the running interpreter's standard library read-only. Deterministic:
files, modules and atoms are all visited in sorted order.
"""
import ast
import os
import sys
import sysconfig
import textwrap
import tokenize

PACKAGES = ["logging", "multiprocessing", "wsgiref", "asyncio", "xml", "http"]
MIN_LINES = 3
MAX_LINES = 200
MIN_ATOMS_PER_MODULE = 15
MIN_MODULES_PER_PACKAGE = 3


def stdlib_root():
    return sysconfig.get_path("stdlib")


def package_files(root, package):
    out = []
    base = os.path.join(root, package)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return out


def module_name(root, path):
    rel = os.path.relpath(path, root)
    assert rel.endswith(".py")
    parts = rel[:-3].split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def extract_atoms(root, package, path):
    """Atoms from one file. Raises on unreadable or unparsable files."""
    with tokenize.open(path) as handle:
        source = handle.read()
    lines = source.split("\n")
    tree = ast.parse(source, filename=path)
    module = module_name(root, path)
    relpath = os.path.relpath(path, root)
    atoms = []

    def emit(node, qualname, clsname):
        if node.decorator_list:
            start = node.decorator_list[0].lineno
        else:
            start = node.lineno
        end = node.end_lineno
        nlines = end - start + 1
        if nlines < MIN_LINES or nlines > MAX_LINES:
            return
        text = textwrap.dedent("\n".join(lines[start - 1:end]))
        atoms.append({
            "id": "%s||%s||%s||%d" % (package, module, qualname, start),
            "l1": package,
            "l2": module,
            "l3": clsname,
            "file": relpath,
            "start": start,
            "end": end,
            "nlines": nlines,
            "text": text,
        })

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            emit(node, node.name, None)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    emit(sub, "%s.%s" % (node.name, sub.name), node.name)
    return atoms


def build_corpus(root=None, packages=None):
    """Collect atoms; returns {"atoms": [...], "stats": {...}} sorted by id."""
    root = root or stdlib_root()
    packages = list(packages or PACKAGES)
    raw = []
    n_files = 0
    for package in sorted(packages):
        for path in package_files(root, package):
            n_files += 1
            raw.extend(extract_atoms(root, package, path))
    counts = {}
    for atom in raw:
        counts[atom["text"]] = counts.get(atom["text"], 0) + 1
    atoms = sorted((a for a in raw if counts[a["text"]] == 1),
                   key=lambda a: a["id"])
    return {"atoms": atoms, "stats": {
        "root": root,
        "packages": sorted(packages),
        "files": n_files,
        "atoms_raw": len(raw),
        "atoms_kept": len(atoms),
    }}


def eligibility(atoms):
    """Modules with >=15 atoms; packages with >=3 such modules."""
    by_mod = {}
    for atom in atoms:
        by_mod.setdefault((atom["l1"], atom["l2"]), []).append(atom["id"])
    mods_by_pkg = {}
    for (pkg, mod), ids in by_mod.items():
        if len(ids) >= MIN_ATOMS_PER_MODULE:
            mods_by_pkg.setdefault(pkg, set()).add(mod)
    mods_by_pkg = {p: mods for p, mods in mods_by_pkg.items()
                   if len(mods) >= MIN_MODULES_PER_PACKAGE}
    truth = {a["id"]: (a["l1"], a["l2"], a["l3"]) for a in atoms}
    atoms_by_mod = {(p, m): sorted(by_mod[(p, m)])
                    for p in mods_by_pkg for m in mods_by_pkg[p]}
    return {"packages": sorted(mods_by_pkg),
            "mods_by_pkg": {p: sorted(mods_by_pkg[p]) for p in mods_by_pkg},
            "atoms_by_mod": atoms_by_mod,
            "truth": truth,
            "n_eligible_modules": sum(len(v) for v in mods_by_pkg.values()),
            "n_eligible_atoms": sum(len(v) for v in atoms_by_mod.values())}


def main(argv):
    if len(argv) != 1:
        raise SystemExit("usage: python3 build_corpus.py")
    corpus = build_corpus()
    elig = eligibility(corpus["atoms"])
    stats = corpus["stats"]
    print("stdlib: %s" % stats["root"])
    print("files: %d atoms: %d kept: %d" % (
        stats["files"], stats["atoms_raw"], stats["atoms_kept"]))
    print("eligible packages (%d): %s" % (
        len(elig["packages"]), " ".join(elig["packages"])))
    print("eligible modules: %d atoms: %d" % (
        elig["n_eligible_modules"], elig["n_eligible_atoms"]))
    for pkg in elig["packages"]:
        print("  %s: %s" % (pkg, " ".join(elig["mods_by_pkg"][pkg])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
