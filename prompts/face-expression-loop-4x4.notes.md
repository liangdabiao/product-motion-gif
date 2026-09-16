# face-expression-loop-4x4.txt — 怎么填（表情包家族 / D 类）

给**一张人脸参考图**，做"同一个人做一整套夸张表情"的 16 格循环。产出物就是聊天表情包。
这是 skill 的第四类，和前三类互不通用，别抄错对方的写法。

## 一、这类为什么自成一派

| | A. 相机绕场景 | B. 相机锁死+全身动作 | C. 相机锁死+背景后掠 | **D. 机位锁死+只变表情** |
|---|---|---|---|---|
| 参考图 | 必须给 | 不给，从零画 | 不给，从零画 | **必须给**（脸就是身份） |
| 画面主体 | 产品/场景 | 角色全身 | 角色全身 | **一张脸（头肩）** |
| 相机 | 绕 60° | 完全不动 | 完全不动 | **完全不动，且锁得更死** |
| 背景 | **必须横移** | 纹丝不动 | **必须后掠** | 纹丝不动（黑底最稳） |
| 变化的东西 | 相机位置 | 四肢与道具 | 景物视差 | **只有面部肌肉** |
| 循环 | `pingpong` | `cycle` | `cycle` | `cycle` |

## 二、为什么 D 类的机位要锁得比 B/C 更死

脸对**平移**的敏感度远高于全身。全身人物横移 1% 看不出来，脸横移 1% 就已经像在"点头晃脑"。
所以模板里那句 *"nothing in the picture changes except the expression on it"* 不是修辞，
是这一类的核心约束。填的时候**不要删、不要弱化**。

## 三、为什么 D 类允许写"分节拍"，而动作类禁止

硬规则 5 说"别写成 cells 1-4 做 A、cells 5-9 做 B"——那条是针对**连续量**（旋转角度、位移）
的，分段列表会让模型在相位边界上跳一下。

但**表情不是连续量**，它本来就是若干离散状态（平静 / 坏笑 / 震惊 / 大笑）的串联。
所以这一类允许点名"节拍"，只是要把接缝写成**过渡**而不是**切换**：
模板里对应那句话是 *"the face never snaps instantly from one extreme to another"*。

**要照抄的部分**：节拍只写成 ANCHORS（cell 1 / 5 / 9 / 12 / 16 各一格，用文字描述得出），
落在具体格号上。这样模型知道节拍在哪，又不会把中间格空掉。

## 四、左右必须显式指定

"a crooked smile"不写左右，模型会逐格随机镜像，看起来就是脸在**抖**。
所有不对称特征都要给方位，模板里的写法是站在观众视角说：

> the corner of the mouth on the viewer's left pulled up high while the other corner pulls down

`viewer's left` 比 `his left` 更少歧义（模型常把"他的左"算反）。有多个不对称特征时，
**全部统一用观众视角**，别一句 viewer's left 一句 his right。

## 五、开头结尾要收在中性脸

cell 1 与 cell 16 都写成同一个"接近中性"的表情，循环缝才看不出来。
如果第 16 格停在大笑上，`cycle` 回来会像被人扇了一巴掌。

## 六、操作流程

```bash
SK="D:/image25/.workbuddy/skills/product-motion-gif"
PY="C:/Users/49707/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# 1. 参考图入库（apiz 只吃公网 URL，本地路径要上传）
apiz upload ./face.jpg --folder expression
#    -> https://cdn-hk.51sux.com/storage/expression/....jpg

# 2. 出图：竖版人脸用 3:4，2K 下整图 1536x2048 -> 单格 384x512
#    首次一律 Flare 试错档 + 2K；验收过要更大再上 Sunburst + 4K（约 133 points）
"$PY" "$SK/scripts/apiz_image.py" \
  --ref "<上一步的 URL>" \
  --prompt-file prompts/<name>.txt \
  --out out/<name>/sheet.json \
  --model apiz/gpt-image-2.5-flare --quality high --size 2K --ratio 3:4

# 3. 切帧看一眼（人脸一定先自己看，别只看数值）
"$PY" "$SK/scripts/contact_sheet.py" sheet.jpg contact.png 4 4 480
"$PY" "$SK/scripts/ab_frames.py" sheet.jpg ab-01-16.png 1 16 4 4 620

# 4. 合成：--trim none 是关键，见下一节
"$PY" "$SK/scripts/make_gif.py" --sheet sheet.jpg --outdir run1 \
  --rows 4 --cols 4 --canvas tight --trim none --bg 0,0,0 --loop cycle \
  --keep-frames --quality-report run1/qa.json
```

## 七、两个必须记住的坑

**1）`--trim` 一定用 `none`，不要用默认的 `union`。**
`union` 会按每格主体的 bbox 做统一裁剪，而脸的 bbox 逐格随表情变化（张嘴→下巴变高、
挑眉→上限变高）。结果就是每格被裁掉的位置不一样，成片里脸在**上下抖**。
这一类的构图是 prompt 保证的（"同位置同大小"），交给脚本重裁只会帮倒忙。

**2）黑底直接用 `--bg 0,0,0`，不要用 `--bg auto`。**
`auto` 从四角采样背景色，剪影式的深色头发容易把四角带偏，误判后主体框会飘。
参考图背景是纯黑时，直接写死 `0,0,0` 最稳。

**3）别让模型在脸上加"情绪符号"。**
眼泪、汗滴、青筋、`#` 号、放射线——这些一旦进 prompt，模型会在部分格里加、部分格里不加，
帧间就不一致了。模板里的 MUST NOT 段已经把它们列进禁止项，**不要为了"更夸张"把它们放回来**。
要真的想要，出图后用代码叠（可控、每格都一致）。

## 八、已踩过的坑

（首次实测后回填）
