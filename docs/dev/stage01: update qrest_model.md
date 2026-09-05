# qREST 可控结构动力模型重构开发计划

## 1. 项目定位

当前项目用于通过简化结构动力模型生成具有明确物理含义、可重复、可控制的结构响应和虚拟监测数据，为 qREST 中的算法开发、单元测试、回归测试和异常分析提供可靠的数据源。

项目的核心定位应统一为：

> **可控结构动力模型与虚拟监测数据生成框架。**

JSON/YAML 配置描述的是：

- 结构模型；
- 结构参数；
- 激励；
- 阻尼；
- 测点；
- 分析工况。

而不是直接描述 OpenSees 命令。

OpenSeesPy 只是结构分析的一种 backend。当前直接刚度矩阵方法则作为另一种 backend，同时承担理论验证和回归测试基准的作用。

本轮开发暂不增加新的结构模型能力，主要完成以下两方面工作：

1. 提高现有模型与数据生成流程的可靠性；
2. 对内部架构进行收敛，为后续模型扩展建立稳定基础。

---

# 2. 本轮开发目标

本轮改造完成后，希望形成以下结构：

```text
Model Configuration
        │
        ▼
Normalized Model Description
        │
        ├───────────────┐
        ▼               ▼
 Direct Backend    OpenSees Backend
        │               │
        └───────┬───────┘
                ▼
        AnalysisResult
                │
        ┌───────┴────────┐
        ▼                ▼
 Sensor Mapping      Exporters
                         │
                qREST Test Dataset
```

核心原则：

1. **模型与求解器分离**
2. **模型与 backend 分离**
3. **计算结果与文件输出分离**
4. **结构配置与 qREST 数据格式分离**
5. **不同简化模型尽量共享分析基础设施**
6. **OpenSees 和直接法应针对相同物理模型进行计算**
7. **现有计算结果在重构阶段原则上保持不变**

---

# 3. 第一阶段：可靠性与配置规范化

第一阶段不进行大规模架构修改，优先修复当前代码中可能造成错误或歧义的问题。

## 3.1 引入配置版本

在顶层配置增加：

```json
{
    "schema_version": "2.0"
}
```

目的：

- 支持未来配置升级；
- 避免旧配置与新程序之间产生隐式行为变化；
- 为配置迁移工具保留可能性。

第一版只需要支持：

```text
2.0
```

旧配置可暂时兼容，并给出明确 warning。

---

## 3.2 明确模型类型

不再通过 `dof_per_floor` 推断模型类型。

配置增加：

```json
"model": {
    "type": "rigid_floor_shear_3d"
}
```

当前支持：

```text
shear_building_1d
rigid_floor_shear_3d
```

`dof_per_floor` 可以继续保留，但应作为模型属性：

```json
"dof_per_floor": ["Ux", "Uy", "Rz"]
```

而不是模型识别依据。

---

## 3.3 加强配置校验

统一检查以下内容。

### 楼层

- `num_stories > 0`
- story 编号唯一
- story 编号位于有效范围
- 质量必须大于 0
- 转动惯量必须大于 0
- 刚度必须大于 0

### 测点

- sensor ID 必须唯一
- story 必须存在
- direction 必须合法
- quantity 必须合法
- 坐标必须可以转换为数值

### Rayleigh 阻尼

要求：

```json
"modes": [1, 3]
```

必须满足：

- 恰好两个模态；
- 模态编号均大于等于 1；
- 两个模态编号不能相同；
- 模态编号不能超过模型有效模态数；
- `zeta >= 0`

禁止静默截断：

```python
modes[:2]
```

应改为严格校验。

---

# 4. OpenSees 构件连接校验

当前 OpenSees 层模型依赖相邻楼层中相同下标的 element 相互连接。

本轮需要提高这一逻辑的可靠性。

## 4.1 为构件增加可选 ID

推荐配置：

```json
{
    "id": "corner_sw",
    "x": -5.0,
    "y": -3.0,
    "kx": 2.0e8,
    "ky": 2.0e8
}
```

OpenSees 建模时优先按照：

```text
element.id
```

建立楼层之间的对应关系，而不是依赖数组位置。

## 4.2 构件连续性检查

相邻楼层同一构件必须满足：

```text
ID 一致
```

对于当前 zeroLength 建模方式，还应检查：

```text
x_upper ≈ x_lower
y_upper ≈ y_lower
```

允许设置较小的浮点容差。

若构件坐标发生变化，应明确报错，而不是继续生成 zeroLength element。

这一限制应在模型文档中明确：

> 当前 `rigid_floor_shear_3d` OpenSees backend 假定层间抗侧构件沿高度保持相同平面位置。

未来若需要处理倾斜或位置变化构件，应由新的模型实现解决。

---

# 5. 坐标系统统一

当前模型允许：

```text
geometry_center
mass_center
```

作为参考坐标。

内部统一原则保持：

> 所有结构动力计算最终使用楼层质心坐标系。

因此：

```text
x_internal = x_input - x_mass_center
y_internal = y_input - y_mass_center
```

当配置本身已经使用 mass center 时，则不再转换。

## 5.1 修复逐层质心问题

测点重新映射时不能只读取：

```text
floor_defaults.mass_center
```

必须读取对应楼层最终归一化后的：

```text
story.mass_center
```

应确保：

```text
直接计算产生的 sensor response
```

和

```text
master response → sensor remapping
```

严格使用同一套坐标转换。

增加对应回归测试。

---

# 6. 地震动输入规范化

当前 ground motion 配置需要进一步明确数据含义。

建议配置逐渐调整为：

```json
"excitation": {
    "type": "uniform_ground_motion",
    "components": {
        "x": {
            "file": "gm_x.txt",
            "unit": "m/s2",
            "dt": 0.02,
            "scale": 1.0
        },
        "y": {
            "file": "gm_y.txt",
            "unit": "m/s2",
            "dt": 0.02,
            "scale": 1.0
        }
    }
}
```

## 6.1 输入校验

至少检查：

- `dt > 0`
- 时间列严格递增
- 数据不能为空
- 不允许 NaN / Inf
- 文件格式是否合法
- duration 与实际输入范围是否一致
- 用户配置采样间隔与文件时间列是否存在明显冲突

## 6.2 单位

内部建议统一使用：

```text
m
s
m/s
m/s²
rad
rad/s
rad/s²
```

外部输入允许其他单位时，在输入层完成统一转换。

---

# 7. 地面速度和位移处理

当前可通过地面加速度积分获得：

```text
ground velocity
ground displacement
```

此机制可以保留，但需要明确其物理含义。

推荐内部增加来源标记：

```text
ground_velocity_source:
    provided
    integrated

ground_displacement_source:
    provided
    integrated
```

如果由加速度直接积分得到，则 metadata 中明确记录：

```text
derived_from_acceleration
```

未来可进一步支持：

```text
baseline correction
high-pass correction
provided ground velocity
provided ground displacement
```

本轮暂不需要实现复杂基线修正，只要求避免将未经处理的积分结果视为无条件可靠的真实位移。

---

# 8. 第二阶段：统一核心数据结构

可靠性修复完成后，开始内部架构收敛。

---

# 9. 统一配置模型

当前：

```text
config.py
shear_config.py
```

存在较多重复。

重构后应逐步形成：

```text
qrest_model/schema/
    case.py
    model.py
    sensor.py
    excitation.py
    damping.py
```

例如：

```python
ModelCase
├── model
├── excitation
├── damping
├── sensors
└── analysis
```

其中：

```python
ModelConfig
```

允许根据：

```text
model.type
```

解析为不同具体模型配置。

例如：

```python
ShearBuildingConfig
RigidFloorBuildingConfig
```

公共字段只定义一次。

---

# 10. 建立模型层

建议增加：

```text
qrest_model/models/
```

当前至少实现：

```text
shear_building.py
rigid_floor.py
```

模型类负责表达结构物理性质，而不是执行具体求解。

例如：

```python
class StructuralModel:
    ...
```

具体模型可以提供：

```python
build_linear_system()
```

或等价接口。

对于 direct backend，可以得到：

```text
M
K
Γ
DOF labels
```

而 OpenSees backend 则读取同一个模型对象建立节点和单元。

---

# 11. 建立统一线性系统表示

对于当前两种简化结构，最终均可以写成：

\[
M\ddot{u}+C\dot{u}+Ku=P(t)
\]

因此增加类似：

```python
@dataclass
class LinearSystem:
    mass: np.ndarray
    damping: np.ndarray
    stiffness: np.ndarray
    influence: np.ndarray
```

模型负责提供：

```text
M
K
Γ
```

阻尼模块根据配置生成：

```text
C
```

direct solver 不再关心：

```text
shear1d
story3d
```

它只处理：

```text
LinearSystem
```

---

# 12. 抽离统一 Newmark 求解器

当前不同 direct backend 中存在重复 Newmark 实现。

统一迁移到：

```text
qrest_model/analysis/newmark.py
```

接口建议类似：

```python
solver = NewmarkSolver(
    beta=0.25,
    gamma=0.5
)

response = solver.solve(
    system,
    excitation
)
```

要求：

- 仅实现线性 Newmark；
- 保持当前平均加速度法默认参数；
- 对时间步长进行一致性检查；
- 明确初始位移、速度和加速度；
- 为未来其他积分方法保留接口。

---

# 13. Newmark 数值优化

由于线性模型中：

```text
K_eff
```

在整个分析过程中保持不变，应避免每一步重新执行完整矩阵分解。

推荐：

```python
scipy.linalg.lu_factor
scipy.linalg.lu_solve
```

如果确认矩阵满足条件，也可以使用 Cholesky。

要求：

- 不改变已有数值结果；
- 新旧实现通过回归测试比较；
- 浮点误差保持合理范围。

---

# 14. 统一模态分析

目前模态性质计算应集中到：

```text
qrest_model/analysis/modal.py
```

建议对于：

```text
K φ = λ M φ
```

使用：

```python
scipy.linalg.eigh(K, M)
```

代替一般形式：

```python
eig(inv(M) @ K)
```

输出统一包含：

```python
ModalResult
├── eigenvalues
├── omega
├── frequency
├── period
└── mode_shapes
```

默认支持：

```text
mass-normalized
```

即：

\[
\phi_i^T M \phi_i = 1
\]

同时统一模态符号方向，保证回归测试稳定。

---

# 15. 统一分析结果 AnalysisResult

逐步取消 backend 返回任意：

```python
dict[str, Any]
```

定义正式结果类型，例如：

```python
@dataclass
class ResponseHistory:
    displacement: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray


@dataclass
class AnalysisResult:
    time: np.ndarray

    relative: ResponseHistory
    absolute: ResponseHistory

    mass_matrix: np.ndarray
    stiffness_matrix: np.ndarray
    damping_matrix: np.ndarray

    modal: ModalResult | None

    sensors: SensorResult | None

    metadata: AnalysisMetadata
```

目标：

- direct 和 OpenSees 返回完全一致的外部结果结构；
- exporter 不再判断不同 backend 的 key；
- 测试代码获得静态类型支持；
- 避免类似：

```text
stiffness_matrix
stiffness_matrix_theory
```

这样的命名差异扩散。

---

# 16. Backend 接口统一

建立统一 backend 抽象：

```python
class AnalysisBackend:
    def run(
        self,
        model,
        excitation,
        analysis_config
    ) -> AnalysisResult:
        ...
```

当前实现：

```text
DirectBackend
OpenSeesBackend
```

外部调用形式统一：

```python
result = backend.run(case)
```

而不是：

```text
run_direct_shear
run_direct_stiffness
run_opensees_shear
run_opensees_story
```

模型类型应由：

```text
case.model.type
```

决定。

backend 只负责选择对应 model adapter。

---

# 17. OpenSees backend 的职责

OpenSees backend 负责：

```text
Model Description
      ↓
OpenSees Nodes
Materials
Elements
Constraints
Excitation
Analysis
      ↓
AnalysisResult
```

OpenSees backend 内部可以针对不同模型提供 builder：

```text
opensees/
    shear_building.py
    rigid_floor.py
```

但外部 backend API 保持统一。

---

# 18. Direct backend 的职责

Direct backend 负责：

```text
StructuralModel
      ↓
LinearSystem
      ↓
NewmarkSolver
      ↓
AnalysisResult
```

其中：

```text
M/K 构造属于 model
阻尼属于 damping
积分属于 solver
```

不要继续将这些内容全部放在：

```text
direct_xxx.py
```

中。

---

# 19. 测点映射独立化

测点映射属于：

```text
结构运动 → 虚拟传感器响应
```

不属于 solver。

建议放入：

```text
qrest_model/postprocess/sensor_mapping.py
```

刚性楼板继续使用：

\[
u_x=U_x-yR_z
\]

\[
u_y=U_y+xR_z
\]

要求：

- direct backend 可以由主自由度后处理得到；
- OpenSees backend 可以直接读取 sensor node；
- 两者结果应通过测试互相验证。

同时保留：

```text
master response → sensor remapping
```

能力，使用户只修改测点布置时不必重新执行结构分析。

---

# 20. 文件输出与分析逻辑分离

当前 backend 中直接负责：

```text
write CSV
write matrix
write metadata
```

应逐步迁移至：

```text
qrest_model/exporters/
```

例如：

```text
exporters/
    raw_csv.py
    structural_properties.py
    qrest_dataset.py
```

backend 只返回：

```text
AnalysisResult
```

不负责决定结果文件如何组织。

---

# 21. 重构测试数据生成器

当前 `generate_test_datasets.py` 中已经包含大量实际库功能。

需要拆分为：

```text
qrest_model/datasets/
    cases.py
    generator.py
    validation.py
```

职责划分：

### cases.py

定义官方测试工况：

```text
single_x
dual_xy
two_x_one_y_torsion
two_x_torsion
staggered_2x_center_y
```

### generator.py

负责：

```text
读取 case
运行模型
保存 master response
测点映射
生成 qREST dataset
```

### validation.py

负责：

```text
direct / OpenSees 对比
sensor node / rigid mapping 对比
matrix comparison
```

原：

```text
scripts/generate_test_datasets.py
```

最终只保留命令行入口。

---

# 22. CLI 统一

本轮后期可以将多个入口统一为：

```bash
qrest-model run case.json --backend direct
```

```bash
qrest-model run case.json --backend opensees
```

```bash
qrest-model validate case.json
```

```bash
qrest-model generate-datasets
```

```bash
qrest-model export-qrest ...
```

暂时不要求必须完成复杂 CLI 框架，优先保证 Python API 清晰。

---

# 23. Python 包规范化

建议增加：

```text
pyproject.toml
```

将项目安装为 editable package：

```bash
pip install -e .
```

取消脚本中大量：

```python
sys.path.insert(...)
```

正式依赖至少包括：

```text
numpy
scipy
```

可选依赖：

```text
openseespy
PyYAML
pytest
```

OpenSees 可以保持 optional dependency。

---

# 24. 测试体系

测试应分成三层。

## 24.1 单元测试

不依赖 OpenSees。

主要测试：

- 配置解析；
- 配置非法值；
- 坐标转换；
- story stiffness；
- global stiffness；
- mass matrix；
- sensor mapping；
- Rayleigh damping；
- Newmark；
- modal analysis；
- qREST metadata；
- exporter。

---

## 24.2 物理性质测试

验证模型满足基本物理规律。

至少包括：

### 对称结构

X 输入时：

```text
Rz ≈ 0
```

### 偏心结构

X 输入时：

```text
Rz ≠ 0
```

### 刚性楼板

验证：

\[
u_x=U_x-yR_z
\]

\[
u_y=U_y+xR_z
\]

### 刚度矩阵

检查：

```text
K = K^T
```

并检查合理模型下：

```text
M > 0
K > 0
```

---

# 25. OpenSees 集成测试

OpenSees 测试单独设置：

```bash
pytest -m opensees
```

至少建立以下案例：

1. 单层对称结构；
2. 多层对称结构；
3. 多层偏心结构；
4. 不均匀楼层刚度；
5. 非零初始 ground acceleration；
6. 多测点刚性楼板映射。

比较：

```text
M
K
Rayleigh coefficients
relative displacement
relative velocity
relative acceleration
absolute acceleration
sensor response
```

direct backend 作为理论参考。

---

# 26. 回归测试

重构前保存若干标准工况的参考结果。

例如：

```text
reference/
    shear_3story/
    story3d_symmetric/
    story3d_eccentric/
```

本轮架构重构原则：

> 对同一配置和算法参数，结构计算结果只能存在浮点数意义上的差异。

需要为：

```text
frequency
mode shape
time history
sensor response
```

设置合理误差容限。

---

# 27. 建议最终目录

本轮结束时可逐渐演化到：

```text
qrest_model/
│
├── schema/
│   ├── case.py
│   ├── model.py
│   ├── excitation.py
│   ├── damping.py
│   └── sensor.py
│
├── models/
│   ├── base.py
│   ├── shear_building.py
│   └── rigid_floor.py
│
├── analysis/
│   ├── system.py
│   ├── result.py
│   ├── newmark.py
│   └── modal.py
│
├── backends/
│   ├── base.py
│   ├── direct.py
│   └── opensees/
│       ├── backend.py
│       ├── shear_building.py
│       └── rigid_floor.py
│
├── postprocess/
│   ├── response.py
│   └── sensor_mapping.py
│
├── exporters/
│   ├── raw_csv.py
│   ├── structural_properties.py
│   └── qrest_dataset.py
│
├── datasets/
│   ├── cases.py
│   ├── generator.py
│   └── validation.py
│
└── cli.py
```

该目录只是目标结构，不要求一次性全部移动。

重构应尽量采用：

```text
新增 → 迁移 → 测试 → 删除旧实现
```

而不是一次性大范围重写。

---

# 28. 推荐开发顺序

## Step 1 — 建立可靠性基线

完成：

```text
schema_version
model.type
sensor ID 检查
damping modes 检查
mass / stiffness 检查
element 对应关系检查
逐层 mass_center 修复
ground motion 校验
```

要求：

```text
现有测试全部通过
```

---

## Step 2 — 建立统一结果类型

增加：

```text
AnalysisResult
ResponseHistory
ModalResult
```

先让现有 backend 通过 adapter 返回统一结果。

暂时不要立即删除旧 dict API。

---

## Step 3 — 抽取公共 Newmark

将：

```text
direct_shear
direct_stiffness
```

中的积分算法迁移到统一 solver。

验证结果一致后删除重复代码。

---

## Step 4 — 抽取统一模态分析

集中：

```text
eigenvalue
frequency
period
mode normalization
```

逻辑。

---

## Step 5 — 建立 StructuralModel

将：

```text
shear1d
story3d
```

结构矩阵生成迁移为模型实现。

---

## Step 6 — 收敛 DirectBackend

形成：

```text
StructuralModel
→ LinearSystem
→ NewmarkSolver
→ AnalysisResult
```

---

## Step 7 — 收敛 OpenSeesBackend

将 OpenSees 入口统一，同时内部保留不同 model builder。

---

## Step 8 — 抽离 exporters

backend 不再直接写文件。

---

## Step 9 — 拆分 dataset generator

将 `generate_test_datasets.py` 中真正的业务代码迁移到包内部。

---

## Step 10 — 清理兼容层

确认：

```text
测试通过
官方数据可重新生成
qREST C++ 测试可正常运行
```

后，再删除旧接口与重复脚本。

---

# 29. 本轮不做的内容

为了防止本次重构范围无限扩大，本轮原则上不实现：

- 新结构模型；
- 弯曲梁模型；
- Timoshenko 模型；
- 弯剪模型；
- 隔震层；
- 非线性构件；
- 材料滞回；
- 大变形；
- 竖向结构自由度；
- 多点地震输入；
- SSI；
- 高级阻尼模型；
- 自动参数识别。

这些内容统一放入下一阶段：

> **能力扩展阶段**

本轮只要求架构能够合理容纳这些能力。

---

# 30. 第三阶段的接口预留

完成本轮重构后，增加新模型时应尽量只需要：

```text
1. 定义新的 ModelConfig
2. 定义新的 StructuralModel
3. 若支持 direct：
      提供 M/K/Γ
4. 若支持 OpenSees：
      提供 OpenSees model builder
```

而不需要重新实现：

```text
ground motion
Rayleigh damping
Newmark
modal analysis
sensor data container
result output
qREST exporter
dataset generator
```

如果未来增加：

```text
shear_flexure
Timoshenko
base_isolated
```

仍然能够复用绝大部分框架，则说明本轮重构目标已经达到。

---

# 31. 本轮验收标准

完成本轮开发后应满足：

### 配置

- 存在明确 schema version；
- 存在明确 model type；
- 非法配置能够尽早给出清晰错误；
- 不存在依赖数组顺序的隐式重要关系。

### 数值

- direct 新旧结果一致；
- OpenSees 与 direct 在验证模型中一致；
- 模态结果稳定；
- 相对/绝对响应定义明确。

### 架构

- Newmark 只存在一个核心实现；
- 模态分析只存在一个核心实现；
- backend 输出统一 `AnalysisResult`；
- model 和 backend 不再是一一绑定关系；
- exporter 不依赖 backend 内部细节。

### 测试

- 单元测试通过；
- 物理性质测试通过；
- OpenSees integration tests 可独立执行；
- 官方测试数据能够重新生成；
- qREST 现有算法测试仍可读取生成数据。

### 可扩展性

增加一个新的线性简化模型时，不需要复制完整的：

```text
config
solver
modal
IO
dataset
```

体系。

---

# 32. 后续能力扩展方向

本轮重构完成后，再进入下一阶段。

优先讨论：

1. 现有 `shear_building_1d` 与 `rigid_floor_shear_3d` 的模型能力边界；
2. 是否增加弯曲、剪切、弯剪类连续模型；
3. 是否增加 Timoshenko / shear-flexure 简化模型；
4. 如何描述局部刚度突变；
5. 如何描述隔震层；
6. 如何引入非线性层弹簧；
7. 是否支持二维/三维不同层模型组合；
8. 如何使用这些模型产生针对 OMA、MBI、EDP、RR 等算法的专用测试工况。

这些内容不应直接堆叠在当前实现之上，而应建立在本轮统一后的 Model / Backend / AnalysisResult 架构之上。