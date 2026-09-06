# qREST Model Stage 2 离散线性结构模型族扩展开发计划

## 1. 阶段定位

Stage 1 与 Stage 1.5 已基本完成 qREST Model 的基础架构重构和可靠性收口。

目前项目已经形成较稳定的主流程：

```text
Config
  ↓
Schema
  ↓
StructuralModel
  ↓
Backend
  ↓
AnalysisResult
  ↓
Postprocess / Exporter / Dataset
```

现有模型主要包括：

```text
shear_building_1d
rigid_floor_shear_3d
```

虽然两者自由度数量和空间形式不同，但其本质都属于：

> **离散层剪切型结构模型**

因此当前 qREST Model 在软件架构上已经具有较好的可扩展性，但结构物理模型仍较单一。

Stage 2 的主要目标是：

> **在保持现有统一分析框架的基础上，建立一组具有不同变形机制的二维离散线性结构模型。**

本阶段不再以基础架构重构为主要任务，而是开始验证：

> 当前架构能否真正承载不同结构动力学理论。

---

# 2. Stage 1.5 遗留问题

Stage 1.5 已基本达到原定目标，但仍有少量问题建议在 Stage 2 开始前或早期处理。

这些问题不属于新的结构功能，而属于已有框架的轻量清理。

---

## 2.1 Repository cleanup

当前开发环境可能产生：

```text
qrest_model.egg-info/
```

等 setuptools 构建文件。

这些文件不应进入版本控制。

建议：

```gitignore
*.egg-info/
build/
dist/
```

同时不应忽略：

```text
.github/
```

因为后续计划增加 GitHub Actions 测试。

---

## 2.2 Backend comparison 相对误差

当前 backend comparison 的 relative L2 使用类似：

```python
denom = max(norm(a), norm(b), 1.0)
```

这种形式在结构响应小于 1 时会低估相对误差。

建议调整为：

```python
eps = small_scale
denom = max(norm(a), norm(b), eps)
```

或采用对称形式：

\[
e_r=
\frac{2\|a-b\|}
{\|a\|+\|b\|+\varepsilon}
\]

本阶段统一：

```text
absolute error
relative error
```

的定义，为后续多模型 OpenSees comparison 使用。

---

## 2.3 OpenSees integration test 确认

OpenSees tests 当前为独立 marker。

应确认：

```bash
QREST_RUN_OPENSEES_TESTS=1 pytest -m opensees
```

能够完整通过。

后续建议加入 CI：

```text
unit tests
integration tests
```

两套流程。

---

## 2.4 Golden regression 补充

现阶段已有：

```text
shear_3story
rigid_symmetric_3story
```

建议补充：

```text
rigid_eccentric_3story
```

锁定：

```text
translation-torsion coupling
off-center sensor response
```

---

## 2.5 Legacy direct solver 清理

当前：

```text
direct_shear.py
direct_stiffness.py
```

仍保留旧 `solve_newmark()` 兼容入口。

正常主流程已经统一使用：

```text
run_linear_direct()
```

因此本阶段可以：

```text
标记 deprecated
```

或确认无外部依赖后删除。

---

## 2.6 StructuralModel 职责进一步明确

当前 StructuralModel 中部分模型仍存在：

```python
linear_system(damping)
```

但新的 DirectBackend 实际主要使用：

```text
mass_matrix()
stiffness_matrix()
influence_matrix()
```

建议以后明确：

> StructuralModel 只负责结构物理，不负责 damping 和 analysis configuration。

即：

```text
StructuralModel
    ├── M
    ├── K
    ├── Γ
    └── DOF layout
```

而：

```text
Backend
```

负责构造：

```text
LinearSystem
```

---

# 3. Stage 2 总体目标

Stage 2 建立一个二维离散线性模型族：

```text
shear_building_1d          [u]

euler_beam_2d              [u, θ]

rayleigh_beam_2d           [u, θ]

timoshenko_beam_2d         [u, θ]

shear_flexure_building_2d  [u, θ]
```

其中现有：

```text
shear_building_1d
```

作为基准模型。

新增四类模型：

1. Euler–Bernoulli 离散弯曲模型；
2. Rayleigh 离散梁模型；
3. Timoshenko 离散梁模型；
4. Building shear-flexure 离散弯剪模型。

---

# 4. 本阶段核心原则

Stage 2 必须继续遵循以下设计原则。

---

## 4.1 离散模型优先

不直接实现连续悬臂梁求解器。

连续梁理论主要用于：

```text
理论参考
参数解释
模态极限关系
验证
```

实际 qREST Model 使用：

```text
floor/node discrete model
```

---

## 4.2 所有模型最终必须提供统一 M / K / Γ

所有 Direct model 最终统一转换为：

\[
M
\]

\[
K
\]

\[
\Gamma
\]

并复用现有：

```text
Modal
Rayleigh damping
LinearSystem
Newmark
AnalysisResult
```

---

## 4.3 不复制分析算法

新增模型不得重新实现：

```text
Newmark
modal analysis
Rayleigh damping
ground motion loading
AnalysisResult
```

新增模型原则上只新增：

```text
ModelConfig
StructuralModel
element theory
response reshape
OpenSees builder
```

---

## 4.4 Direct 与 OpenSees 保持独立实现

Direct backend：

```text
theoretical element matrix
→ assembled M/K
```

OpenSees backend：

```text
node
element
mass
constraint
```

两者不能共用最终 K 后再声称完成验证。

OpenSees 应作为真正独立的物理实现。

---

# 5. 首先引入 Geometry

## 5.1 当前问题

现有 shear model 中：

```text
story = 1, 2, 3 ...
```

已经足以组装结构矩阵。

但：

```text
Euler
Rayleigh
Timoshenko
shear-flexure
```

都需要真实楼层高度：

\[
L_i
\]

因此 Stage 2 首先建立正式 geometry schema。

---

# 6. GeometryConfig

推荐支持：

```json
{
  "geometry": {
    "story_heights": [
      4.5,
      3.6,
      3.6,
      3.6
    ]
  }
}
```

内部统一转换为：

```text
story heights

h1, h2, ..., hN
```

以及：

```text
floor elevations

z0 = 0
z1
z2
...
zN
```

满足：

\[
z_i=\sum_{j=1}^{i}h_j
\]

---

## 6.1 可选 elevations 输入

未来可以允许：

```json
{
  "geometry": {
    "elevations": [
      4.5,
      8.1,
      11.7,
      15.3
    ]
  }
}
```

但内部必须统一为同一种表示。

---

## 6.2 Geometry ownership

Geometry 属于：

```text
StructuralModel
```

不应继续由：

```text
metadata exporter
```

假设。

因此 qREST metadata 中的 elevation 应最终直接读取模型 geometry。

---

# 7. 新二维模型的统一自由度

对于 Euler / Rayleigh / Timoshenko / shear-flexure：

每个楼层节点使用：

\[
q_i=
\begin{bmatrix}
u_i\\
\theta_i
\end{bmatrix}
\]

其中：

```text
u
    水平侧向位移

θ
    沿高度弯曲产生的截面转角
```

整体：

\[
q=
[u_1,\theta_1,u_2,\theta_2,\ldots,u_N,\theta_N]^T
\]

---

# 8. θ 与现有 Rz 必须严格区分

当前：

```text
rigid_floor_shear_3d
```

中的：

\[
R_z
\]

表示：

> 楼板绕竖直方向的平面扭转。

而新二维模型的：

\[
\theta
\]

表示：

> 建筑沿高度弯曲产生的截面转角。

两者物理含义不同。

禁止将：

```text
θ
```

直接复用为现有：

```text
Rz
```

未来 3D 模型再正式定义：

```text
Rx
Ry
Rz
```

---

# 9. Euler–Bernoulli 离散模型

## 9.1 Model type

建议：

```text
euler_beam_2d
```

---

## 9.2 单元自由度

\[
q_e=
[u_i,\theta_i,u_j,\theta_j]^T
\]

---

## 9.3 单元刚度

标准 Euler–Bernoulli bending stiffness：

\[
K_e^{EB}
=
\frac{EI}{L^3}
\begin{bmatrix}
12&6L&-12&6L\\
6L&4L^2&-6L&2L^2\\
-12&-6L&12&-6L\\
6L&2L^2&-6L&4L^2
\end{bmatrix}
\]

---

# 10. Euler 质量矩阵

Stage 2 第一版优先使用：

> **consistent beam mass**

经典形式：

\[
M_e^{EB}
=
\frac{\rho AL}{420}
\begin{bmatrix}
156&22L&54&-13L\\
22L&4L^2&13L&-3L^2\\
54&13L&156&-22L\\
-13L&-3L^2&-22L&4L^2
\end{bmatrix}
\]

这样：

```text
M positive definite
```

能够继续兼容现有：

```text
modal_analysis
NewmarkSolver
```

---

# 11. Euler 暂不实现 massless rotational DOF

另一种建筑模型定义可以使用：

```text
floor translational mass
θ mass = 0
```

但这样：

\[
M
\]

会变为奇异矩阵。

要支持这种模型，需要：

```text
massless DOF
static condensation
DAE-like treatment
```

因此：

> Stage 2 第一版暂不实现。

后续可以作为独立分析能力扩展。

---

# 12. Euler OpenSees 实现

OpenSees 使用：

```text
elasticBeamColumn
```

二维模型节点：

```text
Ux
Uy
Rz
```

使用：

```text
Ux → u
Rz → θ
Uy → constrained
```

节点沿：

```text
vertical direction
```

建立。

必须注意坐标方向与局部 bending axis 定义。

---

# 13. Euler 质量对应

OpenSees 应使用：

```text
element mass
consistent mass
```

使 OpenSees 与 Direct 中：

```text
consistent Euler mass
```

尽量一致。

不得一边使用：

```text
Direct consistent mass
```

另一边使用：

```text
OpenSees nodal lumped mass
```

后再直接比较模态结果。

---

# 14. Rayleigh 离散模型

## 14.1 Model type

建议：

```text
rayleigh_beam_2d
```

---

## 14.2 基本关系

Rayleigh beam 的刚度与 Euler 相同：

\[
K^R=K^{EB}
\]

区别在于：

> 增加显式截面转动惯量。

因此：

\[
M^R
=
M^{EB}
+
M^{rot}
\]

---

# 15. Rayleigh rotational inertia

可以按楼层或单元定义：

\[
J_i
\]

第一版可采用：

```text
nodal rotational inertia
```

例如：

\[
M_i^{rot}=
\begin{bmatrix}
0&0\\
0&J_i
\end{bmatrix}
\]

---

## 15.1 退化关系

Rayleigh 必须满足：

\[
J\rightarrow0
\]

时：

\[
Rayleigh
\rightarrow
Euler
\]

这是 Stage 2 必须加入的 physics test。

---

# 16. Rayleigh OpenSees 实现

OpenSees 使用：

```text
elasticBeamColumn
```

并增加：

```text
nodal rotational mass
```

即：

```text
Euler beam
+
rotational inertia
```

OpenSees 不需要独立 Rayleigh beam element。

---

# 17. Timoshenko 离散模型

## 17.1 Model type

建议：

```text
timoshenko_beam_2d
```

---

## 17.2 自由度

仍然：

\[
q_e=
[u_i,\theta_i,u_j,\theta_j]^T
\]

---

## 17.3 刚度参数

Timoshenko 同时考虑：

```text
bending stiffness

EI
```

和：

```text
shear stiffness

GA_s
```

其中：

\[
GA_s=\kappa GA
\]

---

# 18. Timoshenko 刚度矩阵

定义：

\[
\phi=
\frac{12EI}
{GA_sL^2}
\]

则标准形式：

\[
K_e^T=
\frac{EI}
{L^3(1+\phi)}
\begin{bmatrix}
12&6L&-12&6L\\
6L&(4+\phi)L^2&-6L&(2-\phi)L^2\\
-12&-6L&12&-6L\\
6L&(2-\phi)L^2&-6L&(4+\phi)L^2
\end{bmatrix}
\]

---

# 19. Timoshenko → Euler 极限验证

必须满足：

\[
GA_s\rightarrow\infty
\]

因此：

\[
\phi\rightarrow0
\]

从而：

\[
K^T
\rightarrow
K^{EB}
\]

同时应观察：

\[
f_i^T
\rightarrow
f_i^{EB}
\]

和：

\[
\phi_i^T
\rightarrow
\phi_i^{EB}
\]

---

# 20. Timoshenko OpenSees 实现

优先使用：

```text
ElasticTimoshenkoBeam
```

通过：

```text
E
G
A
I
Av
```

定义等效截面。

OpenSees builder 应独立于 Direct 单元刚度实现。

---

# 21. Building Shear-Flexure Model

## 21.1 Model type

建议：

```text
shear_flexure_building_2d
```

---

## 21.2 物理含义

该模型不应简单等同于 Timoshenko。

Timoshenko：

```text
bending deformation
+
shear deformation
```

共同构成同一构件的总变形。

Building shear-flexure：

```text
flexural subsystem
+
shear subsystem
```

代表两套并联的抗侧力机制。

例如：

```text
core wall
+
frame
```

---

# 22. Shear-flexure 单元

统一单元自由度：

\[
q_e=
[u_i,\theta_i,u_j,\theta_j]^T
\]

---

## 22.1 Flexural branch

采用：

\[
K_e^F=K_e^{EB}
\]

---

## 22.2 Shear branch

采用层间水平剪切弹簧：

\[
K_e^S=
k_s
\begin{bmatrix}
1&0&-1&0\\
0&0&0&0\\
-1&0&1&0\\
0&0&0&0
\end{bmatrix}
\]

---

## 22.3 Total stiffness

\[
\boxed{
K_e^{SF}
=
K_e^F
+
K_e^S
}
\]

即：

```text
flexural stiffness
+
shear stiffness
```

并联。

---

# 23. Shear-flexure 参数

建议每层可以定义：

```json
{
  "story": 1,

  "flexural_section": {
    "E": 3.0e10,
    "A": 20.0,
    "I": 100.0
  },

  "shear_stiffness": 5.0e8
}
```

其中：

```text
flexural_section
```

代表：

```text
wall/core-like subsystem
```

而：

```text
shear_stiffness
```

代表：

```text
frame/shear-like subsystem
```

---

# 24. Shear-flexure OpenSees 实现

建议采用：

```text
elasticBeamColumn
+
twoNodeLink
```

并联。

即：

```text
node i
 | \
 |  \
 |   twoNodeLink
 |
elasticBeamColumn
 |
node j
```

其中：

```text
elasticBeamColumn
```

负责弯曲机制。

```text
twoNodeLink
```

负责层间水平剪切机制。

---

# 25. 暂不使用复杂 flexure-shear interaction element

OpenSees 中存在面向：

```text
distributed plasticity
wall flexure-shear interaction
```

的专用 element。

Stage 2 不使用此类复杂 element。

原因：

```text
参数复杂
物理机制不透明
验证困难
偏离线性 ground-truth model 定位
```

Stage 2 保持：

```text
simple
linear
transparent
controllable
```

---

# 26. 统一 Section 参数设计

对于：

```text
Euler
Rayleigh
Timoshenko
```

推荐配置使用等效截面参数，而不是只输入：

```text
EI
GA
```

例如：

```json
{
  "section": {
    "E": 3.0e10,
    "G": 1.25e10,
    "A": 25.0,
    "I": 120.0,
    "shear_area": 20.0
  }
}
```

Direct backend 内部计算：

\[
EI=E I
\]

\[
GA_s=G A_v
\]

OpenSees backend 可直接使用：

```text
E
G
A
I
Av
```

---

# 27. 等效参数而非真实截面

这里的：

```text
E
G
A
I
```

不必严格对应某一根真实构件。

它们可以表示：

> 整栋建筑或某一高度区段的等效连续抗侧力截面。

但参数应保持清晰的物理意义。

---

# 28. 质量模型独立于刚度模型

Stage 2 建议从架构上区分：

```text
stiffness model
```

与：

```text
mass model
```

不要默认：

```text
Timoshenko
```

自动等于某一个唯一质量矩阵。

---

# 29. 推荐 MassModel

第一阶段可支持：

```text
consistent_beam
```

和：

```text
consistent_beam_with_rotary_inertia
```

以后再增加：

```text
lumped_floor
```

---

# 30. Euler / Rayleigh 的区别必须来自质量

Euler：

```text
consistent translational beam mass
```

Rayleigh：

```text
Euler mass
+
explicit rotary inertia
```

这样两者理论关系最清楚。

---

# 31. Timoshenko 质量

Timoshenko 第一版可采用：

```text
consistent translational beam mass
+
rotary inertia
```

具体矩阵形式应在 theory module 中明确实现并测试。

不要直接依赖 OpenSees 结果作为理论定义。

---

# 32. Influence matrix

对于统一水平地面输入：

\[
M\ddot q+C\dot q+Kq
=
-M\Gamma a_g
\]

新模型中：

```text
u DOF
```

受到 ground translation。

```text
θ DOF
```

不直接叠加地面平动。

因此：

\[
\Gamma=
[1,0,1,0,\ldots]^T
\]

---

# 33. Absolute response

统一保持：

```text
u_absolute = u_relative + u_ground
```

而：

```text
θ_absolute = θ_relative
```

同样：

```text
theta velocity
theta acceleration
```

不叠加地面平动。

---

# 34. Sensor mapping

Stage 2 第一版建议优先支持：

```text
horizontal translational sensor
```

即观测：

\[
u_i
\]

及其速度和加速度。

---

## 34.1 θ 暂不直接定义为普通 physical sensor

因为：

```text
θ
```

是结构 generalized DOF。

后续如需要输出：

```text
rotational channel
```

应单独定义：

```text
derived / generalized sensor
```

而不要混入普通 accelerometer。

---

# 35. 新增理论层模块

推荐新增：

```text
qrest_model/theory/
    euler_beam.py
    rayleigh_beam.py
    timoshenko_beam.py
    shear_flexure.py
```

每个模块至少包含：

```text
element stiffness
element mass
assembly helper
```

---

# 36. 新增模型层

推荐：

```text
qrest_model/models/
    euler_beam.py
    rayleigh_beam.py
    timoshenko_beam.py
    shear_flexure.py
```

每个 model 实现统一接口：

```python
mass_matrix()
stiffness_matrix()
influence_matrix()
```

未来可进一步加入：

```text
dof_layout
geometry
```

---

# 37. Direct backend

新增模型必须继续使用：

```text
run_linear_direct()
```

不得新增：

```text
direct_euler_newmark.py
direct_timoshenko_newmark.py
```

这种重复分析实现。

推荐：

```text
DirectBackend
    ↓
StructuralModel
    ↓
run_linear_direct()
```

---

# 38. OpenSees builder

OpenSees 可以保持 model-specific builder。

建议逐渐形成：

```text
qrest_model/backends/opensees/
    shear.py
    rigid_floor.py
    euler.py
    rayleigh.py
    timoshenko.py
    shear_flexure.py
```

是否在 Stage 2 中立即拆目录可以根据实际代码量决定。

不要仅为了目录形式进行重构。

---

# 39. Stage 2 核心验证体系

每个新模型必须通过：

\[
\boxed{
Theory
\leftrightarrow
Direct
\leftrightarrow
OpenSees
}
\]

三层验证。

---

# 40. 第一层：Element Matrix Tests

直接测试单元理论。

例如：

```text
Euler K symmetry
Euler K rank before boundary condition
Euler M symmetry

Timoshenko K symmetry
Rayleigh M positive definite

shear-flexure:
K = K_f + K_s
```

---

# 41. 第二层：Assembly Tests

建立：

```text
1-story
2-story
3-story
```

小模型。

检查：

```text
global M
global K
boundary condition
DOF ordering
```

---

# 42. 第三层：Modal Tests

比较：

```text
frequency
mode shape
```

并检查：

\[
K\phi
=
\omega^2M\phi
\]

以及：

\[
\phi^TM\phi=1
\]

---

# 43. 第四层：Physics Limit Tests

这是 Stage 2 最重要的新测试类型。

---

## 43.1 Rayleigh → Euler

\[
J\rightarrow0
\]

应有：

```text
M_R → M_E
frequency_R → frequency_E
mode_R → mode_E
```

---

## 43.2 Timoshenko → Euler

\[
GA_s\rightarrow\infty
\]

应有：

```text
K_T → K_E
frequency_T → frequency_E
mode_T → mode_E
```

---

## 43.3 Shear-flexure → flexural

\[
k_s\rightarrow0
\]

应有：

```text
K_SF → K_F
```

---

## 43.4 Shear-flexure shear-dominated trend

逐步提高：

\[
k_s
\]

观察：

```text
frequency
mode shape
deformation mechanism
```

是否表现出合理变化。

---

# 44. 第五层：Direct vs OpenSees

每个模型至少建立：

```text
1-story
3-story
variable property
```

integration cases。

比较：

```text
relative displacement
relative velocity
relative acceleration
absolute response
modal frequencies
```

---

# 45. OpenSees comparison 不仅比较时程

Stage 2 建议同时比较：

```text
modal
dynamic response
```

因为不同：

```text
mass model
element formulation
```

可能导致模态已经不同。

---

# 46. Golden regression

每种新模型至少增加一个：

```text
tests/reference/
```

例如：

```text
euler_3story.json
rayleigh_3story.json
timoshenko_3story.json
shear_flexure_3story.json
```

保存：

```text
frequencies
selected mode-shape values
peak response
selected response samples
```

---

# 47. Model Truth

Stage 2 开始正式引入：

> **Model Truth**

概念。

每个生成的数据集应区分：

```text
truth
```

与：

```text
observation
```

---

# 48. Truth 内容

至少保存：

```text
M
K
C

frequency
mode shapes

full floor/node response

geometry

model parameters
```

---

# 49. Observation 内容

保存：

```text
configured sensor channels
```

即：

```text
limited monitoring data
```

---

# 50. Truth 数据目录建议

可以形成：

```text
dataset/
    config.json

    truth/
        structural_properties/
        full_response/

    observations/
        sensor_response/

    metadata.json
```

Stage 2 不要求一次性重构现有所有 dataset layout。

可以先增加逻辑概念，再逐步迁移目录。

---

# 51. Stage 2 与 OMA / MBI 的结合

新模型不是仅用于展示不同动力学公式。

其重要目的之一是为后续算法研究提供不同类型的真实振型。

---

# 52. Modal ground-truth family

最终可以形成：

```text
shear
Euler
Rayleigh
Timoshenko
shear-flexure
```

五类真实模态。

---

# 53. MBI / mode completion 数据集

后续可以设计：

```text
full floors
↓
select sparse floors
↓
identified / sampled mode shapes
↓
mode completion
↓
compare with truth
```

用于研究：

```text
model mismatch
sensor sparsity
nonuniform stiffness
mode family selection
```

---

# 54. OMA 数据集

可增加：

```text
well-separated modes
close modes
flexure-dominated modes
shear-dominated modes
mixed modes
```

以后还可进一步加入：

```text
noise
sensor loss
```

---

# 55. Stage 2 暂不做 3D beam family

本阶段先完成：

```text
2D one-direction
```

模型族。

不立即实现：

```text
Ux
Uy
Rx
Ry
Rz
```

或完整 6DOF。

原因：

```text
先验证模型理论
先验证 mass model
先验证 OpenSees correspondence
```

之后再扩展空间耦合。

---

# 56. Stage 2 暂不做 nonlinear

本阶段不增加：

```text
plastic hinge
hysteresis
nonlinear material
nonlinear isolation
```

所有新模型仍保持：

```text
linear
```

以继续复用：

```text
LinearSystem
NewmarkSolver
ModalResult
```

---

# 57. Stage 2 暂不做 multi-support excitation

仍使用：

```text
uniform horizontal ground motion
```

Excitation schema 的全面扩展留到后续阶段。

---

# 58. 推荐实施顺序

## Step 0

完成 Stage 1.5 小型 cleanup：

```text
egg-info
.gitignore
relative error
OpenSees tests
```

---

## Step 1

加入：

```text
GeometryConfig
story_heights
elevations
```

并修改 metadata 使用真实 elevations。

---

## Step 2

建立二维 beam-like model 的：

```text
DOF layout
[u, θ]
```

和统一 assembly 工具。

---

## Step 3

实现 Euler theory：

```text
Ke
Me
```

并完成 matrix tests。

---

## Step 4

实现：

```text
EulerStructuralModel
```

接入：

```text
DirectBackend
```

---

## Step 5

实现 Euler OpenSees builder。

完成：

```text
Theory
Direct
OpenSees
```

三重验证。

---

## Step 6

在 Euler 基础上增加 Rayleigh：

```text
rotary inertia
```

---

## Step 7

增加：

```text
Rayleigh → Euler
```

极限测试。

---

## Step 8

实现 Timoshenko：

```text
EI
GA
```

---

## Step 9

实现：

```text
ElasticTimoshenkoBeam
```

OpenSees builder。

---

## Step 10

完成：

```text
Timoshenko → Euler
```

极限验证。

---

## Step 11

实现 shear-flexure：

```text
Euler flexural branch
+
story shear branch
```

---

## Step 12

OpenSees 使用：

```text
elasticBeamColumn
+
twoNodeLink
```

进行独立验证。

---

## Step 13

为所有新模型增加：

```text
golden regression
```

---

## Step 14

建立：

```text
Model Truth
```

数据输出。

---

## Step 15

增加第一批：

```text
OMA / MBI research datasets
```

---

# 59. Stage 2 推荐模型配置体系

最终配置概念建议逐渐形成：

```text
Model
├── type
├── geometry
├── stories / sections
├── mass model
├── damping
├── sensors
└── excitation
```

---

# 60. 示例：Euler

```json
{
  "model": {
    "type": "euler_beam_2d",
    "num_stories": 10
  },

  "geometry": {
    "story_heights": [
      4.5,
      3.6,
      3.6,
      3.6,
      3.6,
      3.6,
      3.6,
      3.6,
      3.6,
      3.6
    ]
  },

  "section_defaults": {
    "E": 3.0e10,
    "A": 25.0,
    "I": 120.0,
    "density": 2500.0
  }
}
```

具体 schema 可在开发时进一步确定。

---

# 61. 示例：Timoshenko

```json
{
  "model": {
    "type": "timoshenko_beam_2d",
    "num_stories": 10
  },

  "section_defaults": {
    "E": 3.0e10,
    "G": 1.25e10,
    "A": 25.0,
    "I": 120.0,
    "shear_area": 20.0
  }
}
```

---

# 62. 示例：Shear-Flexure

```json
{
  "model": {
    "type": "shear_flexure_building_2d",
    "num_stories": 10
  },

  "floor_defaults": {
    "mass": 1.0e6,

    "flexural_section": {
      "E": 3.0e10,
      "A": 20.0,
      "I": 100.0
    },

    "shear_stiffness": 5.0e8
  }
}
```

这些示例仅表达目标概念。

Stage 2 不应为了立即兼容示例而牺牲 schema 清晰度。

---

# 63. Stage 2 验收标准

Stage 2 完成后，应至少满足以下条件。

---

## 63.1 Geometry

结构模型正式拥有：

```text
story heights
elevations
```

Exporter 不再自行假设固定楼层高度。

---

## 63.2 Model family

至少完整支持：

```text
Euler
Rayleigh
Timoshenko
Shear-Flexure
```

四类二维离散线性模型。

---

## 63.3 Unified Direct

所有模型复用：

```text
run_linear_direct()
```

不复制：

```text
Newmark
Rayleigh damping
modal analysis
```

---

## 63.4 OpenSees

每个模型具有合理、独立的 OpenSees representation。

---

## 63.5 Theory validation

每个模型拥有：

```text
element matrix tests
assembly tests
modal tests
```

---

## 63.6 Physics validation

至少验证：

```text
Rayleigh → Euler

Timoshenko → Euler

Shear-Flexure → Flexure
```

理论极限。

---

## 63.7 Integration validation

所有模型：

```text
Direct ≈ OpenSees
```

在合理数值容差下成立。

---

## 63.8 Regression

每种模型至少存在一个：

```text
golden reference
```

---

## 63.9 Research output

能够明确输出：

```text
true modes
full response
sensor response
```

用于：

```text
OMA
MBI
mode completion
response reconstruction
```

算法研究。

---

# 64. Stage 2 完成后的模型体系

预期形成：

```text
                 Linear Structural Models

                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
     Shear             Flexure          Mixed
        │                 │                 │
        │         ┌───────┴───────┐     ┌───┴──────────┐
        │         │               │     │              │
        ▼         ▼               ▼     ▼              ▼
 shear_1d      Euler          Rayleigh Timoshenko  Shear-Flexure
```

---

# 65. Stage 2 完成后的价值

此时 qREST Model 不再只是：

> 一个剪切建筑响应生成工具。

而会成为：

> **具有多种可控结构变形机制、能够提供完整结构真值并可通过 OpenSees 交叉验证的线性结构动力学试验平台。**

它可以同时支持：

```text
结构动力模型研究
模态识别算法验证
振型补全
MBI
响应重构
测点布置研究
模型误差研究
```

---

# 66. 后续阶段

Stage 2 完成后，再考虑：

```text
3D bending / shear-flexure
vertical DOF
rocking
base isolation
multi-support excitation
massless DOF
static condensation
nonlinear story models
hysteretic models
```

其中：

```text
massless DOF + static condensation
```

可以作为线性框架进一步扩展。

而：

```text
base isolation + nonlinear
```

则可以作为之后真正进入特殊结构与强震问题的阶段。

---

# 67. 本阶段最重要的成功标准

Stage 2 的成功不应只定义为：

> “增加了四个新 model.type”。

真正的成功标准应是：

> **新增一种结构理论时，只需要增加该模型自身的物理定义，而不需要重新修改或复制整个分析框架。**

即新增模型主要只影响：

```text
Schema
Theory
StructuralModel
OpenSees builder
```

而：

```text
Modal
Damping
Newmark
AnalysisResult
Exporter
Dataset
CLI
```

能够基本保持不变。

如果 Euler、Rayleigh、Timoshenko 和 Shear-Flexure 都能够按照这一方式进入项目，则说明 Stage 1、Stage 1.5 所建立的架构已经真正经受住了模型扩展验证。