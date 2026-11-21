#!/usr/bin/env python3
"""Populate vendor/ from glide.lock at pinned commits.

Usage: python3 vendor_from_lock.py [path/to/glide.lock]
Reads every "- name: <importpath>" / "version: <sha>" pair and shallow-fetches
the exact commit into vendor/<importpath>. Retries each dep 3 times.
Only imports/ is used (devimports omitted to match etcd's build script).
"""
import os
import subprocess
import sys

lock = sys.argv[1] if len(sys.argv) > 1 else "glide.lock"
root = os.path.dirname(os.path.abspath(lock))

def repo_url(importpath):
    if importpath.startswith("github.com/"):
        return "https://" + importpath
    if importpath.startswith("golang.org/x/"):
        return "https://go.googlesource.com/" + importpath[len("golang.org/x/"):]
    if importpath == "google.golang.org/grpc":
        return "https://github.com/grpc/grpc-go"
    if importpath == "google.golang.org/appengine":
        return "https://github.com/golang/appengine"
    if importpath == "google.golang.org/cloud":
        return "https://github.com/GoogleCloudPlatform/gcloud-golang"
    if importpath == "google.golang.org/protobuf":
        return "https://github.com/protocolbuffers/protobuf-go"
    if importpath == "cloud.google.com/go":
        return "https://github.com/googleapis/google-cloud-go"
    if importpath == "gopkg.in/yaml.v2":
        return "https://gopkg.in/yaml.v2"
    return "https://" + importpath

def parse(path):
    deps, cur = [], None
    section = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("imports:"):
                section = "imports"
            elif line.startswith("devimports:"):
                section = "dev"
            elif line.startswith("- name:"):
                if section == "imports":
                    cur = {"name": line.split(":", 1)[1].strip()}
                    deps.append(cur)
            elif line.strip().startswith("version:") and cur is not None and section == "imports":
                cur["version"] = line.split(":", 1)[1].strip()
    return [d for d in deps if d.get("version")]

def fetch(name, sha, dest):
    if os.path.isdir(os.path.join(dest, ".git")):
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    url = repo_url(name)
    for attempt in range(1, 4):
        try:
            subprocess.run(["rm", "-rf", dest], check=True)
            subprocess.run(["git", "init", "-q", dest], check=True)
            g = subprocess.run(
                ["git", "-C", dest, "remote", "add", "origin", url], check=True)
            r = subprocess.run(
                ["git", "-C", dest, "fetch", "-q", "--depth", "1", "origin", sha],
                timeout=180)
            if r.returncode != 0:
                raise RuntimeError("fetch rc=%d" % r.returncode)
            subprocess.run(["git", "-C", dest, "checkout", "-q", "FETCH_HEAD"], check=True)
            return True
        except Exception as e:
            sys.stderr.write("  attempt %d failed for %s: %s\n" % (attempt, name, e))
    return False

def main():
    deps = parse(lock)
    print("deps to vendor: %d" % len(deps))
    failed = []
    for i, d in enumerate(deps, 1):
        dest = os.path.join(root, "vendor", d["name"])
        print("[%2d/%d] %s @ %s" % (i, len(deps), d["name"], d["version"][:9]))
        if not fetch(d["name"], d["version"], dest):
            failed.append(d["name"])
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("all deps vendored OK")

if __name__ == "__main__":
    main()
