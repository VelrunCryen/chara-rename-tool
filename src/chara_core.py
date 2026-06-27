#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
chara_core.py
SillyTavern 角色卡批量重命名 —— 核心逻辑模块（无 GUI、无第三方依赖）。

被 chara_gui.py 与命令行包装调用；也可独立 import 使用。

对外接口：
    parse_card(path)            -> dict | None           解析单卡信息
    collect_items(folder, recursive) -> list[(path, fn, info)]
    build_plan(items, move_nochara) -> list[Action]
    execute_plan(actions, dry_run, on_progress) -> tuple[int,int,int,int]
    write_log(folder, actions, stats)
    load_history(folder)        -> list[(old, new)]
    undo_from_history(folder)   -> int                   返回撤销条数
"""

import os
import re
import json
import base64
import struct
import zlib
import time
from collections import defaultdict

PNG_SIG = b'\x89PNG\r\n\x1a\n'
INVALID_CHARS = re.compile(r'[\\/:\*\?"<>\|\x00-\x1f]')
VERSION_RE = re.compile(r'(v?\d+(?:\.\d+){0,3})', re.IGNORECASE)
HISTORY_FILE = '.rename_history.json'
LOG_PREFIX = '重命名日志_'


# ---------- PNG chunk 读取 ----------

def read_chunks(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != PNG_SIG:
        return None
    offset = 8
    out = []
    n = len(data)
    while offset < n:
        if offset + 8 > n:
            break
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        ctype = data[offset + 4:offset + 8].decode('latin-1', 'replace')
        cdata = data[offset + 8:offset + 8 + length]
        out.append((ctype, cdata))
        offset += 12 + length
    return out


def extract_chara(path):
    chunks = read_chunks(path)
    if not chunks:
        return None
    for ctype, cdata in chunks:
        if ctype == 'tEXt':
            kw, _, val = cdata.partition(b'\x00')
            if kw == b'chara':
                return val
        elif ctype == 'zTXt':
            kw, sep, rest = cdata.partition(b'\x00')
            if kw == b'chara' and sep:
                try:
                    return zlib.decompress(rest[1:])
                except Exception:
                    return None
        elif ctype == 'iTXt':
            kw, sep, rest = cdata.partition(b'\x00')
            if kw == b'chara' and sep:
                parts = rest.split(b'\x00', 3)
                if len(parts) < 4:
                    return None
                text = parts[3]
                if parts[0] == b'\x01':
                    try:
                        text = zlib.decompress(text)
                    except Exception:
                        return None
                return text
    return None


# ---------- 角色信息 ----------

def parse_card(path):
    """返回 dict 或 None"""
    raw = extract_chara(path)
    if raw is None:
        return None
    try:
        obj = json.loads(base64.b64decode(raw.decode('utf-8', 'replace')))
    except Exception:
        return None
    d = obj.get('data', obj) if isinstance(obj.get('data'), dict) else obj
    if not isinstance(d, dict):
        return None
    name = d.get('name', '') or ''
    version = d.get('version')
    book = d.get('character_book')
    book_name = book.get('name') if isinstance(book, dict) else None
    spec = obj.get('spec', '') or d.get('spec', '')
    m = VERSION_RE.search(name or '')
    name_ver = m.group(1) if m else None
    return {
        'name': name,
        'book': book_name,
        'version': version,
        'name_ver': name_ver,
        'spec': spec,
    }


# ---------- 工具 ----------

def sanitize(name):
    name = INVALID_CHARS.sub('_', str(name)).strip().rstrip('.').strip()
    return name if name else '未命名'


def version_token(info):
    v = info.get('version') or info.get('name_ver')
    if v:
        v = str(v).strip()
        if v and not re.match(r'^v', v, re.IGNORECASE):
            v = 'V' + v
        return v
    return None


def _unique(base, used):
    if base not in used:
        used.add(base)
        return base
    stem, ext = os.path.splitext(base)
    n = 2
    while True:
        cand = f"{stem} ({n}){ext}"
        if cand not in used:
            used.add(cand)
            return cand
        n += 1


# ---------- Action 数据类 ----------

class Action:
    """表示对单个 PNG 文件要做什么操作"""

    def __init__(self, folder, fn, target, status):
        self.folder = folder
        self.fn = fn            # 原文件名（不含路径）
        self.target = target    # 新文件名或子文件夹相对路径
        self.status = status    # RENAME / SAME / NOBOOK / NODATA_MOVE / NODATA

    @property
    def src(self):
        return os.path.join(self.folder, self.fn)

    @property
    def dst(self):
        return os.path.join(self.folder, self.target)


# ---------- 收集与计划 ----------

def collect_items(folder, recursive=True):
    """返回 [(folder, fn, info)]"""
    out = []
    if recursive:
        for f, _, files in os.walk(folder):
            for fn in sorted(files):
                if fn.lower().endswith('.png') and not fn.startswith('.'):
                    out.append((f, fn, parse_card(os.path.join(f, fn))))
    else:
        for fn in sorted(os.listdir(folder)):
            if fn.lower().endswith('.png') and not fn.startswith('.'):
                out.append((folder, fn, parse_card(os.path.join(folder, fn))))
    return out


def build_plan(items, move_nochara=False):
    """items: [(folder, fn, info)] -> list[Action]"""
    by_folder = defaultdict(list)
    for folder, fn, info in items:
        by_folder[folder].append((fn, info))

    actions = []
    for folder, lst in by_folder.items():
        groups = defaultdict(list)
        no_book = []
        no_data = []
        for fn, info in lst:
            if info is None:
                no_data.append(fn)
                continue
            if not info.get('book'):
                no_book.append(fn)
                continue
            groups[sanitize(info['book'])].append((fn, info))

        # 计算"会被腾出的名字"：
        # 只有「会被改名或移走的源文件」原名才会腾空；
        # SAME / NOBOOK 保留原名 → 名字仍被占用。
        # 但 SAME 的判定依赖目标是否与原名相等，这里先做第一次扫描猜测：
        # 单成员 group 中 target == fn 视为 SAME（保留原名），
        # 多成员 / 不同名则视为会腾出原名。
        frees = set()
        if move_nochara:
            frees |= set(no_data)
        for key, members in groups.items():
            if len(members) == 1:
                fn, info = members[0]
                if sanitize(info.get('book', '')) + '.png' != fn:
                    frees.add(fn)             # 将被改名，原名腾出
            else:
                for fn, info in members:
                    frees.add(fn)            # 多张几乎都会改名，原名腾出

        # 共享 used_targets：现存文件名减去将被腾出的源名，
        # 让 _unique 自动给目标加后缀避开现有同名文件。
        existing = set()
        try:
            existing = set(os.listdir(folder))
        except Exception:
            existing = set()
        used_targets = existing - frees

        for key, members in groups.items():
            if len(members) == 1:
                fn, info = members[0]
                target = _unique(key + '.png', used_targets)
                if target == fn:
                    actions.append(Action(folder, fn, target, 'SAME'))
                else:
                    actions.append(Action(folder, fn, target, 'RENAME'))
                continue

            vers = [(fn, version_token(info) or '', info) for fn, info in members]
            assigned = [None] * len(vers)
            used_vers = set()

            for i, (fn, v, info) in enumerate(vers):
                if v and v not in used_vers:
                    assigned[i] = (fn, _unique(f"{key} {v}.png", used_targets))
                    used_vers.add(v)

            remaining = [i for i, a in enumerate(assigned) if a is None]
            stems = [os.path.splitext(vers[i][0])[0] for i in remaining]
            all_diff = len(set(stems)) == len(stems)
            all_prefixed = all(s == key or s.startswith(key + ' ') or
                               s.startswith(key + '(') for s in stems)
            if all_diff and all_prefixed:
                for i in remaining:
                    assigned[i] = (vers[i][0], _unique(vers[i][0], used_targets))
            else:
                base = f"{key} (2).png"
                for i in remaining:
                    assigned[i] = (vers[i][0], _unique(base, used_targets))

            for fn, target in assigned:
                actions.append(Action(folder, fn, target,
                                      'SAME' if target == fn else 'RENAME'))

        for fn in no_book:
            actions.append(Action(folder, fn, fn, 'NOBOOK'))

        for fn in no_data:
            if move_nochara:
                actions.append(Action(folder, fn,
                                      os.path.join('非角色卡', fn), 'NODATA_MOVE'))
            else:
                actions.append(Action(folder, fn, fn, 'NODATA'))

    return actions


# ---------- 执行 ----------

def execute_plan(actions, dry_run=False, on_progress=None):
    """
    真正执行重命名。
    on_progress(done, total, action) — 回调，用于更新进度条。
    返回 (renamed, same, skipped, moved_nodata)
    """
    renamed = same = skipped = moved = 0
    # 记录成功重命名，用于写历史
    history_records = []
    total = len(actions)
    for i, act in enumerate(actions):
        if act.status == 'SAME':
            same += 1
        elif act.status == 'RENAME':
            if not dry_run:
                dst = act.dst
                src = act.src
                # 防御性：dst 被占用且不是自己时，绝不覆盖，直接跳过
                if (os.path.exists(dst)
                        and os.path.abspath(src) != os.path.abspath(dst)):
                    skipped += 1
                else:
                    try:
                        os.rename(src, dst)
                        renamed += 1
                        history_records.append((act.fn, act.target, act.folder))
                    except Exception:
                        skipped += 1
            else:
                renamed += 1
        elif act.status == 'NODATA_MOVE':
            if not dry_run:
                subdir = os.path.dirname(act.dst)
                os.makedirs(subdir, exist_ok=True)
                try:
                    os.rename(act.src, act.dst)
                    moved += 1
                except Exception:
                    skipped += 1
            else:
                moved += 1
        elif act.status in ('NODATA', 'NOBOOK'):
            skipped += 1
        if on_progress:
            on_progress(i + 1, total, act)
    if not dry_run and history_records:
        _save_history_merge(history_records, actions[0].folder if actions else None)
    return renamed, same, skipped, moved


# ---------- 历史与撤销 ----------

def _save_history_merge(records, default_folder):
    """records: [(old_fn, new_fn, folder)]"""
    by_folder = defaultdict(dict)
    for old, new, folder in records:
        by_folder[folder][old] = new
    for folder, mapping in by_folder.items():
        hp = os.path.join(folder, HISTORY_FILE)
        existing = {}
        if os.path.exists(hp):
            try:
                existing = json.load(open(hp, 'r', encoding='utf-8'))
            except Exception:
                existing = {}
        existing.update(mapping)
        json.dump(existing, open(hp, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)


def load_history(folder):
    """返回 dict {old_fn: new_fn}"""
    hp = os.path.join(folder, HISTORY_FILE)
    if not os.path.exists(hp):
        return None
    try:
        return json.load(open(hp, 'r', encoding='utf-8'))
    except Exception:
        return None


def undo_from_history(folder):
    """
    按 .rename_history.json 反向重命名。
    返回 (成功数, 失败数)。

    成功还原的项从历史中删除；未还原（失败）的项保留并回写历史，
    以便用户事后排查或再次尝试，不会丢失记录。
    """
    mapping = load_history(folder)
    if not mapping:
        return 0, 0
    ok = fail = 0
    remaining = dict(mapping)   # 待回写的历史
    for old, new in list(mapping.items()):
        src = os.path.join(folder, new)
        dst = os.path.join(folder, old)
        if not os.path.exists(src):
            fail += 1
            continue
        if os.path.exists(dst):
            fail += 1
            continue
        try:
            os.rename(src, dst)
            ok += 1
            del remaining[old]        # 已还原，从历史中移除
        except Exception:
            fail += 1
    # 回写：成功项已移除，失败项保留
    hp = os.path.join(folder, HISTORY_FILE)
    if remaining:
        try:
            json.dump(remaining, open(hp, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass
    else:
        # 全部还原成功，删除历史文件
        try:
            os.remove(hp)
        except Exception:
            pass
    return ok, fail


# ---------- 日志 ----------

def write_log(folder, actions, stats):
    ts = time.strftime('%Y%m%d_%H%M%S')
    path = os.path.join(folder, f"{LOG_PREFIX}{ts}.txt")
    lines = [
        f"SillyTavern 角色卡批量重命名日志",
        f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"目录: {folder}",
        f"成功重命名: {stats[0]}  无需改名: {stats[1]}  跳过: {stats[2]}  非角色卡移走: {stats[3]}",
        "-" * 60,
    ]
    for a in actions:
        if a.status == 'RENAME':
            lines.append(f"[重命名] {a.fn}  ->  {a.target}")
        elif a.status == 'SAME':
            lines.append(f"[无需改] {a.fn}")
        elif a.status == 'NOBOOK':
            lines.append(f"[无世界书] {a.fn}")
        elif a.status == 'NODATA_MOVE':
            lines.append(f"[非角色卡移走] {a.fn}  ->  {a.target}")
        elif a.status == 'NODATA':
            lines.append(f"[无数据跳过] {a.fn}")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return path
    except Exception:
        return None