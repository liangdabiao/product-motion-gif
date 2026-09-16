---
name: product-motion-gif
description: 把一张（或多张）产品图/场景图变成可循环的动图。原理是让 GPT-Image 2.5 一次性生成 4x4 多格帧图，再切帧、修循环缝、按节奏合成 GIF/WebP/MP4。适用于电商主图、详情页、投放素材的产品环绕/悬浮动效。触发词：产品动图、产品 GIF、环绕动图、旋转动图、多格图、frame sheet、turntable gif、product animation。
agent_created: true
---

# product-motion-gif

产品图/场景图 → 可循环动图。核心是 GPT-Image 2.5 的一致性：**一次生成 4x4=16 帧多格图**，
再切帧合成。不要一帧一次生成——那样漂移严重且贵。

## 什么时候用

- 用户给产品图或场景图，要"动起来"的展示素材（环绕、旋转、悬浮）。
- 输出目标：微信/详情页可用的 GIF、现代平台用的 WebP、投放用的 MP4。

**不适合**：多主体互动、复杂剧情动作、刁钻运镜、需要 48 帧以上的长动画。
GPT-Image 2.5 只在「**透明或纯色背景 + 单主体 + 简单动作**」下稳定，越界就会随机抖动、
画面漂移，甚至出现生物/物理准确性错误。

## 前置条件

- `apiz` CLI 已安装并登录（`apiz auth status`）。模型见下"模型选择"。
- Python 需 `Pillow`、`numpy`；MP4 需要 `ffmpeg`。
- Windows 上若 `bash` 报 `head/ls: command not found`，先补 PATH：
  `export PATH="/c/Windows/System32:/c/Windows:/c/Users/49707/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH"`

## 模型选择（省钱技巧）

| 模型 | 用途 | 实测成本（high/2K） |
|---|---|---|
| `apiz/gpt-image-2.5-flare` | **试 prompt 阶段默认用这个** | 16:9 → 39 points；4:3 → 53 points |
| `apiz/gpt-image-2.5-sunburst` | 定稿出正式版 | 约为 Flare 的 2 倍（16:9 → 78 points） |

两者参数完全相同，改 `--model` 即可切换。**试错一律走 Flare。**

### 尺寸档位：别用 4K（花钱买不到清晰度）

`--size 4K` 并**不是原生 4K 生成**。实测（Flare / high / 4:3 / 4K）：

```
"upstream_width": 2048, "upstream_height": 1536    ← 上游其实只生成 2K
"target_width":   3264, "target_height":   2448    ← 放大 1.59 倍交差
"scale": 1.5938
```

也就是说 4K 档 = **2K 结果做插值放大**，信息量不变，成本却从 53 → **133 points（2.5 倍）**。

实测同一素材、同样输出 640×480 的锐度对比：

| 素材来源 | 拉普拉斯锐度 | 高频能量占比 |
|---|---|---|
| 2K → 640 | 22.35 | 51.4% |
| 4K → 640 | 23.08（+3.3%） | 52.9% |

差异在噪声量级，肉眼不可辨。**结论：固定用 `--size 2K`，不要用 4K。**
单格 512px 是硬上限，想要更大的成品只能靠 3×3 网格（单格 682px）换取，
代价是帧数少、流畅度下降。

## 标准流程

```bash
SK="D:/image25/.workbuddy/skills/product-motion-gif"
PY="C:/Users/49707/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# 1. 参考图入库，拿公网 URL（apiz 只吃 URL，不吃本地路径）
apiz upload ./product.jpg --folder myproj
#    -> https://cdn-hk.51sux.com/storage/myproj/....jpg
#    外链图可直接转存：apiz transfer "<url>"

# 2. 生成 4x4 多格图（prompt 用 prompts/ 下的模板，按主体改前两段）
#    画幅跟随原图：原图方形→1:1，4:3→4:3，长扁场景→16:9
"$PY" "$SK/scripts/apiz_image.py" \
  --ref "<上一步的 URL>" \
  --prompt-file "$SK/prompts/orbit60-4x4.txt" \
  --out out/sheet.json --model apiz/gpt-image-2.5-flare \
  --quality high --size 2K --ratio 4:3

# 3. 切帧编号，先给人看多格图质量（这一步不能省，人才是验收标准）
"$PY" "$SK/scripts/contact_sheet.py" out/sheet.jpg out/contact.png 4 4 480
"$PY" "$SK/scripts/motion_smooth.py" out/sheet.jpg 4 4      # 客观量化"抖不抖"

# 4. 切帧 + 合成
"$PY" "$SK/scripts/make_gif.py" --sheet out/sheet.jpg --outdir out/run1 \
  --rows 4 --cols 4 --canvas tight --bg auto --loop pingpong \
  --keep-frames --quality-report out/run1/qa.json
```

产物：`animation.gif`、`animation.webp`、`animation.mp4`，加 `frames/` 和 `qa.json`。
（`--size 640 --timing ramp --duration 70 --ramp 2.6,0.7,1.8 --max-kb 3000` 都已是默认值，
不用重复写。）

## 八条硬规则

**前两条是已验收的效果标准，改动前先问用户。**

1. **展示类环绕默认 60°，不要 180°、也不要用 90°。**
   用户实测验收顺序：180° 太大（会依次看到正面→侧面→背面，不是"正面展示"）→
   90° 仍偏大 → **60° 通过**（正面 → 三分之四视角）。
   prompt 里写死：`cell 1 = 0° 正面`，`cell 16 = 恰好 60°`，`15 步 × 4°`。
   注："环绕"指**相机绕场景转**，不是模型自转；"正面环绕"的边界是**不越过正侧面、绝不露背面**。

2. **合成默认用"前慢后快"节奏（`--timing ramp`，已是默认）。**
   用户要求：**开头慢、逐渐加快**，让观众看清起始画面。
   默认形状 `--ramp 2.6,0.7,1.8` + `--duration 70`，实测 30 帧停留时长：
   `180×6 → 170×4 → 160×2 → 150×3 ... → 70×2 → 60×2`，总约 4.0 秒。
   `--timing even` 是备选（按每格实际变化量分配时间，追求恒定速度感时才用）。

3. **旋转/环绕类必须 `--loop pingpong`。**
   16 帧只覆盖单程角度，正向播完再镜像回退才无缝（共 30 帧）。用 `auto` 会退化成
   `cycle`，接缝处硬跳。原因：旋转被判为 `pose-change`，而 `halfloop` 只在
   `kind == "translation"` 时生效，`loopcut` 找不到匹配姿态。

4. **默认不要逐帧稳像（`--stabilize off`，已是默认值）。**
   这是最容易踩的坑：逐帧稳像给每一帧算一个**不同**的位移量，"漂移估计误差"直接变成
   帧间抖动。实测一张真实环绕图：pose jitter 指数 **1.87（原始）→ 2.22（开稳像）→
   1.88（关掉）**。它非但没让画面更稳，反而制造了抖动。
   注意：环绕时主体本来就会横向位移，**这是真实视差，不要拿稳像去抹平它**。
   只需要整体重新居中时用 `--stabilize anchor`——一次性常量偏移，帧间关系完全保留。

5. **prompt 里禁止分阶段描述镜头，要用"线性插值 + 每格增量相同"。**
   写成"第 1–4 格近景、第 5–11 格后拉、第 12–16 格全景"，模型就会在阶段交界处猛变
   （实测第 3→4 格明显跳变）。正确写法是把 16 格定义成**一次连续运动的 16 个等时间采样**：
   "cell 1 是起点，cell 16 是终点，中间的每一格恰好落在同一条线性插值的等比位置上；
   任意相邻两格之间的变化量完全相同；全程没有加速、停顿、快段或慢段"。

6. **prompt 必须写明"是相机在环绕，不是模型在自转"，并用数字封顶。**
   否则模型会去转模型本身，几何会崩。同时钉死：固定距离/高度/焦距、地平线不漂、
   全程恰好 N 度、分成等步、**每格主体完整不出格**、场景内每个物体的形状位置颜色不变、
   纯色无缝背景、无文字水印边框。
   量化封顶比定性描述有效得多，例如：`apparent size changes by less than 5%`、
   `max 8% horizontal travel`。

7. **稳像若真的开启，填充色必须是不透明画布色，否则出黑边。**
   `shift_frame` 默认 `fill=(255,255,255,255)`。若填透明 `(0,0,0,0)`，
   后续 `convert("RGB")` 会把透明像素压成**纯黑**——这就是 GIF 边缘那道黑边。
   只有真正的透明底素材才传 `(0,0,0,0)`。
   同理 `quantize_frames` / `export_webp` 走 `flatten_rgb()` 合成到画布色，不要直接 convert。

8. **只做 4x4 / 16 帧；GIF 体积上限 3MB。**
   帧数越多漂移和抖动越明显，成本还翻倍。体积上用户明确 **3MB 可接受**
   （`--max-kb 3000`）。超出预算时阶梯会先降尺寸再降色数，**最低不要跌破 460px/96 色**
   （那个档位明显发糊）；宁可放宽预算，也不要用糊的档位交付。
   注意 2K 生成 + 4x4 时单格只有 512px，所以 640px 是放大得来的；细节密集的素材
   在 3MB 内通常只能保住 **544px** 左右，交付时把实际尺寸说清楚。
9. **多张参考图时，在 prompt 里写清每张的职责。** 实测「外观图 + 剖面图」一起喂时，
   模型会默认把**剖面图也画进画面**。必须显式分工：
   `Image 1 (exterior) is the MAIN VIEW` / `Image 2 (cutaway) is the STRUCTURE REFERENCE
   ONLY - do NOT draw the cutaway, do NOT open up the walls`。

## 验收（最重要的一条）

**人是唯一验收标准，AI 自查不算数。** 流程必须是：

1. 生成完多格图 → **立刻**用 `contact_sheet.py` 出带帧号的检查表给用户看；
2. 合成完 → **立刻**用 `present_files` 把 GIF 交给用户；
3. **不要**在用户验收前就把"经验"写进本文件——没验收的优化是瞎优化；
4. 交付时说明**自己看到的疑点**，但不要替用户下结论。

## 判读 QA 报告

```jsonc
{
  "motion": {"kind": "pose-change", "area_cv": 0.06},  // 环绕=pose-change
  "loop": "pingpong",
  "border": {"mean_rgb": [139.5, 208.9, 253.0], "near_black_fraction": 0.0},
  "output": {"timing": "ramp", "dwell_ms": [180, 180, ...]},
  "verdict": "PASS | REVIEW"
}
```

- **黑边只认 `near_black_fraction`（接近纯黑的像素占比），不要用亮度判定。**
  稳像填充透明的特征是 RGBA→RGB 压成 `(0,0,0)`，真实主体/阴影/彩色背景**三个通道
  不会同时全黑**。之前的版本按"外圈亮度 < 235"判暗带，遇到**蓝色影棚背景**（RGB 约
  `140,209,253`，亮度天然只有 200）会 100% 误报，也会把"主体故意出画"误判成黑边。
  判定：`near_black_fraction > 2%` 才算真黑边。`mean_rgb` 是给人看的，用来确认外圈
  是不是背景色本身。
- `area_cv` 超过 12% → 主体在"变形"而不只是"移动"，多半是多主体或复杂动作。
  （60° 环绕实测 **6%** 左右；180° 全环绕会到 50%+，属正常。）
- `dwell_ms` 在 ramp 模式下应当**单调递减**；若成片顶在下限 60ms，说明收尾偏慢。
- 判断"抖"来自模型还是合成：`motion_smooth.py` 跑**多格图**得 `jitter_idx`（模型的责任），
  再跑**合成后的 frames/** 得另一个值。后者明显更高 = 合成环节在恶化，先查 `--stabilize`。
- **输出尺寸会被体积预算反推。** `--max-kb` 是硬预算：阶梯会从 `--size` 起逐级降尺寸、
  再降色数，直到塞进预算。所以 3MB 预算下不一定能拿到 640px —— 细节密集的素材
  （樱花树、砖墙纹理）压缩率低，可能落到 544px。**日志里 `gif ... (WxH ...)` 报的是实际
  落地尺寸**，要以它为准（曾有个 bug 把尺寸静默压回源单格宽度，导致 GIF 比同帧的 WebP 还小）。

## 文件

- `scripts/apiz_image.py` — apiz CLI 包装，生成多格图并落 JSON（`--model` 可切 flare/sunburst）。
- `scripts/giflab.py` — 库：切帧、遮罩、稳像（含 anchor）、节奏曲线（`even_durations` /
  `ramp_durations`）、循环修复、调色板、导出。
- `scripts/make_gif.py` — CLI：多格图进，GIF/WebP/MP4/QA 出。
- `scripts/contact_sheet.py` — 把多格图切成**带帧号的检查表**，交给用户逐帧验收。
- `scripts/motion_smooth.py` — 量化帧间均匀度（`jitter_idx`）。
- `scripts/verify_edges.py` — 按播放器合成方式量 GIF 边缘，验证黑边是否清净。
- `prompts/orbit60-4x4.txt` — **默认模板**：60° 相机环绕、方形/4:3 主体（已验收）。
- `prompts/turntable-180-4x4.txt` — 180° 环绕（单主体产品，历史版本）。
- `prompts/orbit-reveal-180-16x9.txt` — 宽幅场景 180° 环绕 + 后拉揭示，16:9（历史版本）。
