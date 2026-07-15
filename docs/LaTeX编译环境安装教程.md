# LaTeX 编译环境安装教程

本文档面向 **Windows 用户**，帮助安装 MiKTeX（xelatex 编译器），用于 AutoResearch 项目的 PDF 编译功能。

---

## 一、安装 MiKTeX

### 1. 下载

打开浏览器，访问：**https://miktex.org/download**

点击 **"Download Basic Installer"** 按钮，下载 `basic-miktex-xx.xx-x64.exe`（约 300 MB）。

### 2. 安装

运行下载的安装程序：

- **安装范围**：选择 **"Install MiKTeX for anyone who uses this computer"**（或 "Only for me" 均可）
- **安装路径**：保持默认即可
- **纸张大小**：选 **A4**
- **缺失包处理**：选 **"Yes"**（自动安装缺失的包）

其余选项保持默认，一路 Next 完成安装。

### 3. 验证

打开**新的** PowerShell 终端（安装程序刚结束时打开的终端不含新 PATH，需要开新窗口），输入：

```powershell
xelatex --version
```

看到类似以下输出即安装成功：

```
MiKTeX-XeTeX 4.16 (MiKTeX 25.12)
...
```

---

## 二、常用包预装（推荐）

首次编译论文时 MiKTeX 会自动下载缺失的包，但会弹窗确认。可以先手动装好常用包：

打开 PowerShell（MiKTeX 用户模式不需要管理员），运行：

```powershell
mpm --install=ctex
mpm --install=amsmath
mpm --install=booktabs
mpm --install=hyperref
```

或者一条命令装多个：

```powershell
mpm --install=ctex --install=amsmath --install=booktabs --install=hyperref --install=graphics --install=geometry
```

如果论文使用 IEEE 模板，还需装：

```powershell
mpm --install=ieeetran
```

> **注意：** MiKTeX 的包管理器叫 `mpm`（MiKTeX Package Manager），不是 `tlmgr`（那是 TeX Live 的）。

---

## 三、关闭更新提醒（可选）

MiKTeX 偶尔会提示"未检查更新"，不影响编译但可能干扰自动化流程。关闭方式：

```powershell
initexmf --set-config-value "[Core]NoUpdateCheck=1"
```

如需恢复：将 `1` 改为 `0`。

---

## 四、常见问题

### Q: xelatex 命令找不到？

关闭当前终端，**重新打开**一个新的 PowerShell。安装程序不会刷新已打开终端的 PATH。

如果仍然找不到，手动添加环境变量：
1. 搜索 → "编辑系统环境变量" → 环境变量
2. 在 **Path** 中添加 `C:\Users\<你的用户名>\AppData\Local\Programs\MiKTeX\miktex\bin\x64`

### Q: 编译时报 "package not found"？

这是首次使用时缺包。以**管理员**身份运行一次 xelatex，弹窗时点 Install 即可自动下载。

```powershell
# 以 test-paper 为例
xelatex main.tex
```

### Q: ctex 中文包报错？

ctex 依赖中文字体。如果缺少字体，安装以下任一款：
- 思源宋体（Source Han Serif）
- 或使用 Windows 自带的微软雅黑/宋体

### Q: 编译很慢？

首次编译需要下载缺失的包，之后会很快（通常 2-5 秒）。

---

## 五、在 AutoResearch 中使用

安装完成后，启动 AutoResearch 后端，前端点击"📄 编译 PDF"按钮即可。

编译产物在 `tasks/<项目名>/build/main.pdf`。

---

*最后更新: 2026-07-11*
