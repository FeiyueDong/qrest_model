# qREST Model Stage 3 观测语义与研究数据集体系开发计划

## 1. 阶段定位

Stage 1–Stage 1.5 主要完成：

```text
基础架构重构
配置规范
StructuralModel / Backend 分离
统一 AnalysisResult
Direct / OpenSees 双后端
可靠性与回归验证
```

Stage 2 进一步完成：

```text
Geometry
Euler
Rayleigh
Timoshenko
Shear-Flexure
Theory validation
Physics-limit validation
Direct ≈ OpenSees
Golden regression
```

当前 qREST Model 已经能够提供多种结构理论下的完整动力响应和模态真值。

Stage 3 不再以增加新的结构模型为主要目标，而是解决下一个核心问题：

> **如何把完整结构真值转化为具有明确物理语义、符合真实监测条件、同时方便算法研究的可控观测数据集。**

因此 Stage 3 定位为：

> **观测语义与研究数据集体系建设阶段**

目标是使 qREST Model 从：

> “能够计算多种结构模型响应”

进一步发展为：

> **能够同时提供结构完整真值、真实物理观测和研究型虚拟观测的虚拟结构监测试验平台。**

---

# 2. Stage 2 遗留收口

正式进入 Stage 3 主体开发前，先处理 Stage 2 已发现但不影响其主体完成的少量尾项。

这些问题应尽量在 Stage 3 前期完成，不继续长期积累。

---

# 3. 删除已跟踪的构建产物

虽然 `.gitignore` 已加入：

```text
*.egg-info/
build/
dist/
```

但仓库中仍存在已经被 Git 跟踪的：

```text
qrest_model.egg-info/
```

应删除：

```bash
git rm -r qrest_model.egg-info
```

并确认后续：

```text
git status
```

不会再出现相关构建文件。

---

# 4. 拆分过度增长的 schema

当前：

```text
qrest_model/schema/case.py
```

已经同时负责：

```text
Geometry
Rigid Floor
Shear
Euler
Rayleigh
Timoshenko
Shear-Flexure
Sensor
Damping
Ground Motion
Normalization
```

Stage 2 证明当前架构已经稳定，因此 Stage 3 可以开始拆分 schema。

建议逐步形成：

```text
qrest_model/schema/
    common.py
    geometry.py
    damping.py
    excitation.py

    observation.py

    rigid_floor.py
    shear_building.py

    beam_common.py
    euler.py
    rayleigh.py
    timoshenko.py
    shear_flexure.py
```

要求：

```text
qrest_model.schema
```

仍保持稳定统一导出。

不要求一次性大规模重写。

优先按：

```text
new code → new module
old code → incremental migration
```

方式逐步拆分。

---

# 5. 拆分测试文件

当前：

```text
tests/test_qrest_model.py
```

已经承担大量不同职责。

Stage 3 建议拆为：

```text
tests/
    test_schema.py
    test_geometry.py
    test_analysis.py
    test_observation.py

    models/
        test_shear.py
        test_rigid_floor.py
        test_euler.py
        test_rayleigh.py
        test_timoshenko.py
        test_shear_flexure.py

    datasets/
        test_truth.py
        test_observations.py
        test_research_cases.py

    integration/
        test_opensees.py
        test_qrest_export.py
```

拆分过程不得改变已有测试语义。

---

# 6. Beam sensor mapping 解耦

当前部分 OpenSees backend 复用了：

```text
direct_euler.build_sensor_result()
```

形成：

```text
OpenSees backend
        ↓
Direct backend
```

的非理想依赖。

Stage 3 应将二维模型的观测映射提取至独立模块，例如：

```text
qrest_model/observations/
    beam.py
```

或：

```text
qrest_model/postprocess/
    beam_observation.py
```

使关系变为：

```text
Direct ─────┐
            ↓
       Observation Mapping
            ↑
OpenSees ───┘
```

---

# 7. OpenSees matrix provenance 明确化

目前 OpenSees `AnalysisResult` 中：

```text
mass_matrix
stiffness_matrix
damping_matrix
modal
```

主要来自 qrest_model 自己的理论矩阵，而 OpenSees 独立提供：

```text
OpenSees eigen
OpenSees dynamic response
```

Stage 3 应明确 metadata：

```text
matrix_source
modal_source
response_source
```

例如：

```json
{
  "matrix_source": "qrest_model_theory",
  "modal_source": "qrest_model_matrix",
  "backend_modal_source": "opensees_eigen",
  "response_source": "opensees"
}
```

避免以后将：

```text
AnalysisResult.mass_matrix
```

误认为 OpenSees 内部直接提取的 global matrix。

---

# 8. OpenSees ground-motion validation 独立性增强

Stage 2 的二维模型 OpenSees 时程使用：

```text
qrest_model theory
→ equivalent base inertia load
→ OpenSees
```

因此 Direct/OpenSees 虽然能够独立验证 element 和 solver，但：

```text
base excitation mapping
```

仍共用了同一套理论。

Stage 3 增加至少一个独立验证路径。

推荐：

```text
OpenSees MultiSupport
+
imposed base motion
```

或其他真正的 imposed support motion。

形成：

```text
Direct
    equivalent inertia load

          ↕ compare

OpenSees
    imposed support motion
```

重点验证：

```text
base excitation
relative / absolute response
consistent mass coupling
```

不要求替换现有 OpenSees backend。

该功能可作为专用 integration test。

---

# 9. Rayleigh 模型理论命名说明

当前 Rayleigh 模型采用：

```text
Euler consistent beam mass
+
nodal rotational inertia
```

这属于：

> 离散 Rayleigh-type beam。

Stage 3 应在 README / model documentation 中明确：

```text
rotational_inertia
```

是：

> 节点/楼层集中转动惯量。

不要将其描述成严格的连续分布 Rayleigh beam finite element。

必要时字段可逐步改为：

```text
nodal_rotational_inertia
```

但需考虑配置兼容。

---

# 10. CI 建设

Stage 3 开始正式加入 CI。

至少包含：

```text
Unit / core tests
OpenSees integration tests
```

推荐：

```text
pytest -m "not opensees"
```

以及：

```text
QREST_RUN_OPENSEES_TESTS=1 pytest -m opensees
```

必要时 OpenSees 测试可：

```text
manual
nightly
or separate workflow
```

但核心测试必须在每次提交时执行。

---

# 11. Stage 3 核心问题

Stage 2 后出现了一个重要语义问题：

二维梁模型的结构状态为：

\[
q=
[U_1,\Theta_1,U_2,\Theta_2,\ldots]^T
\]

其中：

```text
U
```

可以对应现实中的水平位移、速度或加速度观测。

但：

```text
Theta
```

首先是：

> 结构广义自由度。

它并不自动等价于：

> 一个现实监测传感器通道。

同样的问题未来还会出现在：

```text
Rz
Rx
Ry
curvature
shear deformation
modal coordinate
```

因此必须建立一个新的基本原则：

\[
\boxed{
Structural\ State
\neq
Physical\ Observation
}
\]

---

# 12. Stage 3 核心语义原则

Stage 3 正式建立三类数据概念。

---

## 12.1 Structural Truth

结构模型自身完整状态。

例如：

```text
Ux
Uy
Rz

U
Theta
```

以及：

```text
displacement
velocity
acceleration
```

这些量的存在只由：

> StructuralModel

决定。

不取决于是否存在现实传感器。

---

## 12.2 Derived Structural Quantity

由结构状态计算得到，但本身不是基本 DOF 的结构量。

例如：

```text
inter-story drift
curvature
shear deformation
story deformation
relative rotation
```

例如 Timoshenko 模型可以进一步定义：

\[
\gamma
=
\frac{\partial U}{\partial z}
-
\Theta
\]

其具体离散定义后续根据模型实现确定。

---

## 12.3 Observation

从完整结构状态中抽取、组合或映射得到的数据。

基本关系定义为：

\[
\boxed{
y=H x
}
\]

或更一般：

\[
y=
H_q q+
H_v\dot q+
H_a\ddot q
\]

其中：

```text
H
```

称为：

> Observation Operator

---

# 13. Observation 再分为两类

Stage 3 采用：

```text
Observation
├── Physical Sensor
└── Virtual Probe
```

---

# 14. Physical Sensor

Physical Sensor 表示：

> 符合真实监测设备和物理观测语义的通道。

当前优先支持：

```text
translation displacement
translation velocity
translation acceleration
```

方向：

```text
X
Y
Z
```

对于刚性楼板：

\[
u_x^{sensor}
=
U_x-yR_z
\]

\[
u_y^{sensor}
=
U_y+xR_z
\]

这些虽然依赖：

```text
Rz
```

但传感器实际测得仍是：

```text
X/Y translation
```

因此属于 Physical Sensor。

---

# 15. Virtual Probe

Virtual Probe 表示：

> 为数值研究方便，从模型状态中直接抽取或构造的观测量。

例如：

```text
Theta
Rz
modal coordinate
curvature
story shear deformation
```

Virtual Probe 可以：

```text
用于测试
用于可视化
用于算法研究
用于 sensitivity study
```

但默认：

> 不作为普通 qREST physical Instrument channel 输出。

---

# 16. Theta 的正式语义

Stage 3 明确：

```text
Theta
```

是：

> beam-like model 的结构广义转角自由度。

它属于：

```text
Structural Truth
```

可以通过：

```text
Virtual Probe
```

被提取。

但不默认属于：

```text
Physical Sensor
```

---

# 17. Theta 在不同理论中的解释

Euler：

\[
\Theta
=
\frac{\partial U}{\partial z}
\]

Timoshenko：

\[
\Theta
\]

为独立截面转角。

通常：

\[
\Theta
\neq
\frac{\partial U}{\partial z}
\]

因此 Stage 3 文档和 API 中禁止将：

```text
Theta
```

简单描述成：

```text
mode-shape slope
```

统一称为：

```text
section / generalized bending rotation
```

---

# 18. Rz 的语义同步调整

现有 rigid-floor：

\[
[U_x,U_y,R_z]
\]

中的：

```text
Rz
```

同样首先属于：

```text
Structural Truth
```

普通偏心 X/Y 传感器的响应通过：

\[
H
\]

从：

\[
[U_x,U_y,R_z]
\]

映射得到。

除非未来明确建立：

```text
rotation sensor
```

否则：

```text
Rz
```

不自动作为 physical qREST channel。

---

# 19. 新 Observation Schema

Stage 3 建议逐步废除：

```text
模型 DOF
=
sensor DOF
```

的隐式设计。

可以建立：

```python
ObservationConfig
```

---

# 20. 推荐基础结构

例如：

```python
@dataclass(frozen=True)
class ObservationConfig:
    observation_id: str
    story: int
    kind: str
    quantity: str
```

其中：

```text
kind
```

至少区分：

```text
physical
virtual
```

---

# 21. Physical observation 示例

例如：

```json
{
  "id": "roof_acc_x",
  "kind": "physical",
  "story": 10,
  "sensor_type": "accelerometer",
  "direction": "X",
  "quantity": "acceleration"
}
```

---

# 22. Virtual probe 示例

```json
{
  "id": "roof_theta",
  "kind": "virtual",
  "story": 10,
  "dof": "Theta",
  "quantity": "displacement"
}
```

---

# 23. 兼容旧 sensors 配置

Stage 3 不要求立即破坏：

```text
sensors
```

旧配置。

推荐：

```text
旧 sensors
    ↓ normalize
PhysicalObservationConfig
```

对于 beam model 当前存在：

```text
dof = Theta
```

的旧 BeamSensorConfig：

建议：

```text
normalize
→ VirtualProbe
```

并发出一次 legacy warning。

---

# 24. Observation Operator

Stage 3 建立统一观测映射概念：

\[
y=Hx
\]

---

## 24.1 Shear model

对于某楼层：

\[
H=
[0,\ldots,1,\ldots]
\]

---

## 24.2 Beam U

\[
H=
[0,\ldots,1,0,\ldots]
\]

---

## 24.3 Beam Theta

Virtual Probe：

\[
H=
[0,\ldots,0,1,\ldots]
\]

---

## 24.4 Rigid-floor X sensor

\[
H_s=
[1,0,-y]
\]

---

## 24.5 Rigid-floor Y sensor

\[
H_s=
[0,1,x]
\]

---

# 25. Observation Operator 的目标

当前不同模型分别存在：

```text
rigid floor sensor mapping
shear sensor mapping
beam sensor mapping
```

Stage 3 不要求一次性做成高度抽象的通用矩阵系统。

但需要逐步统一为：

```text
Structural State
        ↓
Observation Mapping
        ↓
Observation Result
```

最终可扩展为：

```python
ObservationOperator
```

---

# 26. AnalysisResult 与 ObservationResult

当前：

```text
AnalysisResult.sensors
```

语义开始不足。

Stage 3 建议引入：

```text
ObservationResult
```

例如：

```text
AnalysisResult
├── truth
├── derived
├── observations
├── modal
├── M/K/C
└── metadata
```

但为减少破坏，可以分阶段迁移。

第一阶段允许：

```text
AnalysisResult.sensors
```

继续作为 compatibility alias。

---

# 27. 推荐最终数据结构

目标结构：

```text
AnalysisResult

├── time

├── truth
│   ├── relative
│   ├── absolute
│   └── ground

├── derived
│   └── optional derived structural quantities

├── observations
│   ├── physical
│   └── virtual

├── modal

├── mass_matrix
├── stiffness_matrix
├── damping_matrix

└── metadata
```

实际实现可以继续复用现有：

```text
relative
absolute
ground
```

避免 Stage 3 变成 AnalysisResult 的大型重构。

---

# 28. Model Truth 正式化

Stage 2 已经能够输出完整响应和模态。

Stage 3 要将这一能力正式定义为：

> Model Truth。

Model Truth 至少包括：

```text
model type
geometry
DOF layout
M
K
C

modal frequencies
modal shapes

full displacement
full velocity
full acceleration

ground motion
structural parameters
```

---

# 29. Truth 与 Observation 必须分离

研究数据集不得再把：

```text
完整结构响应
```

和：

```text
测点响应
```

混为一个概念。

明确：

```text
Truth
    = 模型完整状态

Observation
    = 算法实际可获得信息
```

---

# 30. Research Dataset 目录

建议建立：

```text
dataset/
    manifest.json
    config.json

    truth/
        modal.npz
        response.npz
        matrices.npz
        structural_properties.json

    observations/
        physical/
            acceleration.csv
            ...
        virtual/
            ...
    
    metadata/
        observation.json
        provenance.json
```

实际文件格式可以根据项目已有约定适当简化。

重点是：

> 逻辑分层必须明确。

---

# 31. 数据文件格式建议

对于内部 research dataset：

优先使用：

```text
NPZ
JSON
CSV
```

组合。

建议：

```text
large numeric array
→ NPZ

configuration / metadata
→ JSON

human-readable sensor data
→ CSV
```

不要强制所有 truth 都使用 qREST 格式。

---

# 32. qREST Export 的职责边界

qREST export 用于：

> 模拟真实监测数据文件。

因此默认只导出：

```text
Physical Observation
```

不直接导出：

```text
Theta truth
Rz truth
modal coordinates
curvature
```

这些属于 research truth/probe。

---

# 33. Virtual Probe 不进入 InstrumentInfo

Stage 3 必须修复当前潜在问题：

```text
Theta
→ default direction X
→ qREST channel
```

禁止这种隐式转换。

如果 observation：

```text
kind = virtual
```

则：

```text
qREST exporter
```

应：

```text
ignore
```

或在显式要求 physical export 时：

```text
raise clear error
```

---

# 34. Future rotational physical sensors

Stage 3 不需要立即实现旋转传感器。

但 schema 应留出扩展空间：

```text
tiltmeter
gyroscope
angular acceleration sensor
```

例如未来：

```text
tiltmeter
→ Theta

gyro
→ Theta_dot
```

只有明确声明：

```text
sensor_type = rotational
```

才可进入 physical observation。

---

# 35. Relative / Absolute 语义

Stage 3 延续 Stage 1.5 约定：

平动：

\[
U^{abs}
=
U^{rel}+U_g
\]

目前纯平动地面输入下：

\[
\Theta^{abs}
=
\Theta^{rel}
\]

但文档应明确：

> 这只是由于当前没有 rotational ground motion。

未来加入：

```text
base rocking
rotational support excitation
```

时：

\[
\Theta^{abs}
=
\Theta^{rel}
+
\Theta_g
\]

因此禁止把：

```text
Theta absolute = relative
```

写死为结构定义。

---

# 36. Research Dataset Pipeline

当前官方：

```text
qrest_model/datasets/
```

主要支持：

```text
story3d
shear1d
```

Stage 3 正式扩展：

```text
Euler
Rayleigh
Timoshenko
Shear-Flexure
```

---

# 37. DatasetCase 不再绑定少量 model alias

当前类似：

```text
story3d
shear1d
```

的 dataset model_type 应逐渐改为直接支持：

```text
schema model.type
```

推荐：

```text
rigid_floor_shear_3d
shear_building_1d
euler_beam_2d
rayleigh_beam_2d
timoshenko_beam_2d
shear_flexure_building_2d
```

兼容旧 alias。

---

# 38. DatasetCase 新职责

DatasetCase 建议包含：

```text
model config

truth policy

observation config

noise config

export policy

research tags
```

例如：

```json
{
  "name": "euler_sparse_5floor",

  "model": {...},

  "observations": {...},

  "research": {
    "task": "mode_completion",
    "family": "euler",
    "sensor_density": "sparse"
  }
}
```

---

# 39. 第一批 Research Dataset 不加入噪声

Stage 3 第一版优先建立：

> deterministic ground-truth datasets。

先不立即加入：

```text
sensor noise
bias
drift
missing data
clock error
```

原因：

```text
先验证 observation semantics
先验证 truth / observation pipeline
```

噪声适合 Stage 3 后半或 Stage 4。

---

# 40. 第一批 OMA Research Dataset

建议建立少量代表性 case。

例如：

```text
OMA-S01
shear model
well separated modes

OMA-E01
Euler model

OMA-T01
Timoshenko model

OMA-SF01
shear-flexure mixed deformation
```

统一使用：

```text
physical translational acceleration
```

作为算法输入。

---

# 41. OMA 数据集重点

每个 case 保存：

```text
true frequency
true mode shapes

full response
physical sensor response

sensor layout
sampling rate
input definition
```

算法侧只能读取：

```text
physical observation
```

Truth 用于验证。

---

# 42. 第一批 Mode Completion / MBI Dataset

Stage 3 建议重点建立：

```text
MC / MBI
```

研究数据集。

---

# 43. Full Truth

例如：

\[
\Phi_\text{truth}
\]

来自全部楼层。

对于 beam：

\[
\Phi_\text{truth}
=
[
U_1,\Theta_1,
U_2,\Theta_2,
...
]^T
\]

---

# 44. Measured Observation

真实监测情形优先：

```text
only U
```

例如只选：

```text
story 1
story 4
story 8
story 12
story 16
```

得到：

\[
\Phi_\text{obs}
=
H\Phi_\text{truth}
\]

---

# 45. Virtual Probe Study

在部分专门研究 case 中，可以加入：

```text
Theta virtual observation
```

用于回答：

> 如果能够获得少量转动信息，振型补全效果会提高多少？

这类 case 必须明确标记为：

```text
virtual observation
```

而不是现实物理监测配置。

---

# 46. 第一批 MBI 模型族组合

建议建立：

```text
MBI-S
truth = shear

MBI-E
truth = Euler

MBI-R
truth = Rayleigh

MBI-T
truth = Timoshenko

MBI-SF
truth = shear-flexure
```

---

# 47. Model Mismatch Dataset

Stage 3 可以开始为后续研究预留一个重要类型：

> Model-form mismatch。

例如：

```text
truth:
    Timoshenko

completion assumption:
    Euler
```

或者：

```text
truth:
    shear-flexure

assumed model:
    shear
```

本阶段不需要实现 MBI 算法。

只需要确保 dataset 能够明确标记：

```text
truth model family
observation layout
```

---

# 48. Observation Density

建议定义标准监测密度：

```text
full
dense
medium
sparse
very_sparse
```

例如 16 层：

```text
full
1–16

dense
1,3,5,7,9,11,13,16

medium
1,4,8,12,16

sparse
1,6,11,16
```

实际规则可以配置，而不是硬编码。

---

# 49. Observation Layout Generator

Stage 3 建议将测点布局从固定 case 中适度抽象出来。

例如：

```text
ObservationLayout
```

支持：

```text
stories
directions
sensor type
quantity
```

未来再扩展：

```text
random sparse layout
leave-one-out
missing floor
```

---

# 50. ObservationResult 数据

每一个 observation channel 至少记录：

```text
id
kind
sensor_type / probe_type
story
location
direction / dof
quantity
unit
source state
```

---

# 51. 单位语义

Stage 3 正式避免：

```text
U
Theta
```

共享相同单位体系。

例如：

```text
U
m

velocity U
m/s

acceleration U
m/s²
```

而：

```text
Theta
rad

Theta_dot
rad/s

Theta_ddot
rad/s²
```

Derived quantities 也应有明确 unit。

---

# 52. Observation provenance

Research dataset 每个观测应能追踪来源。

例如：

```json
{
  "id": "roof_x",
  "kind": "physical",
  "source": {
    "type": "state_mapping",
    "model_dofs": ["Ux", "Rz"]
  }
}
```

对于 beam：

```json
{
  "id": "roof_theta",
  "kind": "virtual",
  "source": {
    "type": "generalized_dof",
    "dof": "Theta"
  }
}
```

---

# 53. Truth provenance

每个 dataset 应保存：

```text
qrest_model version / git commit
model type
backend
config
random seed
```

如果使用：

```text
Direct
```

或：

```text
OpenSees
```

必须在 metadata 中明确。

---

# 54. Dataset reproducibility

相同：

```text
config
seed
backend
```

必须生成一致结果。

如果未来增加随机过程，统一：

```text
seed
```

进入 manifest。

---

# 55. Dataset validation

Stage 3 新增：

```text
validate_dataset()
```

至少检查：

```text
truth dimensions
observation dimensions
channel count
time consistency
units
metadata consistency
sensor story validity
physical/virtual separation
```

---

# 56. Physical observation validation

例如：

```text
physical translational sensor
```

不得：

```text
dof = Theta
```

除非：

```text
sensor_type
```

明确支持 rotation。

---

# 57. Virtual probe validation

Virtual probe 可以访问：

```text
structural DOF
derived quantities
```

但必须声明：

```text
kind = virtual
```

---

# 58. qREST export validation

导出前检查：

```text
all exported channels are physical
```

若发现：

```text
virtual probe
```

则默认不导出。

可以提供：

```text
--include-virtual
```

用于内部 debug CSV。

但不得伪装成：

```text
qREST InstrumentInfo
```

---

# 59. Research dataset 与 qREST dataset 分离

Stage 3 建议明确：

```text
Research Dataset
    ≠
qREST Dataset
```

Research Dataset：

```text
Truth + Physical + Virtual
```

qREST Dataset：

```text
Physical Monitoring Data
```

两者可以来源于同一个 case。

---

# 60. 推荐流程

最终目标：

```text
Model Config
     ↓
StructuralModel
     ↓
Backend
     ↓
AnalysisResult
     ↓
Model Truth
     ↓
Observation Operator
     ↓
┌─────────────────────────────┐
│ Physical Observations       │
│ Virtual Probes              │
└─────────────────────────────┘
     ↓
Research Dataset
     │
     └── Physical subset
            ↓
        qREST Export
```

---

# 61. Stage 3 推荐目录

建议逐步形成：

```text
qrest_model/
    observations/
        __init__.py
        base.py
        physical.py
        virtual.py
        rigid_floor.py
        shear.py
        beam.py

    datasets/
        cases.py
        generator.py
        truth.py
        observations.py
        validation.py
        manifest.py

    exporters/
        research_dataset.py
        qrest_dataset.py
```

具体目录可以根据现有结构调整。

关键是职责清晰。

---

# 62. 第一阶段不实现统一超泛化 H Matrix DSL

虽然理论上：

\[
y=Hx
\]

很漂亮，但 Stage 3 不建议立即设计一个高度抽象的：

```text
arbitrary matrix observation language
```

第一版优先：

```text
typed observation
```

例如：

```text
translation sensor
rigid-floor offset sensor
generalized DOF probe
```

内部再生成 H。

避免配置变成：

```text
用户直接填 matrix
```

导致工程语义丢失。

---

# 63. Stage 3 不增加新的 Structural Model

本阶段原则上不增加：

```text
3D beam
base-isolated
nonlinear
vertical model
```

除非为 observation pipeline 修复所必需。

重点是验证：

> 已有 6 类模型能否稳定产生研究数据。

---

# 64. Stage 3 不立即实现 nonlinear observation

暂不处理：

```text
sensor saturation
clipping
nonlinear measurement
```

Observation Operator 第一版保持线性或显式简单映射。

---

# 65. Stage 3 不立即实现真实噪声模型

可以预留：

```text
noise
```

配置，但第一版保持：

```text
noise-free
```

主要目的是建立：

```text
truth → observation
```

基线。

---

# 66. Stage 3 推荐实施顺序

## Step 0

完成 Stage 2 cleanup：

```text
remove tracked egg-info
schema split
test split
beam observation mapping decoupling
matrix provenance
Rayleigh documentation
CI
```

---

## Step 1

定义：

```text
Structural Truth
Derived Quantity
Observation
```

三类正式语义。

---

## Step 2

定义：

```text
PhysicalObservationConfig
VirtualProbeConfig
```

并提供旧 sensor schema compatibility。

---

## Step 3

实现统一：

```text
ObservationResult
```

数据结构。

---

## Step 4

将：

```text
shear
beam
rigid-floor
```

现有 sensor mapping 迁移到 observation layer。

---

## Step 5

实现：

```text
Observation Operator
```

基础接口。

---

## Step 6

Theta / Rz 正式归类为：

```text
Structural Truth
```

并支持：

```text
Virtual Probe
```

---

## Step 7

修改 qREST exporter：

```text
Physical only
```

并禁止 virtual observation 被错误转换为 X/Y/Z channel。

---

## Step 8

建立：

```text
Model Truth exporter
```

---

## Step 9

扩展 DatasetCase：

```text
six model families
```

---

## Step 10

建立新的：

```text
Research Dataset Generator
```

---

## Step 11

建立：

```text
dataset manifest
provenance
validation
```

---

## Step 12

增加 beam-family research dataset。

---

## Step 13

建立第一批：

```text
OMA benchmark datasets
```

---

## Step 14

建立第一批：

```text
Mode Completion / MBI benchmark datasets
```

---

## Step 15

增加：

```text
Direct equivalent excitation
vs
OpenSees imposed support motion
```

独立 integration validation。

---

# 67. Stage 3 核心测试

必须增加以下测试。

---

## 67.1 Truth independence

同一模型不同 observation layout：

```text
Truth
```

必须完全一致。

即：

```text
sensor configuration
```

不能改变：

```text
M
K
modal
full response
```

---

## 67.2 Observation consistency

Physical U sensor：

\[
y=H_Ux
\]

必须与 truth 对应平动响应一致。

---

## 67.3 Rigid-floor mapping

验证：

\[
a_x=a_{Ux}-y\alpha_z
\]

\[
a_y=a_{Uy}+x\alpha_z
\]

继续成立。

---

## 67.4 Theta virtual probe

验证：

```text
Theta probe
```

等于 truth 中相应：

```text
Theta
```

分量。

---

## 67.5 Physical/Virtual export boundary

确保：

```text
Physical
→ qREST export
```

而：

```text
Virtual
→ not qREST physical channel
```

---

## 67.6 Unit validation

验证：

```text
U → m
Theta → rad
```

以及其时间导数量。

---

## 67.7 Dataset reproducibility

同一 case 连续生成两次：

```text
truth
observations
manifest
```

核心数值一致。

---

## 67.8 Sparse observation

改变观测楼层后：

```text
truth unchanged
observation changed
```

---

## 67.9 OMA benchmark

每个 OMA case 必须包含：

```text
input data
truth frequency
truth mode shape
```

---

## 67.10 MBI benchmark

每个 MBI case 必须包含：

```text
full truth modes
measured DOFs
observation operator / layout
```

---

# 68. Stage 3 Golden Research Cases

建议建立少量固定 case：

```text
research/reference/
```

例如：

```text
oma_shear_10story
oma_euler_10story
oma_timoshenko_10story

mbi_shear_16story_sparse
mbi_euler_16story_sparse
mbi_timoshenko_16story_sparse
mbi_shear_flexure_16story_sparse
```

---

# 69. Dataset complexity 控制

第一批 benchmark case 不追求数量。

建议：

> 少而稳定。

每一类只保留：

```text
1–3
```

个有明确研究含义的 case。

避免 Stage 3 演化成大量难以维护的配置集合。

---

# 70. 第一批 MBI 推荐重点

结合当前研究方向，优先建立：

### Case A

```text
Truth:
Shear

Observation:
5 sparse translational floors
```

---

### Case B

```text
Truth:
Euler

Observation:
same 5 floors
U only
```

---

### Case C

```text
Truth:
Timoshenko

Observation:
same 5 floors
U only
```

---

### Case D

```text
Truth:
Shear-Flexure

Observation:
same 5 floors
U only
```

这样可以研究：

> 同样的监测稀疏程度，在不同结构变形机制下，模态补全难度如何变化。

---

# 71. Optional Theta Probe Case

再额外建立一个：

```text
Timoshenko
U sparse
+
one or two Theta virtual probes
```

用于研究：

> 少量转角信息对补全性能的理论上限帮助。

必须明确：

```text
virtual study
```

而非实际监测 baseline。

---

# 72. Stage 3 与 qREST 算法库的关系

Stage 3 生成的数据最终应该能够服务：

```text
FDD
EFDD
SSI
MBI
response reconstruction
```

但 qrest_model 不负责实现这些算法。

qrest_model 只负责：

```text
truth
observation
dataset
```

算法实现继续属于：

```text
qrest_module
```

---

# 73. Stage 3 验收标准

Stage 3 完成后，应满足以下条件。

---

## 73.1 Stage 2 cleanup

关键遗留问题完成：

```text
egg-info removed
schema/test split
backend observation dependency cleaned
CI available
metadata provenance clear
```

---

## 73.2 Observation semantics

正式区分：

```text
Structural Truth
Derived Quantity
Physical Observation
Virtual Observation
```

---

## 73.3 Theta / Rz

`Theta`、`Rz` 不再隐式等同于普通 physical sensor。

---

## 73.4 Observation layer

所有模型的传感器/观测结果通过独立 Observation 层形成。

---

## 73.5 qREST export

只导出符合现实语义的：

```text
physical observation
```

---

## 73.6 Model Truth

所有模型均能输出结构完整真值。

---

## 73.7 Dataset family

官方 dataset pipeline 支持当前全部 6 种 model.type。

---

## 73.8 Research Dataset

能够输出：

```text
truth
physical observations
virtual probes
manifest
```

---

## 73.9 OMA benchmark

至少建立：

```text
shear
Euler
Timoshenko
```

三类代表性 OMA 数据集。

---

## 73.10 MBI benchmark

至少建立：

```text
shear
Euler
Timoshenko
Shear-Flexure
```

四类 sparse observation benchmark。

---

## 73.11 Reproducibility

所有 reference dataset 可重复生成。

---

## 73.12 Validation

能够自动检查：

```text
truth
observation
qREST export
```

三者语义和维度一致性。

---

# 74. Stage 3 完成后的体系

预期形成：

```text
                  Structural Model
                         │
                         ▼
                      Backend
                         │
                         ▼
                  Analysis Result
                         │
                         ▼
                  Structural Truth
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
      Derived Quantities      Observation Model
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                         ▼                     ▼
                 Physical Sensors       Virtual Probes
                         │                     │
                         └──────────┬──────────┘
                                    ▼
                             Research Dataset
                                    │
                                    ▼
                            Physical subset
                                    │
                                    ▼
                               qREST Data
```

---

# 75. Stage 3 完成后的项目定位

Stage 2 结束时：

> qREST Model 已经是一个多结构模型线性动力学验证框架。

Stage 3 完成后，希望进一步成为：

> **能够提供完整结构真值、现实有限观测以及可控研究观测的虚拟结构监测试验平台。**

它的主要价值将不再只是：

```text
generate response
```

而是：

```text
generate truth
define observation
generate benchmark
evaluate algorithm
```

---

# 76. 后续阶段

Stage 3 完成后，再考虑两条独立扩展路线。

---

## Route A：Observation Complexity

例如：

```text
noise
sensor bias
missing channels
missing samples
clock drift
channel orientation error
sensor failure
```

用于更真实的监测算法鲁棒性研究。

---

## Route B：Structural Complexity

例如：

```text
3D beam-like model
vertical DOF
rocking
base isolation
nonlinear story
hysteretic model
multi-support excitation
```

---

# 77. 本阶段最重要的成功标准

Stage 3 最核心的成功标准不是：

> “又增加了一批 dataset 文件”。

而是：

> **模型拥有的结构状态、研究者可以查看的真值，以及现实传感器能够获得的观测，不再被混为同一种数据。**

最终应满足：

\[
\boxed{
Structural\ Truth
\xrightarrow{Observation\ Operator}
Observation
}
\]

并进一步：

\[
\boxed{
Physical\ Observation
\subset
Research\ Observation
}
\]

对于 qREST Model 来说，这意味着：

> **结构模型负责描述真实结构状态，观测模型负责描述我们能看见什么。**

这一边界一旦建立，后续无论是 `Theta`、`Rz`、3D rotation、rocking、曲率、模态坐标，还是新的传感器类型，都可以在同一套逻辑下自然扩展，而不再需要将每一种结构变量强行解释为物理监测通道。