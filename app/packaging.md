# 打包说明 (Win / Mac)

## 依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

## 内置 ffmpeg

1. 从 [ffmpeg 官方构建](https://ffmpeg.org/download.html) 或 [BtbN builds](https://github.com/BtbN/FFmpeg-Builds/releases) 下载对应平台包。
2. 解压后将 `ffmpeg`、`ffprobe`（Windows 为 `ffmpeg.exe`、`ffprobe.exe`）放入项目根目录 `bin/`：

```
VideoCombining/
  bin/
    ffmpeg
    ffprobe
```

开发阶段未放置 `bin/` 时，会使用 `imageio-ffmpeg` 自带的 ffmpeg（通常不含 ffprobe，程序会回退解析 `ffmpeg -i` 输出）。

## 运行（开发）

```bash
python -m app.main
```

## PyInstaller

在项目根目录执行（推荐统一 spec，与 CI 一致）：

```bash
python -m PyInstaller VideoCombining.spec --noconfirm
```

- **macOS** 产物：`dist/VideoCombining.app`
- **Windows** 产物：`dist/VideoCombining.exe`（单文件）

CI 在 tag `v*` 推送后会自动打 **DMG** / **EXE** 并发布到 GitHub Releases，见仓库 `.github/workflows/build-release.yml`。

## 验证清单

- 启动后日志区显示 `ffmpeg: ffmpeg version ...`
- 混格式素材生成 1 条输出，日志含完整命令行
- 输出目录生成 `build_*.log` 与视频文件
