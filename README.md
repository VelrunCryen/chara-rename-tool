# 角色卡批量重命名工具

让 SillyTavern 角色卡（PNG 内嵌 V2/V3 JSON）按 **世界书名** 批量重命名的小工具。
适合小白用户，带图形界面、预览、撤销、日志功能。界面为浅色卡片式设计，分区清晰。

## 目录结构

```
chara_rename/
├─ CharaRenameTool.exe      ← 双击即用（普通用户只用这个）
├─ README.md                ← 本说明
└─ src/                     ← 开发者才用，普通用户可忽略
   ├─ chara_gui.py          GUI 主程序（tkinter 零依赖）
   ├─ chara_core.py         核心重命名/解析/撤销逻辑
   └─ run.bat               本机有 Python 时一键启动（调试用）
```

## 使用方式

### 普通用户（推荐）
直接双击根目录的 **`CharaRenameTool.exe`**，无需安装 Python。

### 开发者 / 本机已装 Python
进入 `src/` 目录双击 `run.bat`，或命令行：
```bash
cd src
python chara_gui.py
```

## GUI 操作流程

1. **① 选择目标**：
   - 点「选择文件夹」选角色卡所在文件夹（处理整个文件夹）
   - 或点「选择单张卡片」选一张 png（只处理这一张）
   - 选错可点「清除」重选，不锁定在原选择上
2. **② 选项**（勾选即生效）：
   - ☑ 包含子文件夹
   - ☑ 非角色卡自动移入「非角色卡」子文件夹（即纯立绘图归类整理）
3. **预览**：点「预览  只看不改」按钮 → 程序只列出将改的清单，**不动文件**，方便先核对
4. **开始重命名**：点「开始重命名」按钮 → 弹确认 → 真正改名
   - 执行中下方进度条与日志实时刷新
   - 颜色含义：绿=重命名 / 蓝=移入子文件夹 / 灰=无需改 / 橙=跳过 / 红=出错
5. **撤销上次操作**：撤销当前文件夹上次批量重命名（依据隐藏的 `.rename_history.json`，仅还原成功的项）
6. 日志会自动保存到目标目录：`重命名日志_时间戳.txt`

## 重新打包成 exe（开发者用）

需先 `pip install pyinstaller`，在 `src/` 目录执行：
```bash
cd src
pyinstaller -F -w --noconfirm --name CharaRenameTool chara_gui.py
```
产物在 `src/dist/CharaRenameTool.exe`，把它剪切回根目录即可。

## 支持格式
- PNG `tEXt` / `zTXt` / `iTXt` chunk 中的 `chara` 字段（base64 编码 JSON）
- 兼容 Character Card V2 与 V3

## 安全机制
- 重命名前置确认；命名冲突不覆盖，自动加 `(2)/(3)` 后缀
- 生成 `.rename_history.json` 隐藏文件以支持撤销
- 撤销失败的项会保留在历史中以便再次尝试，不会丢失记录
- 生成带时间戳的日志 txt，便于事后核对

## 常见问题
- **点开始没反应**：先点「选择文件夹」
- **exe 闪退**：把 `CharaRenameTool.exe` 移出中文/空格特殊路径再试
- **重命名了想还原**：选中同一文件夹，点「撤销上次操作」