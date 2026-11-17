#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SUSFS LKM BTF-relax 工具流辅助脚本（无第三方依赖）。

子命令:
  fetch  <ref> [-o FILE]      从上游 repo 拉指定 ref(tag/分支/commit) 的 fsnotify_lifetime.c
  patch  <src> [-o FILE]      把 fsnotify_lifetime.patch 应用到源码；上下文不符会报错并要求人工适配
  verify <ko> [--zip FILE]    校验编译产物: ELF/KMI/补丁字符串/vermagic，可比对 zip 的 sha256

默认走代理 http://127.0.0.1:7897（本环境 Google/GitHub raw 需要）。
用法示例见同目录 README.md。
"""
import sys
import os
import re
import json
import hashlib
import urllib.request
import argparse

REPO = "inforcqb/susfs4ksu-for-lkm"
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/kernel/fsnotify_lifetime.c"
DEFAULT_PROXY = "http://127.0.0.1:7897"
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_FILE = os.path.join(HERE, "fsnotify_lifetime.patch")

# 补丁必须出现在产物里的字符串（证明编译进去的是改过的源码）
PATCH_MARKERS = [
    b"sus_path: alloc_group FUNC absent in BTF, assuming 1-arg",
    b"sus_path: add_mark FUNC absent in BTF, assuming 5-arg",
]


def _opener(proxy):
    if proxy and proxy.lower() != "none":
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cmd_fetch(args):
    url = RAW.format(repo=args.repo, ref=args.ref)
    out = args.out or ("fsnotify_lifetime.%s.c" % re.sub(r"[^A-Za-z0-9_.-]", "_", args.ref))
    try:
        with _opener(args.proxy).open(url, timeout=30) as r:
            data = r.read()
    except Exception as e:
        print("拉取失败: %s" % e, file=sys.stderr)
        return 2
    if not data or data.lstrip().startswith(b"404: Not Found"):
        print("ref 不存在或文件不在该 ref: %s" % args.ref, file=sys.stderr)
        return 2
    with open(out, "wb") as f:
        f.write(data)
    print("已拉取 %s -> %s (%d 字节)" % (args.ref, out, len(data)))
    return 0


def parse_patch(text):
    """把 unified diff 解析成 [(old_lines, new_lines), ...]，只处理单个文件。"""
    hunks = []
    old, new = [], []
    for line in text.splitlines():
        if line.startswith("@@"):
            if old:
                hunks.append((old, new))
                old, new = [], []
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("-"):
            old.append(line[1:])
        elif line.startswith("+"):
            new.append(line[1:])
        elif line.startswith(" "):
            old.append(line[1:])
            new.append(line[1:])
    if old:
        hunks.append((old, new))
    return hunks


def cmd_patch(args):
    src_text = open(args.src, encoding="utf-8").read().replace("\r\n", "\n")
    patch_text = open(args.patch, encoding="utf-8").read()
    hunks = parse_patch(patch_text)
    if not hunks:
        print("补丁为空或格式无法识别: %s" % args.patch, file=sys.stderr)
        return 2
    out = src_text
    for n, (old, new) in enumerate(hunks, 1):
        old_s, new_s = "\n".join(old), "\n".join(new)
        cnt = out.count(old_s)
        if cnt != 1:
            print("第 %d 个 hunk 上下文匹配 %d 次（期望 1）——上游结构已变，需人工适配补丁。"
                  % (n, cnt), file=sys.stderr)
            print("  旧块首行: %s" % (old[0] if old else "<空>"), file=sys.stderr)
            return 3
        out = out.replace(old_s, new_s, 1)
    dst = args.out or (os.path.splitext(args.src)[0] + ".patched.c")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("补丁应用成功: %d 个 hunk -> %s" % (len(hunks), dst))
    return 0


def cmd_verify(args):
    data = open(args.ko, "rb").read()
    ok = True

    def chk(label, cond):
        nonlocal ok
        ok = ok and cond
        print("  [%s] %s" % ("OK" if cond else "FAIL", label))

    print("校验 %s (%d 字节)" % (args.ko, len(data)))
    chk("ELF 魔数", data[:4] == b"\x7fELF")
    chk("KMI android13-5.15", b"android13-5.15" in data)
    for m in PATCH_MARKERS:
        chk("补丁串 %s" % m.decode().split(", assuming")[-1].strip(), m in data)
    vm = re.search(rb"vermagic=[^\x00]{1,96}", data)
    print("  vermagic: %s" % (vm.group().decode("utf-8", "replace") if vm else "未找到"))

    if args.zip:
        zdata = open(args.zip, "rb").read()
        print("  %s sha256: %s" % (os.path.basename(args.zip), hashlib.sha256(zdata).hexdigest()))
        print("  说明: 把上面的 sha256 与 GitHub artifact 页面显示的 digest 比对。")

    print("结论: %s" % ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


def build_parser():
    p = argparse.ArgumentParser(description="SUSFS LKM BTF-relax 工具流辅助脚本")
    sub = p.add_subparsers(dest="cmd")

    f = sub.add_parser("fetch", help="拉取指定 ref 的源码")
    f.add_argument("ref", help="tag/分支/commit，如 v2.3.0-r18.9-1")
    f.add_argument("-o", "--out", help="输出文件")
    f.add_argument("--repo", default=REPO)
    f.add_argument("--proxy", default=DEFAULT_PROXY, help="代理，传 none 禁用")
    f.set_defaults(func=cmd_fetch)

    a = sub.add_parser("patch", help="应用补丁并校验上下文")
    a.add_argument("src", help="源码文件")
    a.add_argument("-o", "--out", help="输出文件")
    a.add_argument("--patch", default=PATCH_FILE)
    a.set_defaults(func=cmd_patch)

    v = sub.add_parser("verify", help="校验编译产物")
    v.add_argument("ko", help="susfs_guard_lkm.ko 路径")
    v.add_argument("--zip", help="对应 artifact zip，用于算 sha256")
    v.set_defaults(func=cmd_verify)

    return p


if __name__ == "__main__":
    ap = build_parser()
    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        sys.exit(0)
    sys.exit(args.func(args))
