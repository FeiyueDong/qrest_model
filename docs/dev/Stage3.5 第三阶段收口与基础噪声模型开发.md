# qREST Model Stage 3.5  
# 第三阶段收口与基础噪声模型开发计划

## 1. 阶段定位

Stage 3 已经完成了 qREST Model 从：

> “结构响应生成框架”

向：

> **“具有完整结构真值与有限观测分离能力的虚拟结构监测试验框架”**

的重要转变。

目前已经建立：

```text
Structural Truth
      ↓
Observation Operator
      ↓
Physical Observation
Virtual Probe
      ↓
Research Dataset
```

并完成：

```text
Theta / Rz 观测语义划分
Model Truth exporter
Research Dataset
Physical / Virtual 分离
qREST physical-only export
Observation provenance
Derived quantities
Research benchmark
CI
```

因此 Stage 3 的核心方向是正确且基本完成的。

Stage 3.5 不再引入新的结构理论或复杂功能。

本阶段目标是：

> **修复 Stage 3 尚未完全收口的几个关键问题，并加入一版简单、明确、可扩展的观测噪声模型，使第三阶段形成一个完整可靠的正式版本。**

---

# 2. Stage 3 当前主要欠缺

Stage 3 当前不存在需要推翻的架构问题。

主要欠缺集中在以下几个方面。

---

## 2.1 Observation 配置存在重复来源

当前 research case 中可能同时存在：

```text
observations
```

和：

```text
model_config.sensors
```

两套观测描述。

实际分析主要使用：

```text
model_config.sensors
```

而顶层：

```text
observations
```

更多用于：

```text
manifest
metadata
research description
```

因此可能出现：

```text
配置描述
≠
实际生成的 observation
```

的问题。

Stage 3.5 应解决这一问题，使：

> **Observation 配置成为唯一事实来源。**

---

## 2.2 Observation schema 尚未完全成为运行时主配置

Stage 3 已经建立：

```text
ObservationConfig
PhysicalObservationConfig
VirtualProbeConfig
```

但实际模型仍主要使用：

```text
SensorConfig
ShearSensorConfig
BeamSensorConfig
```

Stage 3.5 不要求彻底删除旧类型。

但需要明确：

```text
ObservationConfig
```

是新的正式语义入口。

旧：

```text
sensors
```

只作为兼容输入。

---

## 2.3 OpenSees imposed-support 验证仍缺 beam case

Stage 3 已建立：

```text
Direct equivalent excitation
vs
OpenSees imposed support motion
```

验证路径。

但目前主要验证：

```text
shear_building_1d
```

尚未真正覆盖：

```text
beam consistent mass
+
base excitation coupling
```

Stage 3.5 应至少增加一个：

```text
Euler beam
```

的 imposed-support 独立验证。

不需要扩展到全部 beam family。

---

## 2.4 Modal Truth metadata 仍不够完整

当前已经输出：

```text
frequency
period
mode shape
DOF labels
```

但没有明确记录：

```text
mode shape normalization
mode sign convention
DOF unit
```

Stage 3.5 应补齐这些基础语义。

---

## 2.5 Research benchmark 目前主要用于 pipeline 验证

当前 3-story benchmark 很适合：

```text
CI
format validation
regression
pipeline test
```

但并不完全代表实际 OMA / MBI 研究工况。

Stage 3.5 不要求建立大量研究数据。

只需要：

> 明确区分 small regression benchmark 与 research-scale benchmark。

并增加少量代表性 research case 即可。

---

# 3. Stage 3.5 核心目标

本阶段主要完成：

```text
Observation 配置收口
Noise 基础接口
Research Dataset 噪声输出
少量验证补强
Stage 3 最终冻结
```

不增加：

```text
新 Structural Model
复杂噪声
非线性
3D
base isolation
sensor failure
missing data
clock drift
```

---

# 4. 最终目标数据链

Stage 3.5 完成后，整体流程应明确为：

```text
Model Config
      ↓
StructuralModel
      ↓
Backend
      ↓
Structural Truth
      ↓
Observation Config
      ↓
Observation Operator
      ↓
Clean Observation
      ↓
Noise Model
      ↓
Measured Observation
      ↓
Research Dataset
```

即：

\[
\boxed{
Model
\rightarrow
Truth
\rightarrow
Observation
\rightarrow
Noise
\rightarrow
Dataset
}
\]

---

# 5. Observation Config 成为唯一事实来源

Stage 3.5 最重要的收口项是：

> **Observation layout 只定义一次。**

Research case 不应长期同时维护：

```text
observations
```

和：

```text
model_config.sensors
```

两套等价信息。

---

# 6. 推荐配置结构

建议逐步形成：

```json
{
  "model_config": {
    "...": "structural model only"
  },

  "observations": {
    "physical": [...],
    "virtual": [...]
  },

  "noise": {...},

  "research": {...}
}
```

其中：

```text
model_config
```

只描述：

```text
geometry
mass
stiffness
damping
excitation
```

而：

```text
observations
```

描述：

```text
哪些楼层
什么方向 / DOF
什么 quantity
physical / virtual
```

---

# 7. 兼容旧 sensors

现有普通模型配置中的：

```text
sensors
```

暂时保留。

建议 normalize 时转换为：

```text
ObservationConfig
```

旧配置：

```text
sensors
```

继续可运行。

Research Dataset 新配置优先使用：

```text
observations
```

不要求一次性删除全部旧接口。

---

# 8. Observation pipeline

推荐形成：

```text
AnalysisResult
      ↓
build_observations(
    result,
    observation_config
)
      ↓
ObservationResult
```

Observation 不再成为 StructuralModel 或 Backend 的必要输入。

应满足：

> 改变 Observation layout 不改变 Structural Truth。

即：

```text
M
K
C
modal
full response
```

必须保持不变。

---

# 9. Noise 的基本定位

Stage 3.5 加入第一版：

> **Measurement Noise**

噪声只作用于：

```text
Observation
```

不作用于：

```text
Structural Truth
Ground Motion
M/K/C
Modal Truth
```

因此：

\[
y_{\mathrm{measured}}
=
y_{\mathrm{clean}}
+
n
\]

---

# 10. 第一版 Noise Model

只实现：

```text
Gaussian White Noise
```

即：

\[
n(t)
\sim
\mathcal N(0,\sigma_n^2)
\]

第一版不实现：

```text
colored noise
bias
drift
clipping
missing sample
sensor failure
clock error
orientation error
```

---

# 11. Noise 默认作用范围

默认：

```text
Physical Observation
    → noisy

Virtual Probe
    → clean

Structural Truth
    → clean
```

这是 Stage 3.5 的固定原则。

---

# 12. Noise Level

第一版推荐：

```text
std_ratio
```

定义：

\[
\sigma_n
=
r
\cdot
\sigma_y
\]

其中：

\[
\sigma_y
=
std(y_{\mathrm{clean}})
\]

例如：

```text
0.01
→ 1%

0.05
→ 5%

0.10
→ 10%
```

---

# 13. 推荐 Noise Config

```json
{
  "noise": {
    "enabled": true,
    "seed": 20260906,

    "model": {
      "type": "gaussian_white",
      "target": "physical"
    },

    "level": {
      "mode": "std_ratio",
      "value": 0.05
    }
  }
}
```

Stage 3.5 第一版只要求支持：

```text
type = gaussian_white

target = physical

level.mode = std_ratio
```

---

# 14. Random Seed

Noise 必须显式支持：

```text
seed
```

推荐：

```python
np.random.default_rng(seed)
```

要求：

```text
same config
+
same seed
→ same noisy data
```

而：

```text
different seed
→ same truth
→ same clean observation
→ different measured observation
```

---

# 15. Noise 不进入 Backend

禁止：

```text
Backend
→ add noise
```

Noise 应独立存在，例如：

```text
qrest_model/noise/
    __init__.py
    config.py
    gaussian.py
```

核心接口可以非常简单：

```text
apply_observation_noise()
```

---

# 16. Noise 的处理单位

每个 physical observation 单独计算：

\[
\sigma_{n,j}
=
r
\cdot
std(y_j)
\]

不同 channel 不共享绝对噪声强度。

因此可以自然处理：

```text
different floor response amplitude
different quantity magnitude
```

---

# 17. Channel noise 独立

第一版默认：

```text
channel A noise
⊥
channel B noise
```

不考虑：

```text
spatial correlation
common-mode noise
```

---

# 18. Zero Signal

若：

\[
std(y)=0
\]

则：

\[
\sigma_n=0
\]

第一版直接：

```text
noise = 0
```

不额外定义 sensor noise floor。

---

# 19. Research Dataset 输出

当 noise disabled：

```text
observations/
    physical/
    virtual/
```

保持当前行为。

---

# 20. Noise enabled 时

建议：

```text
observations/
    physical/
        acceleration.csv

    physical_clean/
        acceleration.csv

    virtual/
        ...
```

其中：

```text
physical
```

表示：

> measured / noisy physical observation。

而：

```text
physical_clean
```

表示：

> noise-free reference observation。

---

# 21. 不覆盖 clean reference

禁止：

```text
clean observation
→ add noise
→ clean lost
```

Research Dataset 必须能够同时访问：

\[
y_{\mathrm{clean}}
\]

和：

\[
y_{\mathrm{measured}}
\]

以支持算法误差分析。

---

# 22. qREST Export

当 noise enabled 时：

```text
qREST export
```

默认导出：

```text
measured physical observation
```

即：

```text
observations/physical
```

而不是：

```text
physical_clean
```

这样 qREST 数据保持：

> 模拟真实监测数据

的语义。

---

# 23. Noise Metadata

建议新增：

```text
metadata/noise.json
```

至少保存：

```text
enabled
type
seed
target
level mode
level value
```

并记录各 channel：

```text
signal_std
target_noise_std
realized_noise_std
```

---

# 24. Noise Provenance

Research manifest / provenance 中至少记录：

```text
noise configured
noise seed
noise type
noise level
```

确保每个 noisy dataset 可重复生成。

---

# 25. Dataset Hash

Stage 3.5 建议区分：

```text
model_config_hash
dataset_config_hash
```

其中：

```text
model_config_hash
```

只表示结构模型。

而：

```text
dataset_config_hash
```

包含：

```text
model
observation
noise
research metadata
```

避免：

```text
noise 1%
noise 10%
```

得到相同 dataset identity。

---

# 26. Modal Truth Metadata

Stage 3.5 增加：

```text
mode_shape_normalization
mode_shape_sign_convention
dof_units
```

建议明确当前：

\[
\phi^T M\phi=1
\]

即：

```text
mass_normalized
```

以及：

```text
largest absolute component positive
```

的符号约定。

---

# 27. DOF Unit

建议 truth metadata 至少说明：

```text
U / Ux / Uy
    translation

Theta / Rz
    rotation
```

对应：

```text
m
rad
```

速度和加速度单位按时间导数解释。

---

# 28. Euler imposed-support validation

Stage 3.5 增加一个最小：

```text
Euler beam
```

验证 case。

对比：

```text
Direct equivalent base inertia
```

和：

```text
OpenSees imposed base motion
```

重点检查：

```text
relative displacement
relative velocity
relative acceleration
absolute acceleration
```

目的是验证：

```text
consistent mass
+
base excitation coupling
```

不要求对 Rayleigh、Timoshenko、Shear-Flexure 全部重复。

---

# 29. Research benchmark 分类

当前 3-story case 保留。

将其正式定位为：

```text
small regression benchmark
```

用途：

```text
CI
format
pipeline
reproducibility
```

---

# 30. Research-scale benchmark

Stage 3.5 只增加少量真实研究规模 case。

建议至少：

```text
1 × OMA
1 × MBI
```

例如：

```text
OMA:
10–16 story
longer broadband response

MBI:
16 story
sparse physical observation
```

不要求大量参数扫描。

---

# 31. OMA benchmark

真正用于 OMA 的数据应至少具备：

```text
reasonable duration
sufficient sampling
broadband excitation
multiple modes excited
```

Stage 3.5 只需要建立一个 baseline。

---

# 32. MBI benchmark

建议建立：

```text
16 story
5 measured levels
U physical observation
Theta truth retained
```

用于后续正式 MBI 测试。

---

# 33. Stage 3.5 不加入复杂 Noise Study

本阶段只验证：

```text
clean
1%
5%
10%
```

类似简单噪声等级即可。

不建立大规模噪声数据库。

---

# 34. Stage 3.5 主要测试

至少增加以下测试。

---

## 34.1 Truth invariance

```text
noise off
noise on
```

必须满足：

```text
M
K
C
modal
full response
```

完全一致。

---

## 34.2 Clean observation invariance

同一 observation config：

```text
clean observation
```

不受 noise seed 影响。

---

## 34.3 Physical noise

Noise enabled 后：

```text
measured physical
≠
clean physical
```

---

## 34.4 Virtual invariance

```text
Theta / Rz virtual probe
```

Noise enabled 前后保持一致。

---

## 34.5 Seed reproducibility

```text
same seed
→ same noise
```

---

## 34.6 Different seed

```text
different seed
→ same truth
→ different measured observation
```

---

## 34.7 Zero level

```text
std_ratio = 0
```

必须：

```text
measured == clean
```

---

## 34.8 Noise ratio

长序列下：

\[
\frac{std(n)}
{std(y)}
\]

应接近配置：

\[
r
\]

允许合理随机误差。

---

## 34.9 qREST export

Noise enabled 时确认：

```text
qREST
→ measured physical
```

---

## 34.10 Observation single source

改变：

```text
ObservationConfig
```

必须改变：

```text
ObservationResult
```

但不能改变：

```text
Structural Truth
```

---

# 35. 推荐实施顺序

## Step 1

收口：

```text
ObservationConfig
```

使其成为 research dataset observation layout 的唯一事实来源。

---

## Step 2

保留旧：

```text
sensors
```

兼容转换。

---

## Step 3

确保：

```text
Truth
```

完全独立于 Observation。

---

## Step 4

增加：

```text
NoiseConfig
```

和：

```text
GaussianWhiteNoise
```

---

## Step 5

实现：

```text
Clean Observation
→ Measured Observation
```

---

## Step 6

扩展 Research Dataset：

```text
physical
physical_clean
virtual
noise metadata
```

---

## Step 7

补：

```text
dataset_config_hash
```

和 noise provenance。

---

## Step 8

补 modal truth metadata。

---

## Step 9

增加 Euler imposed-support integration validation。

---

## Step 10

增加：

```text
1 OMA research benchmark
1 MBI research benchmark
```

---

## Step 11

完善测试、README 和 Stage 3 completion document。

---

# 36. Stage 3.5 验收标准

完成后至少满足：

### Observation

```text
ObservationConfig
```

成为正式 observation layout 来源。

---

### Truth

结构 truth 与 observation/noise 完全解耦。

---

### Noise

支持：

```text
Gaussian white noise
std_ratio
seed
physical only
```

---

### Dataset

Noise enabled 后能够同时输出：

```text
truth
clean physical observation
measured physical observation
virtual probe
noise metadata
```

---

### Reproducibility

相同：

```text
model
observation
noise
seed
```

生成相同 dataset。

---

### qREST

qREST 只导出：

```text
measured physical observation
```

---

### Modal Truth

明确：

```text
normalization
sign convention
DOF units
```

---

### Validation

至少完成一个：

```text
Euler imposed-support
```

独立验证。

---

### Research benchmark

至少拥有：

```text
small regression cases
+
representative OMA case
+
representative MBI case
```

---

# 37. Stage 3 最终完成标准

Stage 3.5 完成后，应当可以正式认为 Stage 3 整体结束。

此时 qREST Model 应形成稳定流程：

\[
\boxed{
Structural\ Model
\rightarrow
Truth
\rightarrow
Observation
\rightarrow
Measurement\ Noise
\rightarrow
Research\ Dataset
}
\]

并明确区分：

```text
结构真实状态
研究用虚拟量
理想物理观测
实际模拟监测观测
```

---

# 38. Stage 3 完成后的项目能力

此时 qREST Model 应能够可靠支持：

```text
OMA algorithm validation
mode completion
MBI
response reconstruction
sensor layout study
noise sensitivity study
```

并且每个研究问题都具有：

```text
known truth
controlled observation
controlled noise
reproducible dataset
```

---

# 39. 本阶段最重要的原则

Stage 3.5 不追求功能数量。

本阶段最重要的是把 Stage 3 已有能力真正收紧成：

> **结构模型负责产生真值，观测模型负责决定能够看到什么，噪声模型负责描述看到的数据有多不完美。**

即：

\[
\boxed{
Truth
\neq
Observation
\neq
Measured\ Observation
}
\]

当这一边界稳定后，Stage 3 才可以认为真正形成了一个完整、可靠并适合后续研究使用的正式版本。