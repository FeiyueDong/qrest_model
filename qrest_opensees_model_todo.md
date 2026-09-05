# qREST 建筑监测可控数据生成模型：开发待做文档 v2

## 1. 开发目标

当前 qREST 建筑监测数据处理算法库主要使用实测数据进行测试。实测数据虽然真实，但存在以下问题：

1. 数据来源不可完全控制；
2. 不清楚真实结构、环境、传感器、噪声、边界条件等因素对数据的具体影响；
3. 当算法分析结果异常时，难以判断是算法问题、数据问题，还是结构真实行为复杂导致；
4. 不利于做可重复、可解释、可批量生成的单元测试和回归测试。

因此需要引入一个可控的结构动力模型，用于生成具有明确物理含义的模拟监测数据。该模型的目标不是替代高精度结构有限元分析，而是为算法验证提供可控、可重复、参数可解释的数据源。
第一版重点实现三向楼层模型：

- 结构：地面 + 10 个楼层；
- 楼层自由度：`Ux, Uy, Rz`；
- 楼板假定：刚性楼板；
- 材料与单元：线弹性；
- 坐标参考点：程序内部统一使用每层质心；
- 输出目标：楼层响应、测点响应、可对比的质量/刚度/阻尼信息。

本版保留两个实现后端，用于互相校验：

1. **方法 A：OpenSeesPy 三向层剪切模型**  
   完整使用 OpenSeesPy 建模、约束、加载、动力分析和记录响应；可额外导出刚度矩阵等用于对比。

2. **方法 B：直接刚度矩阵构造模型**  
   使用 NumPy 显式构造 `M/C/K` 并进行线性动力积分，作为方法 A 的理论对照和回归测试基准。

---

## 2. 坐标和偏心约定

用户配置中的平面坐标默认相对于几何中心 `G`，程序内部统一转换到质心 `C`：

```text
x_c = x_g - x_mass_center
 y_c = y_g - y_mass_center
```

每层主自由度定义在质心：

```text
q_i = [Ux_i, Uy_i, Rz_i]^T
```

任意测点或构件点相对于质心坐标为 `(x, y)` 时，其刚性楼板运动关系为：

```text
u(x, y) = Ux - y * Rz
v(x, y) = Uy + x * Rz
```

速度、加速度同理。

刚心偏心不直接改变质量矩阵，而是通过构件布置或直接刚度矩阵进入刚度耦合项。质量矩阵建议保持：

```text
M_i = diag(m_i, m_i, Jz_i)
```

---

## 3. 配置文件设计

第一版建议使用 YAML 配置文件，而不是在脚本开头硬编码。建议配置项如下：

```yaml
model:
  num_stories: 10
  dof_per_floor: [Ux, Uy, Rz]
  coordinate_reference: geometry_center

floor_defaults:
  mass: 1.0e6
  jz: 8.0e6
  mass_center: [0.0, 0.0]

stories:
  - story: 1
    mass: 1.0e6
    jz: 8.0e6
    mass_center: [0.2, -0.1]
    elements:
      - {x: -5.0, y: -3.0, kx: 2.0e8, ky: 2.0e8}
      - {x:  5.0, y: -3.0, kx: 2.0e8, ky: 2.0e8}
      - {x:  5.0, y:  3.0, kx: 2.0e8, ky: 2.0e8}
      - {x: -5.0, y:  3.0, kx: 2.0e8, ky: 2.0e8}
    direct_stiffness:
      kx: 8.0e8
      ky: 8.0e8
      ktheta: 2.5e10
      stiffness_center: [0.0, 0.0]

sensors:
  - {id: roof_center_x, story: 10, x: 0.0, y: 0.0, direction: X, quantity: accel}
  - {id: roof_corner_x, story: 10, x: 5.0, y: 3.0, direction: X, quantity: accel}
  - {id: roof_corner_y, story: 10, x: 5.0, y: 3.0, direction: Y, quantity: accel}

damping:
  type: rayleigh
  zeta: 0.02
  modes: [1, 3]

ground_motion:
  dt: 0.01
  duration: 20.0
  ax_file: null
  ay_file: null
```

允许 `stories` 未逐层写满时使用 `floor_defaults` 和模板复制。

---

## 4. 方法 A：OpenSeesPy 三向层剪切模型

### 4.1 建模思想

方法 A 必须完整使用 OpenSeesPy 完成分析。推荐采用二维平面动力模型：

```python
ops.model('basic', '-ndm', 2, '-ndf', 3)
```

每个楼层设置一个主节点，位于该层质心，保留 `Ux, Uy, Rz` 三个自由度。每个抗侧构件位置设置从属节点，通过刚性连接与该层主节点形成刚性楼板。相邻楼层同一构件位置之间用线弹性弹簧连接。

OpenSeesPy 中 `rigidLink('beam', master, slave)` 可用于建立主从节点之间同时约束平动和转动自由度的刚性连接；`zeroLength` 单元可用多个单轴材料在指定自由度方向上连接两个同坐标节点。因此该方案可以在 OpenSees 内部自然形成层间平动-扭转耦合刚度。

### 4.2 节点与约束

每层需要三类节点：

```text
master node: 楼层质心主节点，参与动力自由度
spring node: 抗侧构件位置节点，用于连接层间弹簧
sensor node: 可选，测点位置节点，仅用于直接记录测点响应
```

处理规则：

1. 地面层主节点固定 `Ux, Uy, Rz`；
2. 动力楼层主节点赋予质量 `m, m, Jz`；
3. 每层 spring node 和 sensor node 通过 `rigidLink('beam', master, slave)` 连接到该层主节点；
4. 每个 story 的 spring node 与下一层同位置 spring node 之间布置 `zeroLength` 弹簧；
5. 弹簧方向使用 `dir 1` 和 `dir 2`，分别表示 X/Y 向层间抗侧刚度。

### 4.3 层间弹簧

每个抗侧构件可用两个线弹性材料表示：

```python
ops.uniaxialMaterial('Elastic', mat_x, kx)
ops.uniaxialMaterial('Elastic', mat_y, ky)
ops.element('zeroLength', ele_tag, lower_node, upper_node,
            '-mat', mat_x, mat_y,
            '-dir', 1, 2)
```

由于上下节点分别受各自楼层刚性楼板约束，OpenSees 会自动把构件位置 `(x, y)` 对应的刚体运动关系计入系统刚度。这样无需手动组装 `T.T @ k @ T`，但可以在后处理中用该公式导出理论层刚度进行对照。

### 4.4 动力分析

方法 A 的动力分析也应在 OpenSeesPy 中完成：

- 约束处理：优先使用 `Transformation`；
- 系统求解器：线性模型可使用 `BandGeneral` 或其他稳定求解器；
- 积分器：`Newmark`；
- 算法：线弹性模型可使用 `Linear`；
- 激励输入：优先支持 X/Y 双向地面加速度。

地震动输入可先实现两种模式之一：

1. `UniformExcitation`：实现简单，但节点响应通常为相对地面响应；
2. 等效惯性荷载：便于与方法 B 完全对齐。

第一版建议优先实现 `UniformExcitation`，同时在输出字段中明确区分相对加速度和绝对加速度。若要和方法 B 严格逐点比较，应统一输入和响应定义。

### 4.5 输出

OpenSees 后端至少输出：

```text
master_displacement.csv
master_velocity.csv
master_acceleration.csv
sensor_response.csv
modal_info.csv
```

可选导出：

```text
opensees_tangent_stiffness.txt
opensees_mass_matrix.txt
story_stiffness_theory.csv
```

刚度矩阵导出只用于对比分析，不应替代 OpenSees 的动力求解。

---

## 5. 方法 B：直接刚度矩阵构造模型

方法 B 使用 NumPy 显式构造总体矩阵并求解。它不是主分析后端，而是验证工具。

### 5.1 由构件布置构造层刚度

对于某层第 `j` 个构件：

```text
T_j = [[1, 0, -y_j],
       [0, 1,  x_j]]

k_j = [[kx_j, 0],
       [0, ky_j]]

K_story_j = T_j.T @ k_j @ T_j
```

层刚度为：

```text
K_story = sum(K_story_j)
```

该结果应与方法 A 导出的等效刚度进行比较。

### 5.2 由刚心偏心直接构造层刚度

若配置中直接给定 `Kx, Ky, Ktheta, stiffness_center`，则先将刚心坐标转换到质心坐标系：

```text
ex = x_stiffness_center - x_mass_center
ey = y_stiffness_center - y_mass_center
```

再构造：

```text
K_story =
[[ Kx,       0,        -Kx * ey],
 [ 0,        Ky,        Ky * ex],
 [ -Kx*ey,   Ky*ex,     Ktheta + Kx*ey^2 + Ky*ex^2]]
```

### 5.3 总体矩阵和积分

按层剪切关系组装总体 `K`，质量矩阵采用块对角：

```text
M_i = diag(m_i, m_i, Jz_i)
```

阻尼第一版使用 Rayleigh 阻尼：

```text
C = alpha * M + beta * K
```

动力积分使用线性 Newmark。输出格式应尽量与方法 A 完全一致，便于自动比较。

---

## 6. 共用模块划分

由于方法 A 已经由 OpenSeesPy 完成建模和分析，共用模块不应再假设所有后端都使用同一套 `M/C/K/Newmark`。建议拆分如下：

```text
qrest_model/
  common/
    config.py          读取 YAML、补默认值、校验参数
    coordinates.py     几何中心坐标 -> 质心坐标转换
    sensors.py         测点定义、测点响应字段、方向投影
    ground_motion.py   地震动读取、合成、插值、单位处理
    damping.py         Rayleigh 参数计算
    io.py              CSV/NPZ/JSON 输出
    compare.py         两种方法结果对比、误差范数、图表数据

  backends/
    opensees_story.py      方法 A：OpenSeesPy 全流程分析
    direct_stiffness.py    方法 B：直接矩阵构造和 Newmark 分析

  theory/
    story_stiffness.py     T.T @ k @ T 理论层刚度、刚心计算
    sensor_mapping.py      直接法测点响应映射
```

注意：

- `opensees_story.py` 内部负责 OpenSees 节点、材料、单元、约束、分析器和 recorder；
- `direct_stiffness.py` 内部负责矩阵组装和 Newmark；
- `theory/story_stiffness.py` 同时供方法 B 使用，也供方法 A 导出理论对照值；
- `common/sensors.py` 只定义测点元数据，OpenSees 后端可以把测点建成 sensor node，直接记录响应。

---

## 7. 建议脚本

```text
scripts/
  run_opensees_story.py       运行方法 A
  run_direct_stiffness.py     运行方法 B
  compare_backends.py         对比两种方法输出
```

命令示例：

```bash
python scripts/run_opensees_story.py --config configs/default_10story.yaml
python scripts/run_direct_stiffness.py --config configs/default_10story.yaml
python scripts/compare_backends.py --case output/default_10story
```

---

## 8. 验收标准

第一版完成后应满足以下检查：

1. **对称结构检查**  
   质量中心与刚心重合、X 向单向输入时，`Rz` 响应应接近 0。

2. **偏心结构检查**  
   刚心相对质心偏移后，X/Y 输入应能激发明显扭转响应，同层不同测点响应应出现差异。

3. **测点映射检查**  
   OpenSees sensor node 输出应与直接法的刚性楼板公式结果一致。

4. **刚度矩阵检查**  
   方法 A 导出的等效刚度或理论对照刚度，应与方法 B 的层刚度构造结果一致。

5. **动力响应检查**  
   在线弹性、相同输入、相同阻尼和相同响应定义下，方法 A 与方法 B 的主自由度响应趋势应一致。若使用 `UniformExcitation`，需明确比较的是相对响应还是绝对响应。

6. **数据格式检查**  
   两个后端输出字段尽量一致，至少包括：

```text
time, story, node_or_sensor_id, ux, uy, rz, ax, ay, arz
```

---

## 9. Codex 执行顺序

建议按以下顺序开发：

1. 建立 YAML 配置与参数校验；
2. 实现坐标转换、测点定义、地震动读取；
3. 实现 `theory/story_stiffness.py`，用于刚度理论对照；
4. 实现方法 B，先保证矩阵法可运行；
5. 实现方法 A，完整使用 OpenSeesPy 完成建模和分析；
6. 实现两个后端统一输出；
7. 实现 `compare_backends.py`；
8. 编写最小测试用例：对称结构、偏心结构、测点分布差异；
9. 补充 README，说明运行方式和输出解释。

---

## 10. 后续扩展

第一版完成后可继续扩展：

- 单向层剪切模型；
- 杆系模型 + 刚性楼板；
- 非线性弹簧或损伤退化；
- 风荷载、脉动荷载、环境振动输入；
- 传感器噪声、漂移、缺失、安装角误差；
- 批量工况生成与算法回归测试。
