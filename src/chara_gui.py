#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
角色卡重命名工具 GUI（基于 tkinter，零第三方依赖）。
封装：双击即用，可选文件夹/单个文件，支持预览、撤销与日志。

运行：
    python chara_gui.py
打包（可选）：
    pyinstaller -F -w --name 角色卡重命名工具 chara_gui.py
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import chara_core as core


# ---------- 设计令牌（统一配色 / 字体 / 间距） ----------
COLOR_BG        = "#f4f5f7"     # 主背景
COLOR_CARD      = "#ffffff"     # 卡片背景
COLOR_BORDER    = "#dfe2e6"     # 区块边框
COLOR_TEXT      = "#1f2329"     # 主文字
COLOR_TEXT_SUB  = "#8a9099"     # 副文字
COLOR_ACCENT    = "#2e7d32"     # 主色（绿，做「开始」）
COLOR_ACCENT_H  = "#256528"
COLOR_SECONDARY = "#4a5568"     # 次色（灰蓝，做「预览」）
COLOR_SECONDARY_H = "#3a4354"
COLOR_WARN      = "#c2410c"     # 橙（撤销）
COLOR_WARN_H    = "#9a3412"
COLOR_HEADER_BG = "#2e7d32"     # 顶部标题条
FONT_FAMILY     = "Microsoft YaHei UI"
FONT_TITLE      = (FONT_FAMILY, 14, "bold")
FONT_SECTION    = (FONT_FAMILY, 10, "bold")
FONT_BODY       = (FONT_FAMILY, 10)
FONT_BODY_B     = (FONT_FAMILY, 10, "bold")
FONT_SMALL      = (FONT_FAMILY, 9)
FONT_LOG        = ("Consolas", 9)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SillyTavern 角色卡批量重命名工具")
        self.geometry("820x620")
        self.minsize(720, 540)
        self.configure(bg=COLOR_BG)
        self._setup_style()
        self._build_ui()
        self._target = None        # 当前选定文件夹路径
        self._single_file = None   # 选单文件时记录文件名

    # ---------- ttk 样式 ----------
    def _setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use('clam')   # clam 对配色支持最好
        except Exception:
            pass
        st.configure('.', background=COLOR_BG, foreground=COLOR_TEXT,
                     fieldbackground=COLOR_CARD, bordercolor=COLOR_BORDER,
                     lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER,
                     font=FONT_BODY)
        # LabelFrame
        st.configure('TLabelframe', background=COLOR_CARD,
                    bordercolor=COLOR_BORDER, relief='solid', borderwidth=1)
        st.configure('TLabelframe.Label', background=COLOR_CARD,
                    foreground=COLOR_ACCENT, font=FONT_SECTION)
        # Label
        st.configure('TLabel', background=COLOR_CARD, foreground=COLOR_TEXT,
                     font=FONT_BODY)
        st.configure('Sub.TLabel', background=COLOR_CARD,
                     foreground=COLOR_TEXT_SUB, font=FONT_SMALL)
        st.configure('Mode.TLabel', background=COLOR_CARD,
                     foreground=COLOR_ACCENT, font=FONT_BODY_B)
        # Checkbutton
        st.configure('TCheckbutton', background=COLOR_CARD,
                     foreground=COLOR_TEXT, font=FONT_BODY)
        # 进度条
        st.configure('Horizontal.TProgressbar',
                     troughcolor=COLOR_BORDER, background=COLOR_ACCENT,
                     bordercolor=COLOR_BORDER, thickness=14)

    # ---------- 自定义扁平按钮 ----------
    def _flat_button(self, parent, text, bg, fg="#ffffff", hbg=None,
                     command=None, width=14, height=28, font=FONT_BODY_B):
        hbg = hbg or bg
        b = tk.Button(parent, text=text, command=command,
                      bg=bg, fg=fg, activebackground=hbg, activeforeground=fg,
                      relief='flat', bd=0, cursor='hand2',
                      font=font, width=width, height=1,
                      padx=14, pady=6, highlightthickness=0)
        # 鼠标悬停效果
        b.bind('<Enter>', lambda e: b.config(bg=hbg))
        b.bind('<Leave>', lambda e: b.config(bg=bg))
        return b

    # ---------- 界面 ----------
    def _build_ui(self):
        # 顶部品牌条
        header = tk.Frame(self, bg=COLOR_HEADER_BG, height=52)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="SillyTavern 角色卡批量重命名工具",
                 bg=COLOR_HEADER_BG, fg="#ffffff",
                 font=(FONT_FAMILY, 15, "bold")).pack(side='left', padx=20)
        tk.Label(header, text="按内嵌世界书名一键改名  ·  支持预览 / 撤销",
                 bg=COLOR_HEADER_BG, fg="#c8e6c9",
                 font=FONT_SMALL).pack(side='left')

        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill='both', expand=True, padx=18, pady=14)
        body.columnconfigure(0, weight=1)

        # ① 选择目标
        top = self._section(body, "①  选择目标", row=0)
        inner = tk.Frame(top, bg=COLOR_CARD)
        inner.pack(fill='x', padx=12, pady=(4, 10))
        inner.columnconfigure(0, weight=1)
        self.lbl_target = tk.Label(inner, text="尚未选择目标",
                                  bg=COLOR_CARD, fg=COLOR_TEXT_SUB,
                                  font=FONT_BODY, anchor='w')
        self.lbl_target.grid(row=0, column=0, sticky='we', padx=(0, 10))
        btnrow = tk.Frame(inner, bg=COLOR_CARD)
        btnrow.grid(row=0, column=1, sticky='e')
        self._flat_button(btnrow, "选择文件夹", COLOR_SECONDARY, hbg=COLOR_SECONDARY_H,
                          command=self._pick_folder, width=12).pack(side='left',
                                                                    padx=(0, 6))
        self._flat_button(btnrow, "选择单张卡片", COLOR_SECONDARY, hbg=COLOR_SECONDARY_H,
                          command=self._pick_file, width=12).pack(side='left',
                                                                  padx=(0, 6))
        self.btn_clear = self._flat_button(btnrow, "清除", "#94a3b8", hbg="#64748b",
                                          command=self._clear_target,
                                          width=6)
        self.btn_clear.pack(side='left')
        self.btn_clear.config(state='disabled', disabledforeground="#cbd5e1",
                              bg="#e2e8f0")
        # 模式提示
        self.lbl_mode = tk.Label(inner, text="", bg=COLOR_CARD,
                                 fg=COLOR_ACCENT, font=FONT_BODY_B, anchor='w')
        self.lbl_mode.grid(row=1, column=0, columnspan=2, sticky='w', pady=(6, 0))

        # ② 选项
        opt = self._section(body, "②  选项", row=1)
        optrow = tk.Frame(opt, bg=COLOR_CARD)
        optrow.pack(fill='x', padx=12, pady=(4, 10))
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_move = tk.BooleanVar(value=True)
        ttk.Checkbutton(optrow, text="包含子文件夹",
                        variable=self.var_recursive,
                        style='TCheckbutton').pack(side='left', padx=(0, 24))
        ttk.Checkbutton(optrow, text="非角色卡自动移入「非角色卡」子文件夹",
                        variable=self.var_move,
                        style='TCheckbutton').pack(side='left')
        tk.Label(optrow, text="意即纯立绘图归类整理",
                 bg=COLOR_CARD, fg=COLOR_TEXT_SUB,
                 font=FONT_SMALL).pack(side='left', padx=(8, 0))

        # ③ 操作
        act = self._section(body, "③  操作", row=2)
        actrow = tk.Frame(act, bg=COLOR_CARD)
        actrow.pack(fill='x', padx=12, pady=(6, 10))
        tip = tk.Label(actrow, text="先「预览」核对，再「开始重命名」；并可随时撤销",
                       bg=COLOR_CARD, fg=COLOR_TEXT_SUB, font=FONT_SMALL,
                       anchor='w')
        tip.pack(fill='x', pady=(0, 6))
        grow = tk.Frame(actrow, bg=COLOR_CARD)
        grow.pack(fill='x')
        self.btn_preview = self._flat_button(grow, "预览   只看不改",
               COLOR_SECONDARY, hbg=COLOR_SECONDARY_H,
               command=lambda: self._on_run(dry=True), width=20)
        self.btn_preview.pack(side='left', padx=(0, 10))
        self.btn_run = self._flat_button(grow, "开始重命名",
               COLOR_ACCENT, hbg=COLOR_ACCENT_H,
               command=lambda: self._on_run(dry=False), width=16)
        self.btn_run.pack(side='left', padx=(0, 10))
        self.btn_undo = self._flat_button(grow, "撤销上次操作",
               COLOR_WARN, hbg=COLOR_WARN_H,
               command=self._on_undo, width=14)
        self.btn_undo.pack(side='left')

        # 进度条
        prog = tk.Frame(body, bg=COLOR_BG)
        prog.grid(row=3, column=0, sticky='we', pady=(0, 8))
        prog.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(prog, mode='determinate',
                                        style='Horizontal.TProgressbar')
        self.progress.grid(row=0, column=0, sticky='we')
        self.lbl_progress = tk.Label(prog, text="0 / 0", bg=COLOR_BG,
                                    fg=COLOR_TEXT_SUB, font=FONT_SMALL, width=10)
        self.lbl_progress.grid(row=0, column=1, padx=(10, 0))

        # ④ 日志
        log = self._section(body, "④  日志", row=4, expand=True)
        logwrap = tk.Frame(log, bg=COLOR_CARD)
        logwrap.pack(fill='both', expand=True, padx=12, pady=(4, 10))
        # Text + 滚动条容器，用一个带边框的 Frame 包起来
        logbox = tk.Frame(logwrap, bg=COLOR_BORDER, bd=1)
        logbox.pack(fill='both', expand=True)
        self.log = tk.Text(logbox, wrap='none', state='disabled',
                          font=FONT_LOG, background="#1e1e1e",
                          foreground="#d4d4d4", bd=0, padx=10, pady=8,
                          insertbackground="#d4d4d4", highlightthickness=0)
        sb = ttk.Scrollbar(logbox, command=self.log.yview,
                           style='Vertical.TScrollbar')
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True, side='left')
        self.log.tag_config('ok', foreground='#73c991')
        self.log.tag_config('same', foreground='#888')
        self.log.tag_config('skip', foreground='#d19a66')
        self.log.tag_config('move', foreground='#569cd6')
        self.log.tag_config('err', foreground='#f44747')
        self.log.tag_config('info', foreground='#c586c0')

        # 状态栏
        self.var_status = tk.StringVar(value="就绪")
        sb_bar = tk.Frame(self, bg=COLOR_TEXT, height=24)
        sb_bar.pack(fill='x', side='bottom')
        sb_bar.pack_propagate(False)
        tk.Label(sb_bar, textvariable=self.var_status, bg=COLOR_TEXT,
                 fg="#ffffff", font=FONT_SMALL, anchor='w').pack(
            side='left', padx=10, pady=2)

    # ---------- 区块构造 ----------
    def _section(self, parent, title, row, expand=False):
        f = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                     highlightthickness=1, bd=0)
        f.grid(row=row, column=0, sticky='we' if not expand else 'nsew',
               pady=(0, 10))
        if expand:
            f.rowconfigure(1, weight=1)
        parent.rowconfigure(row, weight=1 if expand else 0)
        tk.Label(f, text=title, bg=COLOR_CARD, fg=COLOR_ACCENT,
                 font=FONT_SECTION, anchor='w').pack(fill='x', padx=12, pady=(8, 0))
        # 细分隔线
        tk.Frame(f, bg=COLOR_BORDER, height=1).pack(fill='x', padx=12, pady=(2, 0))
        return f

    # ---------- 选择 ----------
    def _pick_folder(self):
        d = filedialog.askdirectory(title="选择角色卡所在文件夹")
        if d:
            self._target = d
            self._single_file = None
            self.lbl_target.config(text=d, fg=COLOR_TEXT)
            self.lbl_mode.config(text="模式：处理整个文件夹")
            self._enable_clear()

    def _pick_file(self):
        f = filedialog.askopenfilename(
            title="选择单个角色卡（PNG）",
            filetypes=[("PNG 角色卡", "*.png"), ("所有文件", "*.*")])
        if f:
            self._target = os.path.dirname(f)
            self._single_file = os.path.basename(f)
            self.lbl_target.config(text=f, fg=COLOR_TEXT)
            self.lbl_mode.config(text=f"模式：仅处理单张「{self._single_file}」")
            self._enable_clear()

    def _clear_target(self):
        self._target = None
        self._single_file = None
        self.lbl_target.config(text="尚未选择目标", fg=COLOR_TEXT_SUB)
        self.lbl_mode.config(text="")
        self.btn_clear.config(state='disabled', bg="#e2e8f0")

    def _enable_clear(self):
        self.btn_clear.config(state='normal', bg="#94a3b8")

    # ---------- 日志 ----------
    def _log_line(self, text, tag=''):
        self.log.configure(state='normal')
        if tag:
            self.log.insert('end', text + '\n', tag)
        else:
            self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    # ---------- 执行 ----------
    def _on_run(self, dry=False):
        if not self._target or not os.path.isdir(self._target):
            messagebox.showwarning("提示", "请先选择文件夹或角色卡。")
            return
        recursive = self.var_recursive.get()
        move = self.var_move.get()

        self._clear_log()
        self.var_status.set("正在扫描…" + ("（预览模式）" if dry else ""))
        self._set_buttons('disabled')

        def work():
            try:
                # 单文件模式：强制不递归，避免误改子目录同名文件
                items = core.collect_items(self._target,
                                           recursive=(recursive and not self._single_file))
                if self._single_file:
                    items = [(f, fn, info) for (f, fn, info) in items
                             if fn == self._single_file]
                actions = core.build_plan(items, move_nochara=move)
                n_rename = sum(1 for a in actions if a.status == 'RENAME')
                n_move = sum(1 for a in actions if a.status == 'NODATA_MOVE')
                n_same = sum(1 for a in actions if a.status == 'SAME')
                n_nobook = sum(1 for a in actions if a.status == 'NOBOOK')
                n_nodata = sum(1 for a in actions if a.status == 'NODATA')
                summary = (f"扫描完成：共 {len(actions)} 个 PNG 文件\n"
                           f"  待重命名：{n_rename}\n"
                           f"  非角色卡待移动：{n_move}\n"
                           f"  已是正确名：{n_same}\n"
                           f"  无世界书（保留原名）：{n_nobook}\n"
                           f"  无 chara 数据（不处理）：{n_nodata}")
                self.after(0, lambda: self._log_line(summary, 'info'))

                if n_rename == 0 and n_move == 0:
                    self.after(0, lambda: messagebox.showinfo("结果", "没有需要重命名的卡片。"))
                    self.after(0, self._done)
                    return

                if not dry:
                    msg = (f"将对 {n_rename} 张卡片重命名"
                           + (f"，并把 {n_move} 张非角色卡移入子文件夹" if n_move else "")
                           + "。\n是否继续？\n\n提示：可点击「撤销上次操作」还原。")
                    if not messagebox.askyesno("确认", msg):
                        self.after(0, lambda: self._log_line("用户取消。", 'info'))
                        self.after(0, self._done)
                        return

                total = len(actions)
                self.after(0, lambda: self.progress.configure(maximum=total, value=0))
                self.after(0, lambda: self.lbl_progress.config(text=f"0 / {total}"))

                def on_progress(done, t, act):
                    def upd():
                        self.progress.step(1)
                        self.lbl_progress.config(text=f"{done} / {t}")
                        tag = {
                            'RENAME': 'ok', 'SAME': 'same',
                            'NOBOOK': 'skip', 'NODATA': 'skip',
                            'NODATA_MOVE': 'move'
                        }.get(act.status, '')
                        label = {
                            'RENAME': f"[重命名] {act.fn}  ->  {act.target}",
                            'SAME': f"[无需改] {act.fn}",
                            'NOBOOK': f"[无世界书] {act.fn}",
                            'NODATA': f"[无数据跳过] {act.fn}",
                            'NODATA_MOVE': f"[非角色卡移走] {act.fn}  ->  {act.target}",
                        }.get(act.status, act.fn)
                        self._log_line(label, tag)
                    self.after(0, upd)

                stats = core.execute_plan(actions, dry_run=dry, on_progress=on_progress)
                ok, same, skip, moved = stats

                if not dry:
                    logp = core.write_log(self._target, actions, stats)
                    if logp:
                        self.after(0, lambda: self._log_line(f"日志已保存：{logp}", 'info'))

                finish = (f"完成。成功重命名 {ok} 张，"
                          f"无需改名 {same} 张，"
                          f"跳过 {skip} 张，"
                          f"非角色卡移动 {moved} 张"
                          + ("（预览模式，未实际改名）" if dry else ""))
                self.after(0, lambda: self._log_line(finish, 'info'))
                self.after(0, lambda: messagebox.showinfo("完成", finish))
            except Exception as e:
                self.after(0, lambda: self._log_line(f"出错：{e}", 'err'))
                self.after(0, lambda: messagebox.showerror("出错", str(e)))
            finally:
                self.after(0, self._done)

        threading.Thread(target=work, daemon=True).start()

    def _set_buttons(self, state):
        for b in (self.btn_run, self.btn_preview, self.btn_undo):
            b.config(state=state)

    def _done(self):
        self._set_buttons('normal')
        self.var_status.set("就绪")

    # ---------- 撤销 ----------
    def _on_undo(self):
        if not self._target:
            messagebox.showwarning("提示", "请先选择目标文件夹再撤销。")
            return
        hist = core.load_history(self._target)
        if not hist:
            messagebox.showinfo("撤销", "该文件夹没有可撤销的历史记录。")
            return
        n = len(hist)
        if not messagebox.askyesno("确认撤销",
                                   f"将撤销 {n} 项重命名，恢复原文件名。\n是否继续？"):
            return
        ok, fail = core.undo_from_history(self._target)
        self._log_line(f"撤销完成：成功 {ok} 项，失败 {fail} 项。", 'info')
        messagebox.showinfo("撤销", f"成功 {ok} 项，失败 {fail} 项。")
        self.var_status.set("已撤销")


def main():
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()