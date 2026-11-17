# GPU 加速环境安装说明（CUDA 版 PyTorch）

> 本文记录数字人推理从 CPU 切换到 GPU 的完整过程，包含版本选择、下载源、安装命令、验证方法与常见坑。
> 适用于 Windows + NVIDIA 显卡环境。实测环境：RTX 4060 Laptop（8 GB 显存）。

---

## 1. 先判断到底需不需要 GPU

LiveTalking（Wav2Lip）在 CPU 上推理的实测表现：

| 环境 | 推理帧率 | 主观体验 |
|------|---------|---------|
| CPU（20 线程，modelres 160，batch_size 8） | 5 ~ 6 fps | 声音断续、口型跟不上 |
| GPU（RTX 4060，modelres 192，batch_size 16） | 25 fps（推流上限） | 连贯 |

推流目标就是 25 fps（每帧预算 40 ms）。CPU 单帧需要 160~190 ms，必然掉帧；GPU 单帧在 40 ms 以内，所以"卡"的问题能被根治，而不是缓解。

判断命令：

```powershell
py -3.12 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

- 输出 `2.x.x+cpu False` → 装的是 CPU 版，需要按本文重装
- 输出 `2.x.x+cu1xx True` → 已经是 GPU 版，可直接跳到第 5 节调参

> 注意：不要只看 `nvidia-smi` 能显示显卡就以为 GPU 可用。`nvidia-smi` 正常只说明**驱动**装好了；PyTorch 能不能用 GPU，取决于 torch 的构建版本是不是 CUDA 版。

---

## 2. 版本选择原则

**要让 torch 的版本号与项目现有版本保持一致，只把 `+cpu` 换成 `+cu1xx`。**

原因：项目里其他依赖（numpy、opencv、transformers）已经按当前 torch 版本验证过，换大版本容易连锁升级，风险远大于收益。

本项目的实际情况：

| 包 | 原（CPU） | 换（CUDA） |
|----|-----------|------------|
| torch | 2.14.1+cpu | **2.14.1+cu126** |
| torchvision | 0.29.1+cpu | **0.29.1+cu126** |

CUDA 版本选 `cu126` 的依据：显卡驱动为 566.24（驱动端支持到 CUDA 12.7），cu126 向下兼容，不需要升级驱动。

---

## 3. 下载 wheel（国内网络的关键一步）

`download.pytorch.org` 在国内基本不可用（实测代理 24 KB/s、直连经常 reset，2.6 GB 需要数小时）。

**可用镜像：阿里云 PyTorch wheels 镜像**，实测单线程 2.2 MB/s（约 20 分钟下完 2.6 GB）。

```powershell
# 建目录（不要放 C 盘）
New-Item -ItemType Directory -Force "D:\code.agent\torch_cu126" | Out-Null
Set-Location "D:\code.agent\torch_cu126"

# torch（约 2.6 GB）
curl.exe -L --retry 5 -o "torch-2.14.1+cu126-cp312-cp312-win_amd64.whl" `
  "https://mirrors.aliyun.com/pytorch-wheels/cu126/torch-2.14.1%2Bcu126-cp312-cp312-win_amd64.whl"

# torchvision（约 6 MB）
curl.exe -L --retry 5 -o "torchvision-0.29.1+cu126-cp312-cp312-win_amd64.whl" `
  "https://mirrors.aliyun.com/pytorch-wheels/cu126/torchvision-0.29.1%2Bcu126-cp312-cp312-win_amd64.whl"
```

下完先校验 zip 完整性（wheel 本质是 zip，下载中断会是坏包）：

```powershell
py -3.12 -c "import zipfile; z=zipfile.ZipFile(r'D:\code.agent\torch_cu126\torch-2.14.1+cu126-cp312-cp312-win_amd64.whl'); print(z.testzip(), len(z.namelist()))"
```

`testzip()` 返回 `None`、条目数正常即时完整。

> 多线程分片下载不要用：实测阿里云镜像会限速并发连接，8 线程反而全 0 进度。

---

## 4. 安装

**安装前必须先停掉 LiveTalking**（它加载着 torch 的 DLL，不停会文件占用导致安装失败）。

```powershell
# 停掉占用 8010 的进程（PID 用 netstat 查）
netstat -ano | Select-String ":8010 "
Stop-Process -Id <PID> -Force

# 安装：--no-deps 是必须的，避免 numpy/pillow 被连带升级
py -3.12 -m pip install --no-deps --force-reinstall `
  "D:\code.agent\torch_cu126\torch-2.14.1+cu126-cp312-cp312-win_amd64.whl" `
  "D:\code.agent\torch_cu126\torchvision-0.29.1+cu126-cp312-cp312-win_amd64.whl"
```

参数说明：

- `--no-deps`：只装这两个包，不动 numpy / pillow / packaging 等已装依赖。**漏掉这个参数，pip 会把 numpy 从 2.2.x 升到 2.5.x，可能直接打断项目的其它模块**
- `--force-reinstall`：同名同版本（都是 2.14.1）时必须强制，否则 pip 会判定 `Requirement already satisfied` 而跳过，装完仍是 CPU 版

安装成功应看到：

```
Successfully installed torch-2.14.1+cu126 torchvision-0.29.1+cu126
```

可能出现的警告（无害）：`Failed to remove contents in a temporary directory '...\~orch'`。这是卸载旧版时的残留，可手工删除 `D:\Python\Lib\site-packages\~orch`、`~orchvision` 目录。

---

## 5. 验证与启动

### 5.1 验证 CUDA 可用

```powershell
py -3.12 -c "import torch, torchvision; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.version.cuda)"
```

期望输出：

```
2.14.1+cu126
True
NVIDIA GeForce RTX 4060 Laptop GPU
12.6
```

### 5.2 启动 LiveTalking

GPU 可用后就**不需要再降分辨率和批大小**，直接用默认值即可：

```powershell
# 目录：third_party\LiveTalking
# TTS 用 qwentts，必须先注入 DashScope Key
$env:DASHSCOPE_API_KEY = (Get-Content "..\..\.env" | Where-Object { $_ -match '^DASHSCOPE_API_KEY=' }) -split '=',2 | Select-Object -Skip 1

py -3.12 app.py --listenport 8010
```

推理参数对照：

| 场景 | modelres | batch_size |
|------|----------|------------|
| GPU 可用 | 192（默认） | 16（默认） |
| 仅 CPU（回退） | 160 | 8 |

### 5.3 确认真的在用 GPU

启动日志里必须出现这一行：

```
INFO:utils.logger:Using cuda for inference.
```

再看显存占用（模型常驻约 2.3 GB）：

```powershell
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
```

---

## 6. 常见坑

| 现象 | 原因 | 处理 |
|------|------|------|
| `pip install` 卡在下载不动 | 官方源被墙 / 代理过慢 | 用阿里云镜像下 wheel 后本地安装 |
| 装完 `cuda.is_available()` 仍是 False | 同名版本 pip 判定 already satisfied | 必须加 `--force-reinstall` + 本地 wheel 路径 |
| 装完项目其它模块报 numpy 错误 | 少了 `--no-deps`，numpy 被升级 | 回滚 numpy，或重装时加 `--no-deps` |
| 安装时报文件被占用 | LiveTalking 正在跑 | 先停服务再装 |
| 长时间推理后报 `DeviceRemovedError` | Windows TDR：单 kernel 超时约 2 秒，驱动重置 | 插电 + 高性能模式，别把 batch 开太大 |
| 显存不够 / 第二个模型加载失败 | 8 GB 显存，wav2lip 已占约 2.3 GB | 一次只跑一个数字人实例，关掉其它吃显存的程序 |
| 首次 `import torch` 卡好几秒 | CUDA context 初始化（ms~s 级，远慢于 CPU 上下文切换） | 属正常现象，服务启动时预热即可 |

---

## 7. 记录

| 项 | 值 |
|----|----|
| 安装日期 | 2026-11-15 |
| torch / torchvision | 2.14.1+cu126 / 0.29.1+cu126 |
| 显卡 | NVIDIA GeForce RTX 4060 Laptop，8188 MiB |
| 驱动版本 | 566.24（CUDA 12.7） |
| 实测帧率 | CPU 5~6 fps → GPU 25 fps |
| 显存占用 | 启动后约 2304 MiB |
