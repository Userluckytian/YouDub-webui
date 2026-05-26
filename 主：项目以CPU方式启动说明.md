# YouDub WebUI 项目采用【CPU】的方式启动的说明

本文档提供了手动下载和配置项目所需资源的详细说明，适用于网络环境受限或希望提前准备资源的用户。

## 环境要求

### 软件版本要求

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| **操作系统** | Windows 10/11 | 推荐使用 PowerShell 5.1+ |
| **Python** | 3.12.x | 通过 pyenv-win 管理，项目本地版本 |
| **Node.js** | 20+ | 建议使用 v22.x 或更高版本 |
| **FFmpeg** | 任意最新版本 | 需要 full_build-shared 版本 |

### Python依赖包主要版本

项目会自动安装以下主要依赖包（通过 `requirements.txt`）：
- torch（PyTorch深度学习框架）
- torchcodec（视频编解码，依赖FFmpeg DLL）
- fastapi（Web框架）
- uvicorn（ASGI服务器）
- openai（OpenAI API客户端）
- voxcpm（语音合成）
- modelscope（模型下载）
- 其他音频处理库


## 重要说明

本项目不要求安装特定版本的Python，而是使用Python版本管理器来管理项目依赖。所有Python环境都只在项目文件夹下处理，不会影响系统全局Python环境。

## 一、Python版本管理器安装（必需）

### 安装 pyenv-win

**用途**：Python版本管理器，用于在项目目录下管理不同版本的Python

**安装命令**（PowerShell）：
```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"
&"./install-pyenv-win.ps1"
```

**安装后配置**：
1. 关闭并重新打开PowerShell
2. 验证安装：`pyenv --version`
3. 配置镜像源（华为云，国内访问更快）：
   ```powershell
   # pyenv-win 默认已配置华为云镜像，无需手动配置
   # 如果需要检查或修改，编辑以下文件：
   # C:\Users\你的用户名\.pyenv\pyenv-win\.versions_cache.xml
   # 全局搜索： https://xxxxxxx/python
   # 全部替换成华为云镜像：
   # https://mirrors.huaweicloud.com/python
   ```
4. 安装Python 3.12：`pyenv install 3.12.7`
5. 在项目目录下设置本地Python版本：
   ```powershell
   cd YouDub-webui
   pyenv local 3.12.7
   ```
---


## 二、需要下载的内容

### 1. FFmpeg（必需）

**用途**：视频处理、音频转换

**下载地址**：
- https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.0.1-full_build-shared.7z

**放置目录**：
- 下载后，解压到任意目录，例如：`D:\Program Files\ffmpeg`
- 将 `D:\Program Files\ffmpeg\bin` 添加到系统 PATH 环境变量

**安装测试**：
```powershell
ffmpeg -version
```
如果显示版本信息，说明安装成功。

**注意事项**：
- 必须下载 `full_build-shared` 版本（检查解压后，bin目录是否包含DLL文件，因为本项目采用的torchcodec是动态链接DLL的，不然会报错）

---

### 2. Xget Now 浏览器插件（如果你的代理速度不快，推荐使用这个加速插件下载。如果你没有这个问题，请跳过这一小节）

**用途**：加速一些常用网站的下载，比如github，gitlab，huggingFace等

**下载地址**：
- Edge 浏览器：https://microsoftedge.microsoft.com/addons/detail/xget-now/jigpfhbegabdenhihpplcjhpfdcgnalc?hl=zh-CN
- Chrome 浏览器：https://chromewebstore.google.com/detail/xget-now/ajiejgobfcifcikbahpijopolfjoodgf?hl=zh-CN

**安装说明**：
- 根据浏览器选择对应的下载地址
- 安装插件到浏览器

**使用方法**：
1. 先关闭自己的代理软件（如 Clash、V2Ray 等）
2. 打开 Xget Now 浏览器插件
3. 开始下载模型或者文件

---

### 3. 下载Whisper 语音识别模型：large-v3-turbo.pt（必需）

**用途**：语音识别和字幕生成

**下载地址**：
- ModelScope（推荐，国内访问更快）：https://www.modelscope.cn/models/iic/Whisper-large-v3-turbo/file/view/master/large-v3-turbo.pt?status=2
- OpenAI CDN：https://openaipublic.azureedge.net/main/whisper/models/aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a/large-v3-turbo.pt

**文件大小**：约 1.5GB

**放置目录**：
- 项目根目录下的 `models` 文件夹
- 完整路径：`YouDub-webui\models\large-v3-turbo.pt`

**环境变量配置**：
在 `.env` 文件中添加：
```env
WHISPER_MODEL=large-v3-turbo
WHISPER_DOWNLOAD_ROOT=./models
```

---

### 4. VoxCPM TTS 模型（可选，首次运行自动下载）

**用途**：生成目标语言配音

**下载地址**：
- ModelScope：https://www.modelscope.cn/models/OpenBMB/VoxCPM2 (可以不下载，代码运行时找不到会自己下载，因为是国内地址，所以一般不会出现下载报错的问题，如果下载报错就手动下载)
- **注意**：下载链接的最后部分`OpenBMB/VoxCPM2`就是模型ID，需要配置到环境变量中

**文件大小**：约 3-5GB

**放置目录**：
- 默认自动下载到：`YouDub-webui/data/modelscope/OpenBMB__VoxCPM2`

**手动下载配置（仅在自动下载失败时需要）**：
如果代码运行时自动下载失败，可以手动下载并配置：

1. 从 ModelScope 下载 VoxCPM2 模型文件
2. 将下载的模型文件夹解压到任意目录，例如：`D:\VoxCPM2`
3. 在 `.env` 文件中添加以下配置：
   ```env
   VOXCPM_MODEL_DIR=D:\VoxCPM2
   ```
4. 重启后端服务，程序会从指定目录加载模型

**注意**：一般情况下不需要手动下载，代码会自动从国内ModelScope地址下载，速度较快。

**环境变量配置**：
```env
# 模型ID：指定使用ModelScope上的哪个VoxCPM模型
VOXCPM_MODEL=OpenBMB/VoxCPM2

# 是否加载降噪器（false=不加载，提高速度；true=加载，提高音质）
VOXCPM_LOAD_DENOISER=false

# 推理参数（保持默认即可）
VOXCPM_CFG_VALUE=2.0
VOXCPM_INFERENCE_TIMESTEPS=10
VOXCPM_MIN_REFERENCE_MS=1200
```

**说明**：
- `VOXCPM_MODEL`：ModelScope上的模型ID，格式为`组织名/模型名`
- `OpenBMB/VoxCPM2`：这是OpenBMB组织发布的VoxCPM2模型
- 如果使用其他版本，可以修改这个ID，例如`OpenBMB/VoxCPM2-v2`

---

### 5. Demucs 音频分离模型（可选，首次运行自动下载）

**用途**：分离人声和背景音

**下载地址**：
- Hugging Face：https://huggingface.co/facebook/demucs(可以不下载，代码运行时找不到会自己下载，因为是国内地址，所以一般不会出现下载报错的问题，如果下载报错就手动下载)

**文件大小**：约 500MB

**放置目录**：
- 自动下载到系统缓存目录
- 也可通过 git submodule 管理：`./submodule/demucs`

---

### 6. FunASR 语音识别模型（可选，首次运行自动下载）

**用途**：替代 Whisper 的语音识别方案

**下载地址**：
- ModelScope：https://www.modelscope.cn/models/iic/SenseVoiceSmall(可以不下载，代码运行时找不到会自己下载，因为是国内地址，所以一般不会出现下载报错的问题，如果下载报错就手动下载)

**文件大小**：约 200MB

**放置目录**：
- 默认自动下载到：`YouDub-webui/data/modelscope/iic__SenseVoiceSmall`

**环境变量配置**：
```env
FUNASR_MODEL=iic/SenseVoiceSmall
FUNASR_VAD_MODEL=fsmn-vad
```

---

## 三、项目启动步骤

### 1. 基础环境检查

```powershell
# 检查 pyenv-win 版本
pyenv --version

# 检查项目本地Python版本
python --version

# 检查 Node.js 版本（需要 20+）
node --version

# 检查 FFmpeg
ffmpeg -version
ffprobe -version
```

### 2. 安装 Python 依赖

```powershell
# 在项目根目录下
# 创建虚拟环境（如果还没有）
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\activate

# 安装依赖（使用阿里云镜像加速）
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
```

**说明**：
- 虚拟环境会创建在项目目录下的`.venv`文件夹
- 所有Python包都安装在虚拟环境中，不影响系统全局环境
- 使用阿里云镜像可以加速pip下载
- 主要依赖包括：torch、torchcodec、fastapi、uvicorn、openai、voxcpm、modelscope等

### 3. 安装前端依赖

```powershell
cd apps/web
npm install
cd ../..
```

### 4. 基础配置

在项目根目录的`.env`文件中配置以下必需项（如果.env文件不存在，可以从`env.txt.example`复制）：

```env
# 设备配置（CPU模式）
DEVICE=cpu

# OpenAI API 配置（翻译用）
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=glm-4-flash
OPENAI_TRANSLATE_CONCURRENCY=1

# 模型缓存目录
MODEL_CACHE_DIR=./data/modelscope
```

**说明**：
- `DEVICE=cpu`：强制使用CPU模式（如果有GPU可改为`cuda`）
- `OPENAI_TRANSLATE_CONCURRENCY=1`：翻译并发数，免费账户建议设为1
- 其他模型配置已在前面各模型下载章节中说明

### 5. 启动后端服务

```powershell
# 在项目根目录下
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 启动前端服务

```powershell
# 在项目根目录下
cd apps/web
npm run dev
```

### 7. 访问应用

打开浏览器访问：http://localhost:3000

---

## 五、Windows 兼容性修复（已修复）

以下Windows兼容性问题已在代码中修复，无需手动操作：

### 1. Demucs 进度条错误
**已修复**：`backend/app/adapters/demucs.py` 中已禁用进度条（`progress=False`），避免Windows下的tqdm兼容性问题。

### 2. VoxCPM print 错误
**已修复**：`backend/app/adapters/voxcpm.py` 中已添加标准输出重定向，避免Windows下的print兼容性问题。

---

## 六、常见问题

### 1. 智谱AI 速率限制

**错误**：`Error code: 429 - 您的账户已达到速率限制`

**解决**：在 `.env` 文件中降低翻译并发数：
```env
OPENAI_TRANSLATE_CONCURRENCY=1
```

### 2. 端口占用

**错误**：`Error: listen EADDRINUSE: address already in use`

**解决**：
```powershell
# 查找占用端口的进程
netstat -ano | findstr :8000
netstat -ano | findstr :3000

# 终止进程
taskkill /F /PID <进程ID>
```

### 3. 模型下载失败

**解决**：手动下载模型文件并按照上述说明放置到指定目录，配置相应的环境变量。

---

## 七、资源汇总表

| 资源名称 | 用途 | 大小 | 下载地址 | 放置目录 | 是否必需 |
|---------|------|------|---------|---------|---------|
| FFmpeg | 视频处理 | ~100MB | [下载链接](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.0.1-full_build-shared.7z) | 自定义目录 | 必需 |
| Xget Now 浏览器插件 | 加速视频下载 | ~1MB | [Edge](https://microsoftedge.microsoft.com/addons/detail/xget-now/jigpfhbegabdenhihpplcjhpfdcgnalc?hl=zh-CN) / [Chrome](https://chromewebstore.google.com/detail/xget-now/ajiejgobfcifcikbahpijopolfjoodgf?hl=zh-CN) | 浏览器插件 | 推荐 |
| Whisper | 语音识别 | ~1.5GB | [ModelScope](https://www.modelscope.cn/models/iic/Whisper-large-v3-turbo/file/view/master/large-v3-turbo.pt?status=2) | `./models/` | 必需 |
| VoxCPM | 配音生成 | ~3-5GB | [ModelScope](https://www.modelscope.cn/models/OpenBMB/VoxCPM2) | `./data/modelscope/` | 必需 |
| Demucs | 音频分离 | ~500MB | [Hugging Face](https://huggingface.co/facebook/demucs) | 自动下载 | 可选 |
| FunASR | 语音识别 | ~200MB | [ModelScope](https://www.modelscope.cn/models/iic/SenseVoiceSmall) | `./data/modelscope/` | 可选 |

---

## 八、磁盘空间需求

- 基础项目文件：~500MB
- Whisper 模型：~1.5GB
- VoxCPM 模型：~3-5GB
- Demucs 模型：~500MB
- 工作目录（处理视频时）：~1-5GB（取决于视频大小）

**总计建议预留空间**：至少 10GB

---

## 九、网络要求

- 访问 GitHub（项目克隆、Demucs 模型）
- 访问 ModelScope（VoxCPM、FunASR 模型）
- 访问 OpenAI API 或兼容服务（翻译）
- 访问 YouTube/Bilibili（视频下载，需要代理）

如果网络环境受限，建议手动下载上述模型文件。

---

**生成时间**：2026-05-26
