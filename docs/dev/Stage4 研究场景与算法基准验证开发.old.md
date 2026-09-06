# qREST Model Stage 4
# 研究场景与算法基准验证开发计划

## 1. 阶段定位

经过 Stage 1–3，qREST Model 已经基本完成：

```text
Stage 1
稳定统一的动力分析框架

Stage 2
多种线性结构模型族

Stage 3
Structural Truth / Observation / Dataset 分离
```

当前完整数据链已经形成：

```text
Structural Model
      ↓
Backend
      ↓
Structural Truth
      ↓
Observation
      ↓
Measurement Noise
      ↓
Research Dataset
```

Stage 4 不再以增加新的结构模型为主要目标。

本阶段重点转向：

> **构造真正适合 OMA、模态补全、MBI 和响应重构研究的虚拟监测场景，并让算法项目实际消费这些数据进行验证。**

Stage 4 定位为：

> **研究场景与算法基准验证阶段**

---

# 2. Stage 4 基本原则

Stage 4 最重要的原则是：

> **算法输入与模型真值必须继续严格分离。**

算法实际获得：

```text
Physical Monitoring Data
```

模型额外提供：

```text
Structural Truth
Modal Truth
Virtual Probe
M / K / C
Full Response
Derived Quantities
```

这些额外信息只能用于：

```text
benchmark
evaluation
diagnostics
research comparison
```

不得默认作为算法输入。

---

# 3. Algorithm Input 的定位

提供给：

```text
qrest_module
FDD
EFDD
SSI
MBI
response reconstruction
```

等算法的数据，应尽量模拟真实监测设备能够获得的数据。

典型内容包括：

```text
time / sampling interval
physical acceleration channels
channel ID
sensor location
direction
unit
basic monitoring metadata
```

必要时可以包括：

```text
ground / base physical channels
```

前提是实际研究场景中这些测点确实存在。

---

# 4. Algorithm Input 不应包含

默认不得提供：

```text
M
K
C

true modal frequency
true mode shape

Theta truth
Rz truth

full unmeasured response
virtual probe

true modal coordinate
```

这些属于：

> Evaluation Truth

而不是：

> Algorithm Input。

---

# 5. Benchmark 数据的双层结构

一个研究 case 应同时具有两个视角。

## 5.1 Algorithm View

算法只能读取：

```text
physical observation
```

例如：

```text
01F_X
04F_X
08F_X
12F_X
16F_X
```

及其必要元数据。

---

## 5.2 Evaluation View

评估程序可以额外读取：

```text
truth/modal.npz
truth/response.npz
truth/matrices.npz
virtual observations
research metadata
```

用于计算误差。

因此：

```text
Research Dataset
├── algorithm_input
└── evaluation_truth
```

概念上必须严格分离。

当前目录不一定立即改名，但 API 和文档需要体现这一原则。

---

# 6. Stage 4 开始前的小修复

正式扩展研究场景前，应先完成 Stage 3 剩余的几个小问题。

这些修改范围较小，不单独建立新阶段。

---

## 6.1 修正 rigid-floor noise

当前 rigid-floor physical observation 内部仍可能使用：

```text
[X, Y, Rz]
```

多分量 history。

噪声强度不得基于整个多分量数组计算：

\[
std([X,Y,R_z])
\]

而必须先得到该 physical channel 真正对应的标量时程：

\[
y_j(t)
\]

然后：

\[
\sigma_{n,j}
=
r\,std(y_j)
\]

建议提取统一：

```text
extract_observation_series()
```

供：

```text
noise
CSV exporter
qREST exporter
```

共享。

---

## 6.2 Noise enabled 时强制 seed

Research Dataset 强调可重复性。

因此：

```text
noise.enabled = true
```

时必须要求：

```text
seed
```

存在。

否则直接报错。

不在 Stage 4 引入 nondeterministic research dataset。

---

## 6.3 Noisy ObservationResult rows 一致性

当前 noisy history 与 legacy：

```text
rows
```

可能不完全同步。

Stage 4 前应保证：

```text
ObservationResult
```

内部只有一个权威数据来源。

推荐：

```text
channel + history
```

作为 canonical representation。

`rows` 可以继续兼容，但必须由当前 history 生成，不能保留 clean value。

---

# 7. Stage 4 第一项主要工作：真实研究型激励

当前 research-scale case 仍主要采用 deterministic multi-sine。

对于 OMA，应该加入更接近环境振动的随机激励。

Stage 4 第一版建议增加：

> **Stochastic Excitation**

---

# 8. 随机激励的定位

必须与 Stage 3 measurement noise 区分。

Measurement Noise：

```text
structure
→ response
→ sensor
→ noise
```

随机激励：

```text
random excitation
→ structure
→ response
```

即：

> excitation randomness ≠ measurement noise。

---

# 9. 第一版随机激励

第一版不需要复杂环境荷载模型。

建议只实现：

```text
Gaussian broadband excitation
```

并支持：

```text
seed
amplitude
duration
```

必要时增加：

```text
band-limit
```

但可以作为第二步。

基本形式：

\[
a_g(t)\sim \mathcal N(0,\sigma_a^2)
\]

或者经过简单带限滤波后的随机输入。

---

# 10. 随机激励必须可复现

例如：

```json
{
  "ground_motion": {
    "type": "stochastic",
    "seed": 1001,
    "dt": 0.02,
    "duration": 300.0
  }
}
```

要求：

```text
same config
+
same seed
→ same excitation
```

---

# 11. OMA Baseline

Stage 4 建立第一套真正的 OMA benchmark。

建议规模：

```text
10–16 stories

sampling:
50–100 Hz

duration:
300–600 s

excitation:
broadband stochastic

observation:
physical acceleration
```

第一版只需要：

```text
1–2
```

个稳定 case。

---

# 12. 推荐第一套 OMA case

例如：

```text
OMA-SHEAR-12
```

Truth：

```text
12-story shear model
```

Algorithm Input：

```text
12 floor X acceleration
```

Excitation：

```text
broadband stochastic
```

Noise cases：

```text
clean
1%
5%
10%
```

Evaluation Truth：

```text
true modal frequencies
true full mode shapes
```

---

# 13. 第二套 OMA case

后续可增加：

```text
OMA-TIMO-12
```

或：

```text
OMA-SF-12
```

用于研究：

> 当真实结构不完全符合简单 shear assumption 时，OMA 本身是否仍能稳定识别模态。

但 Stage 4 第一版不需要建立很多 case。

---

# 14. OMA Evaluation

最基础评价指标：

### Frequency error

\[
e_f
=
\frac{|f_{identified}-f_{truth}|}
{f_{truth}}
\]

### Mode shape MAC

\[
MAC(\phi_i,\hat\phi_i)
=
\frac{
|\phi_i^H\hat\phi_i|^2
}{
(\phi_i^H\phi_i)
(\hat\phi_i^H\hat\phi_i)
}
\]

必要时后续加入：

```text
damping error
mode missing rate
false mode count
```

第一版不需要全部实现。

---

# 15. Stage 4 第二项主要工作：MBI / Mode Completion Benchmark

目前已有：

```text
mbi_timoshenko_16story_research
```

其布局已经接近真实研究需求：

```text
16 floors

physical U:
1,4,8,12,16
```

Stage 4 应正式将其转化为算法 benchmark。

---

# 16. MBI Algorithm Input

MBI 输入侧只提供实际可获得的：

```text
physical response
identified / measured modal information
sensor layout
```

不得直接提供：

```text
Theta truth
full mode shape
full response
```

---

# 17. MBI Evaluation Truth

评价侧可以读取：

\[
\Phi_{\rm truth}
\]

和：

\[
x_{\rm truth}(t)
\]

用于比较：

### Mode completion error

\[
e_\phi
=
\frac{
\|\hat\phi-\phi_{\rm truth}\|
}{
\|\phi_{\rm truth}\|
}
\]

或 MAC。

### Response reconstruction error

\[
e_x
=
\frac{
\|\hat x-x_{\rm truth}\|
}{
\|x_{\rm truth}\|
}
\]

---

# 18. Model Mismatch

Stage 4 建议首次正式加入：

> **truth family 与 assumed family 不一致**

的研究场景。

例如：

```text
Truth:
Timoshenko

Algorithm assumption:
Euler
```

或者：

```text
Truth:
Shear-Flexure

Assumption:
Shear
```

这对我们正在研究的：

```text
assumed modal shape
mode completion
MBI
```

尤其重要。

---

# 19. 注意职责边界

qrest_model 只负责记录：

```text
truth_family
benchmark metadata
observation
```

不负责实现：

```text
Euler-based MBI
Timoshenko-based MBI
```

这些仍属于算法项目。

---

# 20. Stage 4 第三项主要工作：算法项目适配

Stage 4 应第一次建立正式：

```text
qrest_model
      ↓
Research Dataset
      ↓
qrest_module
      ↓
Algorithm Result
      ↓
Benchmark Evaluator
      ↓
Metrics
```

---

# 21. 不建议算法直接读取 Research Dataset 全目录

为了防止算法意外使用 truth，建议提供专门的：

```text
algorithm input export
```

例如：

```text
algorithm_input/
```

或者直接继续使用：

```text
qREST physical dataset
```

---

# 22. 推荐优先复用 qREST

由于 qREST 本身就是我们定义的物理监测数据格式：

Stage 4 推荐：

```text
Research Dataset
       ↓
physical observations
       ↓
qREST export
       ↓
qrest_module
```

这样最接近真正未来使用流程。

---

# 23. 因此 Research Dataset 与 Algorithm Dataset 的关系

建议正式明确：

```text
Research Dataset
=
完整研究档案

Algorithm Dataset
=
Research Dataset 的 physical projection
```

即：

\[
D_{\rm algorithm}
=
P_{\rm physical}
(D_{\rm research})
\]

---

# 24. Evaluation 工具

Stage 4 建议增加一个很轻量的：

```text
benchmark/
```

模块。

例如：

```text
qrest_model/
    benchmark/
        modal.py
        response.py
```

负责：

```text
frequency error
MAC
response error
```

不实现识别算法本身。

---

# 25. Evaluation Input

Evaluator 接收：

```text
truth result
estimated result
```

例如：

```text
identified frequencies
identified mode shapes
```

输出：

```text
matching
error
MAC
```

---

# 26. Mode Matching

第一版可以采用比较简单的规则：

```text
frequency nearest
+
optional MAC
```

不需要一开始设计复杂 matching system。

重点是形成：

```text
identified mode
↔
truth mode
```

的明确对应关系。

---

# 27. Stage 4 Noise Study

现有 Gaussian measurement noise 可以开始真正用于研究。

建议只使用几个标准等级：

```text
0%
1%
5%
10%
```

不要建立大量连续参数。

目标是验证：

```text
algorithm performance
vs
noise level
```

而不是研究复杂传感器噪声模型。

---

# 28. Stage 4 Observation Density Study

对于 MBI / mode completion，可以定义少量布局：

```text
full
medium
sparse
```

例如 16 层：

```text
full:
1–16

medium:
1,4,8,12,16

sparse:
1,6,11,16
```

Stage 4 不需要建立随机 sensor layout generator。

---

# 29. 推荐 Benchmark Matrix

第一版可以控制在非常小的范围。

例如：

```text
OMA
    1 structural model
    ×
    3 noise levels

MBI
    1 truth model
    ×
    2 sensor layouts
    ×
    2 noise levels
```

总共几个到十几个 case 已经足够。

---

# 30. 不要在 Stage 4 做的内容

Stage 4 暂不加入：

```text
nonlinear structure
base isolation
new structural family
3D beam
colored noise
sensor failure
clock drift
missing samples
large dataset library
complex experiment manager
```

这些都可以后续再讨论。

---

# 31. Stage 4 推荐实施顺序

## Step 0

修复 Stage 3 小问题：

```text
rigid-floor scalar noise
noise seed required
noisy rows consistency
```

---

## Step 1

增加：

```text
reproducible stochastic excitation
```

---

## Step 2

建立：

```text
real OMA baseline
```

---

## Step 3

规范：

```text
Research Dataset
vs
Algorithm Input
```

的访问边界。

---

## Step 4

优先通过：

```text
qREST physical export
```

向 qrest_module 提供算法输入。

---

## Step 5

让至少一个真实算法：

```text
FDD
```

读取生成数据并返回识别结果。

---

## Step 6

实现基础：

```text
frequency matching
frequency error
MAC
```

---

## Step 7

验证：

```text
FDD result
vs
Modal Truth
```

---

## Step 8

使用：

```text
16-story sparse case
```

接入：

```text
mode completion / MBI
```

---

## Step 9

加入少量：

```text
noise level
observation density
model mismatch
```

实验。

---

# 32. Stage 4 最低验收标准

Stage 4 完成后至少应做到：

### OMA

一个真正的 stochastic OMA dataset 可以被：

```text
qrest_module FDD
```

直接读取并运行。

---

### Truth comparison

能够自动得到：

```text
identified frequency
vs
truth frequency
```

和：

```text
MAC
```

---

### MBI

一个 16-story sparse observation case 可以作为：

```text
mode completion / MBI
```

标准输入。

---

### Input isolation

算法运行过程中默认无法访问：

```text
truth/
```

中的信息。

---

### Noise

至少可以完成：

```text
clean
vs
noisy
```

算法结果比较。

---

### Reproducibility

整个：

```text
model
→ excitation
→ observation
→ noise
→ dataset
```

流程在给定 seed 下可重复。

---

# 33. Stage 4 完成后的项目角色

Stage 3 完成后：

> qREST Model 是一个能够生成完整结构真值和有限观测的虚拟监测平台。

Stage 4 完成后，希望进一步成为：

> **能够直接生成算法输入、运行标准研究场景并提供客观真值评价的结构动力学算法 benchmark 平台。**

最终形成：

```text
qrest_model
    Generate Truth
    Generate Monitoring Data
            ↓
qrest_module
    Run Algorithm
            ↓
qrest_model / benchmark
    Compare With Truth
```

---

# 34. 本阶段最重要的原则

Stage 4 不追求：

> “生成更多数据”。

真正目标是：

> **让数据开始被真实算法消费，并证明整个 Truth–Observation–Algorithm–Evaluation 链路成立。**

即：

\[
\boxed{
Truth
\rightarrow
Physical\ Monitoring\ Data
\rightarrow
Algorithm
\rightarrow
Estimated\ Result
\rightarrow
Truth\ Comparison
}
\]

其中算法只能看见真实监测场景下应该能够获得的信息。

这将是 qREST Model 从“模型工具”真正走向“研究基础设施”的关键一步。