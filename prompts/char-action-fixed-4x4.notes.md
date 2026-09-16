# char-action-fixed-4x4.txt — 填写说明

**这是什么**：从零生成"一个角色做一套动作"的 4×4 多格图模板。**没有参考图**，
所以整份 prompt 就是画面的唯一来源——形容不到的，模型就自己编。

**什么时候用它**：用户说"生成一个 XX 在做 XX 的动图"（游戏人物、角色动作、招式特效、
吉祥物动作）。触发词：角色动图、人物动作、游戏人物、招式 GIF、sprite sheet。

**什么时候别用它**：
- 有参考图、要绕着转 → 用 `orbit60-l2r-4x4.txt`。
- 多主体互动 / 打斗 / 有剧情 → 本 skill 明确不适合，出图会崩（多个角色必漂移）。
- 需要 48 帧以上的长动作 → 16 帧装不下，考虑拆成两段分别生成。

---

## 填写顺序（重要）

**先写 `CHARACTER` 段，再写别的。** 这是硬规则 16 的同类要求：先指名主体，
模型才知道该在谁身上保持一致。三件事必须写死：

1. **身份**：谁、什么年龄体型、脸、以及**每一个穿戴件**——头冠/帽子、外袍、内衬、
   鞋子、佩饰，各自写清**颜色和材质**。不要写"传统服饰"，要写
   "a tall golden five-Buddha crown"、"a golden-and-crimson brocade kasaya robe over a
   white inner robe"。
2. **朝向 + 机位**：例如 "faces to the RIGHT, seen in three-quarter front view from slightly
   below eye level"。写死朝向能避免 16 格里人物忽左忽右。
3. **道具**：把道具当**刚体**写——**数给它**（"exactly nine rings"），
   并列出它永不变形（不弯、不变长、不掉环、不换成别的武器、不脱手漂浮）。
   道具一变，整段的"一致性"就废了。
4. **人口线**：`Exactly two arms, two hands and one <prop>. No helper, no monster, no second
   figure, no animal, no audience - nothing else in the picture is alive.`
   模型非常爱加人/加兽/加围观群众，这句不能省。

## 动作怎么写：一条弧，不是一张分镜表

**硬规则 5 在这里同样适用**：写成"1–4 格蓄力、5–9 格出手、10–16 格收招"，
模型会在阶段交界处猛跳。正确写法是把 16 格定义成**同一个连续动作的 16 个等时间采样**：

> 16 cells are 16 equal-time samples of ONE single unbroken motion... no cell repeats another,
> no pose is held across two cells, the motion never reverses.

然后只给**三个锚点格**（1 / 8 / 16）当"里程牌"，且每格只描述一句样子，
不要写成指令式的阶段安排。

**Cell 16 必须是循环缝**：让收招几乎落回 cell-1 的起手式、特效衰减成余辉。
这样合成时用 `--loop cycle` 就能无缝循环。若 cell 16 停在动作最猛的收势，
用 cycle 会硬跳，用 pingpong 会倒放（攻击倒放观感很怪）——**这是这个模板的默认取舍**。

## 相机必须写成"锁死"

这是和 orbit 模板**相反**的一条，最容易抄错：

| | orbit60-l2r-4x4 | char-action-fixed-4x4 |
|---|---|---|
| 相机 | 绕主体转 60° | **完全不动** |
| 背景 | **必须横移**（转动的唯一线索） | **纹丝不动** |
| 主体 | 居中不动，由背景承载转动 | 居中，**自己动** |

所以本模板里"主体居中、不逐格重新构图、不变尺寸"仍然是必须的，
但**绝不能**写"背景要横移 / 背景元素不许钉死"——那会把平涂底搅花。

## 出图与合成

```bash
SK="D:/image25/.workbuddy/skills/product-motion-gif"
PY="C:/Users/49707/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# 生成：不带 --ref 就是纯文本生成
"$PY" "$SK/scripts/apiz_image.py" \
  --prompt-file prompts/<你的填充版>.txt \
  --out out/<name>/sheet.json \
  --model apiz/gpt-image-2.5-flare --quality high --size 2K --ratio 4:3

# 合成：动作类用 cycle（cell16≈cell1 已闭环）。用 pingpong 会倒放。
"$PY" "$SK/scripts/make_gif.py" --sheet out/<name>/sheet.jpg --outdir out/<name>/run1 \
  --rows 4 --cols 4 --canvas tight --bg auto --loop cycle \
  --keep-frames --quality-report out/<name>/run1/qa.json
```

- **字符数**：模板本体 **5800 字符**（含占位提示），已贴近 6000 上限。
  `<<< >>>` 里的提示是**整段替换**掉的，填充后数字会变——**填完必须复测**；
  `apiz_image.py` 会自动打印 `[apiz_image] prompt chars: N` 并本地拦截超限。
- **画幅**：单角色全身 + 横向冲出去的特效 → `4:3`；只有站姿/竖向道具 → `2:3` 或 `1:1`。
- **`--size 2K` 是默认**；单格 4:3 时约 512×384，成品长边做 480 以内不用上 4K。
- 交付前先跑 `contact_sheet.py`（带帧号检查表）和 `ab_frames.py`（首尾格对比），
  **出图立刻给用户看，不要自己先下效果结论**（验收一节）。

## 已知风险与写法对策（预防性提示，非实测结论）

> 这一节是**基于模板结构推出来的风险清单**，用于出图后自查，**不是已验证的效果结论**。
> 后面实测确认过的才升格进 SKILL.md 硬规则。

- **人物会"变脸/换衣服"**：CHARACTER 段没把穿戴件写全。补齐颜色+材质+件数。
- **会多出手/多出人**：漏了人口线那句。
- **道具悄悄换掉**（锡杖变禅杖、法杖变剑）：要把道具当刚体 + 数特征 + 列禁止项。
- **动作中途"变档"**：把动作写成了阶段列表。改回"一条弧 + 三锚点"。
- **整体像 PPT 翻页**：锚点之间没有强调"每格变化量均匀"，要明写 equal samples。

## 实测记录

- 首个填充实例：`唐僧 + 九环锡杖聚气挥出金光`，国风 3D 游戏渲染 + 深墨蓝灰纯色底，
  4:3 / 2K / Flare，prompt 5204 字符。见工作区 `D:/image25/gif-lab/out/tangmonk/`。
