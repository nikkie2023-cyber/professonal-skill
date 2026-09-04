# Content Workbench Agent

一个面向短视频创作者的爆款视频拆解 Agent 本地 MVP。它支持视频上传或公开链接输入，并输出时间轴报告、可复刻/不可复刻判断和针对用户目标的改进建议。没有配置视频模型时使用 Mock 模式，方便先测试产品流程。

## 功能

- 视频上传与公开视频链接输入
- 带货 / 涨粉目标选择
- 时间轴拆解报告
- 可复刻性判断与用户改进建议
- 可选 DeepSeek 文本推理与 Qwen 视频理解
- 可选 FFmpeg 截图和 Excel 报告导出

## 项目结构

```text
app/
  main.py             Web 服务入口
  analyzer.py         视频分析编排
  providers.py        Mock / 文本模型 provider
  qwen_provider.py    Qwen 视频理解 provider
  script_generator.py 复刻脚本生成
  templates/          Web 页面
tests/                自动化测试
browser_extension/    浏览器扩展入口
data/                 本地上传与运行数据（不提交）
```

用户可以粘贴公开可访问的视频链接，也可以上传视频文件。链接由后端临时下载并处理；抖音/小红书分享链接可能因平台权限、登录或防爬限制失败。

## 运行

在本目录执行：

```powershell
$env:PYTHONPATH = "app"
python -m app.main
```

然后访问：`http://127.0.0.1:8000/`

首次运行建议创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 测试

```powershell
$env:PYTHONPATH = "app"
python -m unittest discover -s tests
```

## 真实截图

安装 FFmpeg 并确保 `ffmpeg` 和 `ffprobe` 在 PATH 中，重启服务后，报告会按时间轴生成截图并在页面展示。也可以在 `.env` 中设置 `FFMPEG_PATH` 和 `FFPROBE_PATH` 指向服务器上的可执行文件。仓库不会包含本地 FFmpeg 二进制文件；没有 FFmpeg 时报告会明确显示 `unavailable`，不会伪造截图。

## DeepSeek

复制 `.env.example` 为 `.env`，或在启动前设置环境变量：

```powershell
$env:USE_DEEPSEEK="true"
$env:DEEPSEEK_API_KEY="你的 Key"
$env:DEEPSEEK_MODEL="deepseek-chat"
```

DeepSeek 当前只作为文本推理层，负责根据时间轴和账号画像生成迁移建议。要让模型真实理解视频画面，还需要接入支持视频输入的模型，并把其输出接到 `app/analyzer.py` 的 provider 层。

## 安全提示

不要提交 `.env`、API Key、个人上传视频或生成的运行数据。请复制 `.env.example` 为 `.env`，并仅在本地填写密钥。

## Qwen 视频理解

设置：

```powershell
$env:QWEN_API_KEY="你的千问 Key"
$env:QWEN_MODEL="qwen3-vl-flash"
```

公开链接会直接传给 Qwen。小于约 8MB 的上传文件会以 Base64 发送；更大的上传文件需要先放到可公开访问的对象存储，后续可接入 OSS。Qwen 视觉视频模型主要负责画面理解；如果要识别原视频口播，需要再接入支持音频的视频模型或语音转写模型。
