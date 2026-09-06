# qREST Model Stage 1.5 架构收口与可靠性优化计划

## 1. 阶段定位

Stage 1 已完成 qREST Model 的第一轮架构重构，项目已经具备：

- `schema_version` 与明确的 `model.type`；
- 统一配置校验；
- `StructuralModel` 层；
- `LinearSystem`；
- 公共 Newmark 求解器；
- 公共模态分析；
- `AnalysisResult`；
- Direct / OpenSees 统一入口；
- exporter、dataset、CLI 等基础模块；
- Python package 与 `pyproject.toml`。

当前项目已经从若干独立分析脚本演化为一个小型的结构动力分析与虚拟监测数据生成框架。

但现阶段仍处于：

> **新架构已经建立，但旧实现与兼容路径尚未完全退出核心流程**

的状态。

Stage 1.5 的目标不是继续增加新的结构模型，而是完成架构收口，使项目真正满足：

```text
Model Configuration
        ↓
Normalized Schema
        ↓
StructuralModel
        ↓
Backend
        ↓
AnalysisResult
        ↓
Postprocess / Exporter / Dataset
```

其中：

> `AnalysisResult` 应成为所有内部模块唯一认可的分析结果表示。

本阶段完成后，再正式进入新的模型能力扩展阶段。

---

# 2. 本阶段核心目标

Stage 1.5 重点解决以下六个问题：

1. 统一不同模型的相对/绝对响应语义；
2. 清除 library 对 `scripts/` 的反向依赖；
3. 让 `AnalysisResult` 成为内部唯一结果格式；
4. 增加结构模型与阻尼参数的物理有效性检查；
5. 进一步统一 DirectBackend；
6. 建立真正可靠的 OpenSees 集成测试和数值回归基准。

本阶段原则：

> 不主动增加新的结构物理能力，只完善现有框架。

---

# 3. 统一响应语义

## 3.1 当前问题

当前 `rigid_floor_shear_3d` 的结果已经明确区分：

```text
relative response
absolute response
ground response
```

并能够提供：

```text
relative displacement
relative velocity
relative acceleration

absolute displacement
absolute velocity
absolute acceleration

ground displacement
ground velocity
ground acceleration
```

但 `shear_building_1d` 目前主要只保存相对响应。

在 dataset exporter 中，又额外重新读取 ground motion，并将地面运动补回得到绝对响应。

因此当前两个模型存在不同语义：

```text
rigid_floor:
    Backend → relative + absolute + ground

shear:
    Backend → relative
    Exporter → 再构造 absolute
```

同时 SensorResult 中 `value` 的语义也并不完全统一。

这是当前最优先需要解决的问题。

---

# 4. 响应统一目标

无论模型类型如何，所有 Backend 都必须返回统一：

```python
AnalysisResult(
    time=...,
    relative=...,
    absolute=...,
    ground=...,
    sensors=...
)
```

其中统一规定：

```text
relative
    结构相对于地面运动的响应

ground
    输入地面运动

absolute
    relative + ground translation
```

旋转自由度不添加地面平动：

```text
Rz_absolute = Rz_relative
```

当前只考虑平动地面输入。

---

## 4.1 SensorResult 统一

建议明确：

```text
relative_value
    对应传感器方向的相对响应

value
    对应传感器方向的绝对响应
```

所有模型均遵循相同规则。

例如加速度测点：

```text
value = absolute acceleration
relative_value = relative acceleration
```

不能因为模型类型不同而改变含义。

---

## 4.2 Exporter 职责调整

Exporter 不应再执行：

```text
relative → absolute
```

这样的动力学后处理。

Exporter 只负责：

```text
AnalysisResult
    ↓
CSV / JSON / qREST
```

因此 shear time-history exporter 中重新加载 ground motion、再次积分地面运动的逻辑应删除。

---

# 5. `AnalysisResult` 成为唯一内部结果格式

## 5.1 当前问题

现在已经存在：

```python
AnalysisResult
```

但内部仍有很多流程：

```text
AnalysisResult
    ↓
to_legacy_dict()
    ↓
Exporter / Dataset
```

部分 dataset generator 甚至仍直接调用旧：

```text
run_direct_shear()
run_direct_stiffness()
```

获取 dict。

因此目前的 `AnalysisResult` 还只是统一 API 的一层 facade，而不是整个项目真正的数据核心。

---

# 6. AnalysisResult 优化目标

项目内部统一使用：

```python
AnalysisResult
```

禁止新的 library 代码依赖 legacy dict。

推荐依赖关系：

```text
Backend
   ↓
AnalysisResult
   ├── Dataset
   ├── Exporter
   ├── Validation
   ├── CLI
   └── Postprocess
```

只有兼容旧接口时允许：

```text
AnalysisResult
        ↓
to_legacy_dict()
```

即：

> Legacy dict 必须位于架构边界，而不能重新流入内部核心模块。

---

# 7. 完善 AnalysisResult

当前 `AnalysisResult` 已经具有较好的基本结构。

Stage 1.5 建议进一步加强其 invariant 检查。

至少验证：

### Time

```text
time.ndim == 1
time strictly increasing
time finite
```

### Response

```text
relative.shape[0] == len(time)
absolute.shape == relative.shape
```

### Matrix

```text
M.shape == (ndof, ndof)
C.shape == (ndof, ndof)
K.shape == (ndof, ndof)
```

并检查：

```text
finite
symmetric
```

其中质量矩阵和刚度矩阵至少应满足合理的数值对称性。

---

# 8. ModalResult 正式进入 AnalysisResult

## 8.1 当前问题

`AnalysisResult` 已经拥有：

```python
modal: ModalResult | None
```

但 Backend 当前没有实际填充。

Exporter 又独立执行：

```text
modal_analysis(M, K)
```

导致模态分析仍存在重复入口。

---

## 8.2 优化目标

对于当前所有线性结构模型，Backend 构建：

```text
M
K
```

后统一执行：

```python
modal = modal_analysis(M, K)
```

并保存：

```python
result.modal
```

以后所有模块：

```text
Exporter
Dataset
Algorithm config generator
Validation
```

统一读取：

```text
result.modal
```

而不再重新执行特征值分析。

---

# 9. 清除 library → scripts 反向依赖

## 9.1 当前问题

当前仍存在类似：

```python
qrest_model.datasets.generator
    ↓
scripts.make_algorithm_configs

qrest_model.datasets.generator
    ↓
scripts.map_sensors
```

这种依赖。

这意味着：

```text
library → scripts
```

与理想架构方向相反。

`scripts/` 应当只是应用入口，不应该保存 library 必需的业务逻辑。

---

# 10. 依赖方向目标

最终严格保持：

```text
scripts
CLI
tests
   ↓
qrest_model
```

禁止：

```text
qrest_model
   ↓
scripts
```

---

## 10.1 推荐迁移

将：

```text
scripts/map_sensors.py
```

中的核心逻辑迁入：

```text
qrest_model/postprocess/
```

或：

```text
qrest_model/exporters/
```

例如：

```text
qrest_model/postprocess/sensor_mapping.py
```

---

将：

```text
scripts/make_metadata.py
```

核心逻辑迁入：

```text
qrest_model/exporters/qrest_metadata.py
```

---

将：

```text
scripts/make_algorithm_configs.py
```

核心逻辑迁入：

```text
qrest_model/exporters/algorithm_config.py
```

或：

```text
qrest_model/datasets/algorithm_config.py
```

根据其最终职责决定。

---

## 10.2 Scripts 最终形式

每个 script 最终只应承担：

```text
argparse
↓
调用 qrest_model API
↓
打印结果
```

原则上应控制为很薄的 CLI wrapper。

---

# 11. 结构物理有效性检查

## 11.1 当前问题

目前已经能够检查：

```text
mass > 0
jz > 0
kx > 0
ky > 0
```

但：

> 单个参数为正，不保证整个结构刚度矩阵有效。

例如所有抗侧构件均位于质心：

```text
x = 0
y = 0
```

则可能出现：

```text
Kθθ = 0
```

导致结构存在自由刚体扭转自由度。

类似问题可能直到模态分析或动力分析阶段才暴露。

---

# 12. Story stiffness 有效性检查

对于：

```text
rigid_floor_shear_3d
```

建议每层计算：

\[
K_i
\]

并检查：

```text
K_i symmetric
K_i positive definite
```

可以使用：

```python
eigvalsh(K_story)
```

若：

```text
min(eigenvalue) <= tolerance
```

则明确报错：

```text
Story N stiffness matrix is singular or not positive definite.
```

错误信息应尽量给出：

```text
story ID
minimum eigenvalue
```

便于用户定位配置问题。

---

# 13. 全局系统有效性检查

StructuralModel 构造完成后，还建议检查：

```text
M positive definite
K positive definite
```

对于当前固定基础的线性建筑模型，理论上不应存在刚体模态。

若出现非正或接近零特征值，应在进入：

```text
Rayleigh damping
Newmark
```

之前报错。

---

# 14. Rayleigh 重频问题

## 14.1 当前问题

目前已经检查：

```text
mode_a != mode_b
```

但不同模态编号可能具有：

\[
\omega_i \approx \omega_j
\]

特别是 X/Y 对称结构中，这是一种正常且常见的情况。

此时 Rayleigh 方程：

\[
\xi_i=\frac{\alpha}{2\omega_i}
+\frac{\beta\omega_i}{2}
\]

使用两个几乎相同频率求：

```text
alpha
beta
```

会导致线性方程奇异或严重病态。

---

# 15. Rayleigh 优化目标

计算系数前增加：

```text
frequency separation check
```

例如：

```python
if np.isclose(w1, w2, rtol=..., atol=...):
    raise ValueError(...)
```

错误应清楚说明：

```text
Selected Rayleigh reference modes have identical
or nearly identical natural frequencies.
Choose two modes with distinct frequencies.
```

对于：

```text
zeta == 0
```

可以直接：

```text
alpha = 0
beta = 0
```

避免无意义求解。

---

# 16. DirectBackend 进一步统一

## 16.1 当前问题

虽然已经建立：

```text
DirectBackend
```

但内部仍分发到：

```text
direct_shear.py
direct_stiffness.py
```

两者仍分别执行完整分析流程。

与此同时：

```text
ShearBuildingModel
RigidFloorBuildingModel
```

已经都能提供：

```text
mass_matrix()
stiffness_matrix()
influence_matrix()
linear_system()
```

说明 DirectBackend 已经具备进一步统一的基础。

---

# 17. DirectBackend 最终目标

希望逐渐形成：

```text
ModelConfig
    ↓
StructuralModel
    ↓
M / K / Γ
    ↓
Damping
    ↓
LinearSystem
    ↓
NewmarkSolver
    ↓
Response reshape
    ↓
AnalysisResult
```

其中通用步骤：

```text
M/K
Rayleigh damping
LinearSystem
Newmark
Modal
```

只实现一次。

不同模型只负责：

```text
结构矩阵
影响矩阵
DOF layout
response reshape
sensor mapping
```

---

# 18. 不要求强行统一 OpenSees Builder

OpenSees 与 DirectBackend 的性质不同。

不同结构模型对应：

```text
不同 node
不同 element
不同 constraint
```

因此 OpenSees 可以继续保持：

```text
opensees/
    shear_building.py
    rigid_floor.py
```

类似的模型专用 builder。

Stage 1.5 不要求把所有 OpenSees 模型构造强行合并成一个文件。

需要统一的是：

```text
输入
输出
公共分析约定
AnalysisResult
```

而不是内部 OpenSees 建模细节。

---

# 19. 测试体系补强

Stage 1 的测试已经覆盖大量：

```text
schema
mapping
modal
Newmark
dataset
CLI
export
```

Stage 1.5 重点补充：

```text
integration
regression
physical validity
```

---

# 20. OpenSees Integration Tests

建议正式加入 pytest marker：

```python
@pytest.mark.opensees
```

通过：

```bash
pytest -m opensees
```

独立运行。

至少建立以下工况。

---

## Case 1：单层对称结构

验证：

```text
Direct vs OpenSees
```

比较：

```text
displacement
velocity
acceleration
absolute acceleration
```

---

## Case 2：多层对称结构

验证：

```text
楼层矩阵组装
多层 Newmark
OpenSees node response
```

---

## Case 3：偏心结构

验证：

```text
Ux
Uy
Rz
```

耦合。

重点比较：

```text
torsional response
off-center sensor response
```

---

## Case 4：变刚度结构

使用不同楼层：

```text
k_story
```

验证层间组装与 OpenSees element stiffness。

---

## Case 5：非零初始 ground acceleration

验证：

```text
initial acceleration
first analysis step
```

一致。

---

## Case 6：多个测点

验证：

```text
OpenSees sensor node
```

与：

```text
rigid-floor analytical mapping
```

一致。

---

# 21. Golden Regression Tests

## 21.1 当前问题

目前：

```text
run_result()
```

与：

```text
legacy run()
```

之间的比较主要验证 adapter 是否正确。

它无法证明未来重构没有改变原始物理结果。

---

## 21.2 建立固定 reference cases

建议至少保存：

```text
tests/reference/
    shear_3story/
    rigid_symmetric_3story/
    rigid_eccentric_3story/
```

每个工况不必保存完整大时程。

可以保存：

```json
{
    "frequencies": [...],
    "peak_displacement": [...],
    "peak_acceleration": [...],
    "selected_time_samples": [...]
}
```

也可以使用：

```text
npz
```

保存少量矩阵与时程样本。

---

## 21.3 Regression 内容

至少比较：

```text
M
K
C
frequency
mode shape
peak response
selected response samples
sensor response
```

允许合理浮点误差。

---

# 22. 模态退化情况下的测试

对称三维建筑容易产生重复模态。

建议增加：

```text
repeated / near-repeated mode
```

测试，用于验证：

- `modal_analysis()` 能正常返回；
- 模态排序稳定；
- Rayleigh 阻尼能够拒绝不合适的参考模态；
- 不会产生难以理解的 `LinAlgError`。

---

# 23. CLI Validation 改进

当前：

```bash
qrest-model validate
```

使用单一：

```text
--tolerance
```

同时判断：

```text
absolute error
relative L2 error
```

二者物理意义不同。

建议逐步改为：

```text
--abs-tol
--rel-tol
```

例如：

```bash
qrest-model validate case.json \
    --backend-a direct \
    --backend-b opensees \
    --abs-tol 1e-10 \
    --rel-tol 1e-8
```

旧：

```text
--tolerance
```

可暂时兼容。

---

# 24. Ground Motion 本阶段处理范围

Stage 1 已显著增强 ground motion 校验。

目前已经能够处理：

```text
一列 acceleration
两列 time + acceleration
NaN / Inf
时间非递增
dt 不一致
duration 超范围
```

Stage 1.5 不强制完成整个 excitation schema 重设计。

暂时保留：

```text
ground_motion
ax_file
ay_file
```

避免扩大本阶段范围。

---

# 25. Excitation Schema 留给下一阶段

未来模型扩展前再正式设计：

```text
ExcitationConfig
UniformGroundMotion
GroundMotionComponent
```

例如：

```text
component
unit
dt
file
scale
```

以便后续支持：

```text
vertical input
multi-support input
different source formats
provided velocity/displacement
```

Stage 1.5 只需保证现有 ground motion API 内部行为稳定。

---

# 26. 建筑高度暂不在 Stage 1.5 强制修改

当前 metadata 默认使用固定：

```text
story_height
```

这一点从长期设计看仍应进入结构模型：

```text
geometry
elevations
story_heights
```

但当前：

```text
shear_building
rigid_floor_shear
```

动力矩阵并不依赖实际高度。

因此为控制本轮范围：

> Stage 1.5 暂不强制修改建筑高度 schema。

但应列为进入：

```text
shear-flexure
bending
Timoshenko
```

模型之前的必做项。

---

# 27. Schema 文件暂不进行纯形式拆分

当前：

```text
schema/
    case.py
    model.py
    excitation.py
    sensor.py
    damping.py
```

已经建立接口层次，但主要实现仍集中在 `case.py`。

Stage 1.5 不以“拆文件”为目标。

仅当真正增加第三种：

```text
ModelConfig
```

时，再将：

```text
rigid floor
shear building
excitation
sensor
```

分别拆成独立实现。

避免为了目录形式进行无实际收益的重构。

---

# 28. 推荐实施顺序

## Step 1

统一 shear response：

```text
relative
absolute
ground
sensor absolute/relative
```

---

## Step 2

修改 exporter，使其不再自行重构绝对响应。

---

## Step 3

将 dataset/exporter 全部切换至：

```text
AnalysisResult
```

---

## Step 4

迁移：

```text
map_sensors
make_metadata
make_algorithm_configs
```

核心逻辑进入 `qrest_model`。

清除：

```text
qrest_model → scripts
```

依赖。

---

## Step 5

将：

```text
modal_analysis
```

结果正式加入：

```text
AnalysisResult.modal
```

并删除 exporter 中重复计算。

---

## Step 6

增加：

```text
story stiffness positive-definite check
global system validation
Rayleigh repeated-frequency validation
```

---

## Step 7

进一步统一：

```text
DirectBackend
```

使其直接消费：

```text
StructuralModel
LinearSystem
```

减少 `direct_xxx` 完整流程重复。

---

## Step 8

增加 OpenSees integration tests。

---

## Step 9

建立 golden regression cases。

---

## Step 10

最后清理旧兼容层。

原则：

```text
先迁移
再测试
最后删除
```

---

# 29. 本阶段明确不做

Stage 1.5 不增加：

- shear-flexure 模型；
- Euler 梁；
- Rayleigh 梁；
- Timoshenko 梁；
- 隔震层；
- 非线性层弹簧；
- 滞回材料；
- 竖向自由度；
- rocking；
- 多点地震输入；
- SSI；
- 大变形；
- 非线性动力分析。

这些内容统一放在下一阶段。

---

# 30. Stage 1.5 验收标准

完成后应满足以下条件。

## 30.1 Result

所有 Backend 均统一返回：

```text
AnalysisResult
```

并具有统一：

```text
relative
absolute
ground
sensor
modal
```

语义。

---

## 30.2 Legacy

```text
dict
```

只允许存在于：

```text
compatibility wrapper
legacy CLI/output
```

不能再作为内部核心接口。

---

## 30.3 Dependency

禁止：

```text
qrest_model
    ↓
scripts
```

`scripts/` 可以被删除而不影响：

```text
import qrest_model
```

核心 API 正常工作。

---

## 30.4 Direct Backend

增加新的线性 StructuralModel 时，不应再需要复制：

```text
Newmark
Rayleigh
modal
AnalysisResult construction
```

完整流程。

---

## 30.5 Physical validity

非法结构：

```text
zero torsional stiffness
singular stiffness
non-positive mass
```

应在分析早期给出清晰错误。

Rayleigh 参考模态频率重复时应给出明确错误，而不是底层矩阵求解异常。

---

## 30.6 Testing

至少具备：

```text
unit tests
physical tests
OpenSees integration tests
golden regression tests
```

四层验证。

---

# 31. Stage 1.5 完成后的目标架构

最终希望达到：

```text
                Config
                  │
                  ▼
                Schema
                  │
                  ▼
           StructuralModel
                  │
          ┌───────┴────────┐
          ▼                ▼
      DirectBackend    OpenSeesBackend
          │                │
          └───────┬────────┘
                  ▼
            AnalysisResult
                  │
       ┌──────────┼────────────┐
       ▼          ▼            ▼
 Postprocess   Dataset      Exporters
                              │
                              ▼
                         qREST Data
```

并保持严格依赖方向：

```text
CLI / scripts
     ↓
qrest_model
```

---

# 32. 下一阶段进入条件

只有当以下问题基本解决后，再开始增加第三种结构模型：

```text
统一 AnalysisResult
统一 DirectBackend
无 library → scripts 反向依赖
结构稳定性检查
Rayleigh 重频保护
OpenSees integration tests
golden regression
```

此时可以选取一种与现有层剪切模型物理机制明显不同、但仍属于线性简化模型的模型作为架构验证。

优先候选：

> **shear-flexure / 弯剪建筑模型**

该模型应尽量只新增：

```text
ModelConfig
StructuralModel
必要的 OpenSees Builder
```

并直接复用：

```text
Excitation
Damping
Modal
Newmark
AnalysisResult
Sensor
Exporter
Dataset
CLI
```

如果能够做到这一点，则说明 Stage 1 与 Stage 1.5 的架构重构真正达到了预期目标。