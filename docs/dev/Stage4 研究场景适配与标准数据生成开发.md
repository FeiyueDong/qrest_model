# qREST Model Stage 4
# 研究场景适配与标准数据生成开发计划

## 1. 阶段定位

经过前三阶段，qREST Model 已经具备：

```text id="u14tfc"
Structural Model
      ↓
Dynamic Analysis
      ↓
Structural Truth
      ↓
Observation
      ↓
Measurement Noise
      ↓
Research Dataset
```

Stage 4 不再继续扩展新的结构模型，也不在 qREST Model 中建立算法运行和评价框架。

本阶段目标是：

> **使现有结构模型能够方便地构造 OMA、模态补全、MBI、响应重构等研究场景，并稳定输出两类数据：真实监测形式的数据，以及完整的模型真值。**

Stage 4 定位为：

> **研究场景适配与标准数据生成阶段**

---

# 2. 基本职责边界

qREST Model 负责：

```text id="kih7xz"
结构模型
动力分析
激励
完整响应
物理观测
简单测量噪声
结构真值
标准监测数据生成
```

qREST Model 不负责：

```text id="7p0ov2"
FDD / SSI / MBI 算法执行
算法结果匹配
MAC 评价
误差统计
批量研究实验管理
```

这些工作继续由：

```text id="3ah8ki"
qrest_module
+
research scripts
```

承担。

---

# 3. 两类输出

Stage 4 应继续保持非常简单的输出逻辑。

## 3.1 Monitoring Data

模拟真实物理监测设备能够获取的数据。

主要包括：

```text id="g21x0f"
physical acceleration / velocity / displacement
channel ID
sensor location
direction
unit
DT
NPTS
basic building / monitoring metadata
```

算法项目主要消费这一部分。

---

## 3.2 Structural Truth

模型内部完整保存：

```text id="ra83pn"
M / K / C
true modal frequencies
true mode shapes
full response
ground input
Theta / Rz
virtual probes
derived structural quantities
structural parameters
```

这些内容用于：

```text id="5241bk"
研究对比
算法验证
结果解释
```

但不默认提供给算法。

因此始终保持：

\[
\boxed{
Algorithm\ Input
\approx
Physical\ Monitoring\ Data
}
\]

而：

\[
\boxed{
Research\ Reference
=
Structural\ Truth
}
\]

---

# 4. Stage 4 数据链

目标流程保持简单：

```text id="1f0ctg"
Model Config
      ↓
Structural Analysis
      ↓
Research Dataset
      ├── Structural Truth
      └── Physical Observation
                    ↓
                 scripts
                    ↓
          qREST / qrest_module Dataset
```

核心模型只负责产生正确的数据。

`scripts/` 负责把 physical observation 整理成算法项目可以直接使用的监测数据集。

---

# 5. Stage 4 第一项工作：研究型激励

当前模型已经支持：

```text id="5lekh0"
single sine
multi-sine
recorded ground motion
```

Stage 4 需要补充一种简单的随机激励，使模型能够更合理地生成 OMA 类型数据。

---

# 6. 第一版随机激励

仅增加：

> **可复现的宽频随机激励**

第一版建议采用：

```text id="meai2g"
Gaussian stochastic excitation
```

并支持：

```text id="wst9w2"
seed
amplitude / std
dt
duration
```

必要时增加简单：

```text id="te7khp"
frequency band
```

控制。

不需要模拟：

```text id="4oxy31"
真实风荷载空间分布
交通荷载
复杂环境激励模型
```

---

# 7. 随机激励与 Measurement Noise 的区别

必须继续明确：

```text id="9uccpo"
Stochastic Excitation
    ↓
Structure
    ↓
Response
```

和：

```text id="49ch20"
Response
    ↓
Physical Sensor
    ↓
Measurement Noise
```

是两个不同过程。

即：

\[
Excitation\ Randomness
\neq
Measurement\ Noise
\]

---

# 8. 随机激励可复现性

随机激励必须显式使用：

```text id="mksie5"
seed
```

相同：

```text id="2tm9iy"
model
excitation config
seed
```

必须生成完全相同的输入和结构响应。

---

# 9. OMA 研究场景

Stage 4 建立少量真正适合 OMA 的标准 case。

第一版不需要很多。

建议至少建立：

```text id="z16qpz"
OMA-Shear
OMA-Beam
```

两类代表性场景。

---

# 10. OMA-Shear

例如：

```text id="3a68ri"
12-story shear building
```

建议：

```text id="ru08ek"
sampling rate:
50–100 Hz

duration:
300–600 s

excitation:
broadband stochastic

observation:
physical acceleration
```

Algorithm Dataset 中只包含物理加速度测点。

Truth 中保留：

```text id="hhb0j9"
true frequency
true mode shape
full response
M/K/C
```

---

# 11. OMA-Beam

可选择：

```text id="xup24c"
Euler
或
Timoshenko
```

作为第二类研究场景。

Algorithm Dataset 仍只输出：

```text id="hps8bl"
U physical acceleration
```

而：

```text id="xt679w"
Theta
```

保留在 Truth / Virtual Probe 中。

---

# 12. MBI / Mode Completion 场景

继续使用 Stage 3 已建立的：

```text id="5wgf0l"
16-story sparse observation
```

作为基础。

典型：

```text id="qq57mq"
16 floors

physical observation:
1, 4, 8, 12, 16

full truth:
all floors
```

用于：

```text id="vdnc9n"
mode completion
MBI
response reconstruction
```

---

# 13. Model Mismatch 场景

Stage 4 可以保留非常简单的 model mismatch 描述。

例如：

```text id="73tmpe"
Truth:
Timoshenko

Research assumed model:
Euler
```

或者：

```text id="x2pr2p"
Truth:
Shear-Flexure

Research assumed model:
Shear
```

qREST Model 只需要在 dataset metadata 中记录：

```text id="i1cbps"
truth model family
suggested mismatch family
```

不负责实际运行 assumed model 算法。

---

# 14. Measurement Noise 场景

继续使用 Stage 3 已实现的：

```text id="x4w469"
Gaussian white measurement noise
```

即可。

Stage 4 只建议形成少量标准等级：

```text id="xldfjo"
clean
1%
5%
10%
```

不扩展新的噪声类型。

---

# 15. Observation Density

对于模态补全和响应重构，可以准备少量标准测点布局：

```text id="9hqtwq"
full
medium
sparse
```

例如 16 层：

```text id="e19sml"
full:
1–16

medium:
1,4,8,12,16

sparse:
1,6,11,16
```

不需要随机 sensor layout generator。

---

# 16. scripts 的 Stage 4 定位

`scripts/` 应被明确为：

> **模型输出到标准监测数据集的转换与辅助工具层。**

它不负责结构计算，也不负责算法执行。

主要任务：

```text id="s039br"
读取 Research Dataset
提取 physical observation
生成 qREST data
生成 metadata
生成/复制算法配置
组织最终数据目录
```

---

# 17. 推荐主流程

最终用户最好只需要执行类似：

```text id="jr69iu"
generate research case
      ↓
export monitoring dataset
```

第二步由：

```text id="yjzj1g"
scripts/export_datasets.py
```

作为主要入口。

---

# 18. export_datasets.py

建议将其作为 Stage 4 的主要 dataset conversion script。

职责：

```text id="ohbt1w"
读取 Research Dataset
      ↓
选择 physical observation
      ↓
生成 qREST data.txt
      ↓
生成 qREST metadata.json
      ↓
准备 config/
      ↓
形成完整 qrest_module dataset
```

最终生成：

```text id="e2cqwk"
dataset_name/
    dataset_name_data.txt
    dataset_name_metadata.json
    config/
```

---

# 19. make_metadata.py

保留为独立辅助工具。

但应更新为兼容：

```text id="smuhde"
Stage 4 Research Dataset
```

优先从：

```text id="kn8gqp"
physical observation metadata
geometry
sampling information
```

生成 qREST metadata。

不要依赖旧 master-history 流程。

---

# 20. make_algorithm_configs.py

该脚本需要重点调整。

目前它属于早期实现，Stage 4 应重新定义其原则：

> **算法配置不得从 Structural Truth 中获取算法本不应知道的信息。**

禁止默认读取：

```text id="1th7h3"
true modal frequency
true mode shape
```

然后生成：

```text id="v9yxnv"
FDD init frequency
known modal search position
```

否则 benchmark 会发生 Truth Leakage。

---

# 21. Algorithm Config 允许使用的信息

可以使用：

```text id="i85qlg"
DT
NPTS
Nyquist frequency
channel count
sensor geometry
data quantity
```

这些都是监测数据自身能够提供的信息。

---

# 22. Algorithm Config 推荐方式

第一版建议采用：

```text id="rvfhqh"
default profile
+
basic data-derived parameters
```

例如：

```text id="qq2g23"
nfft
```

可以由：

```text id="n68nsj"
NPTS
```

计算。

滤波上限可以由：

\[
f_N=\frac{1}{2DT}
\]

确定。

而：

```text id="2wpovs"
init modal frequencies
```

应：

```text id="j6ip0y"
不设置
或使用算法默认自动识别
```

除非用户显式提供。

---

# 23. Config Profile

不需要复杂配置系统。

可以仅提供：

```text id="5522xj"
default
oma
response_reconstruction
```

几个简单 profile。

实际详细算法配置仍应遵循：

```text id="vi7wl5"
qrest_module
```

当前配置规范。

---

# 24. map_sensors.py

Stage 3 已经建立正式 Observation pipeline。

因此旧：

```text id="5nla0v"
master response
→ map_sensors.py
→ sensor response
```

流程不应继续作为 Stage 4 主路径。

建议：

```text id="i5cxk3"
保留 legacy compatibility
或明确 deprecated
```

新的 research case 应直接使用：

```text id="i75y1d"
Observation Config
→ Physical Observation
```

---

# 25. build_datasets.py

该脚本属于较早的数据集生成入口。

Stage 4 应明确它和新的：

```text id="hmnl10"
Research Dataset
```

流程之间的关系。

建议：

- 若仍有旧 regression dataset 依赖，则继续保留；
- 新研究场景优先使用现有 `generate-research` / research dataset pipeline；
- 不再继续扩展两套平行 dataset generator。

---

# 26. scripts 最终建议结构

不要求大规模重构。

只需要让职责变得清楚：

```text id="nrw5vu"
scripts/
    export_datasets.py
        主转换入口

    make_metadata.py
        metadata 辅助工具

    make_algorithm_configs.py
        config 辅助工具

    build_datasets.py
        legacy / regression dataset

    map_sensors.py
        legacy compatibility
```

如果后续发现功能重复，再删除旧脚本。

Stage 4 不要求为了“整洁”强行合并所有文件。

---

# 27. Monitoring Dataset 原则

最终输出给 qrest_module 的数据必须保持：

> **简单、真实、物理可解释。**

例如：

```text id="yclto8"
CH01 acceleration X
CH02 acceleration X
CH03 acceleration Y
...
```

不得出现：

```text id="btv7n0"
Theta
Rz truth
full modal matrix
M/K/C
```

作为普通物理监测通道。

---

# 28. Research Dataset 继续保持丰富

Research Dataset 则继续完整保存：

```text id="9r2ozj"
truth/
derived/
observations/
metadata/
manifest.json
```

Stage 4 不重新设计这一结构。

只在需要时补充：

```text id="2u4jsw"
scenario metadata
excitation metadata
```

即可。

---

# 29. 推荐标准研究 Case

Stage 4 第一版建议只维护少量代表性 case：

```text id="7alcht"
OMA:
    shear stochastic
    beam stochastic

Mode Completion / MBI:
    Timoshenko 16-story medium
    Timoshenko 16-story sparse

Response Reconstruction:
    one sparse physical observation case
```

不建立大量排列组合。

---

# 30. Case Metadata

建议每个 research case 至少记录：

```text id="te9xh1"
task
model_family
excitation_type
observation_density
noise_level
scale
```

例如：

```json id="755g8u"
{
  "research": {
    "task": "oma",
    "family": "shear",
    "excitation": "stochastic",
    "sensor_density": "full",
    "scale": "research_scale"
  }
}
```

---

# 31. Stage 4 测试重点

Stage 4 不需要增加大量测试。

主要验证以下内容。

---

## 31.1 Stochastic reproducibility

相同：

```text id="5vxpsy"
seed
```

生成相同随机激励和响应。

---

## 31.2 Stochastic variability

不同 seed：

```text id="wy26wh"
input different
response different
model truth properties unchanged
```

---

## 31.3 Monitoring export

从 Research Dataset 导出的：

```text id="4qlw11"
data
metadata
config
```

可以形成完整监测数据集。

---

## 31.4 Physical-only

导出结果只包含：

```text id="7obn94"
physical observation
```

---

## 31.5 No Truth Leakage

算法 config generation 不允许默认读取：

```text id="xut0sz"
truth modal frequency
truth mode shape
```

测试应专门检查这一点。

---

## 31.6 Metadata consistency

检查：

```text id="hk6t18"
ChannelNum
NPTS
DT
channel order
units
sensor locations
```

与实际 data 一致。

---

# 32. Stage 4 推荐实施顺序

## Step 1

增加简单：

```text id="5qx5a0"
stochastic excitation
```

及其 seed/reproducibility。

---

## Step 2

建立：

```text id="q7h6i4"
OMA stochastic research case
```

---

## Step 3

整理现有：

```text id="yjm53z"
scripts/
```

职责。

---

## Step 4

以：

```text id="nt11n2"
export_datasets.py
```

作为统一监测数据集导出入口。

---

## Step 5

更新：

```text id="gywu3z"
make_metadata.py
```

适配当前 Research Dataset。

---

## Step 6

重构：

```text id="hbtoau"
make_algorithm_configs.py
```

去除 Truth Leakage，并适配当前 qrest_module 配置。

---

## Step 7

明确：

```text id="ogphkt"
map_sensors.py
build_datasets.py
```

的 legacy / regression 定位。

---

## Step 8

建立少量：

```text id="2z0hs4"
OMA
MBI / mode completion
response reconstruction
```

标准研究 case。

---

## Step 9

完成：

```text id="f7d89m"
Research Dataset
→ scripts
→ qREST/qrest_module Dataset
```

端到端验证。

---

# 33. Stage 4 验收标准

Stage 4 完成后，应满足：

### Research Scenario

能够生成：

```text id="89gdj8"
stochastic OMA
sparse MBI
response reconstruction
```

等代表性场景。

---

### Monitoring Data

能够稳定得到：

```text id="zyfqkh"
physical monitoring data
```

其形式与真实监测数据一致。

---

### Truth

同时保留：

```text id="v1o13v"
complete structural truth
```

用于后续研究对比。

---

### scripts

能够一条主流程完成：

```text id="wm3i04"
Research Dataset
→ qrest_module usable dataset
```

包括：

```text id="d01aiy"
data
metadata
algorithm config
```

---

### No Truth Leakage

算法数据和自动生成配置不得默认利用：

```text id="f52nv9"
true modal information
full response truth
virtual probe
```

---

### Reproducibility

随机激励和测量噪声均在明确 seed 下可复现。

---

# 34. Stage 4 不包含

本阶段暂不加入：

```text id="u2c5we"
新结构模型
非线性
base isolation
3D beam
复杂噪声
missing data
sensor failure
clock drift
算法执行框架
benchmark evaluator
复杂实验管理器
```

---

# 35. Stage 4 最终目标

Stage 4 完成后，qREST Model 应形成稳定定位：

> **根据明确可控的结构、激励和观测条件，生成与真实结构监测形式一致的数据，同时提供完整可追溯的结构真值。**

最终工作流：

```text id="c2txwy"
qrest_model
    │
    ├── Monitoring Data
    │       ↓
    │     scripts
    │       ↓
    │   qREST / qrest_module
    │
    └── Structural Truth
            ↓
       Research Comparison
```

Stage 4 的重点不是增加更多功能，而是：

\[
\boxed{
让现有模型真正稳定地产生“可用的研究数据”
}
\]

并保持：

\[
\boxed{
Physical\ Monitoring\ Data
\neq
Structural\ Truth
}
\]

这一基本边界。