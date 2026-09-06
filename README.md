# qREST 可控结构动力模型

本目录提供一个用于生成 qREST 测试数据的可控数值模型。它的目标不是替代精细有限元分析，而是生成结构、质量、刚度、阻尼、输入地震动和测点位置都明确可控的响应数据，方便算法单元测试、回归测试和异常结果排查。

当前包含三自由度刚性楼板模型、单向层剪切模型，以及 Stage 2 引入的四类二维离散线性模型。三自由度模型的基本假定为：

- 结构自由度：每层 `Ux, Uy, Rz`
- 楼板假定：刚性楼板
- 结构层数：配置文件控制，默认样例为 10 层
- 坐标参考：配置默认以几何中心为参考，程序内部统一转换到每层质心
- 材料和单元：线弹性
- 输出内容：楼层主自由度响应、测点响应、质量/刚度/阻尼矩阵、逐层理论刚度

新版模型配置建议在顶层声明 `schema_version: "2.0"`，并通过 `model.type` 明确模型类型：

- `rigid_floor_shear_3d`：三自由度刚性楼板剪切模型
- `shear_building_1d`：单向层剪切模型
- `euler_beam_2d`：Euler-Bernoulli 二维弯曲梁模型
- `rayleigh_beam_2d`：离散 Rayleigh-type beam，在 Euler 刚度与 consistent mass 基础上增加节点/楼层集中转动惯量
- `timoshenko_beam_2d`：包含弯曲和剪切变形的 Timoshenko 梁模型
- `shear_flexure_building_2d`：Euler 弯曲分支与层间剪切分支并联的弯剪建筑模型

旧配置暂时仍可读取，但程序会发出 legacy warning。`dof_per_floor` 继续作为模型自由度属性保留，不再作为模型类型识别依据。

## 目录结构

```text
story3d/                         三自由度刚性楼板模型工作区
  configs/
    default_10story.json
    variable_stiffness_16story_external_gm.json
  scripts/
    run_direct_stiffness.py
    run_opensees_story.py
    compare_backends.py
shear1d/                         单向层剪切模型工作区
  configs/
    shear_16story_external_gm.json
  scripts/
    run_direct_shear.py
    run_opensees_shear.py
    compare_shear_backends.py
beam2d/                          二维离散线性模型工作区
  configs/
    euler_3story.json
    rayleigh_3story.json
    timoshenko_3story.json
    shear_flexure_3story.json
output/                          多模型族默认输出，默认被 git 忽略
input/                           多模型共用的外部激励文件
config/
  datasets/                      批量生成测试数据的工况配置
  research/                      Stage 3 研究数据集 benchmark 配置
scripts/                         数据集生成、测点映射、元信息和导出入口
  build_datasets.py
  map_sensors.py
  make_metadata.py
  make_algorithm_configs.py
  export_datasets.py              兼容命令行包装，实际导出逻辑在 qrest_model/exporters/
qrest_model/
  analysis/                      统一线性系统、Newmark 和模态分析
  schema/                        配置 schema、dataclass 和归一化入口
  common/                        地震动、阻尼、IO、对比工具和旧配置兼容入口
  datasets/                      官方工况定义、生成流程和验证工具
  exporters/                     后端输出、时程、结构属性和 qREST 文本数据集导出
  models/                        结构物理模型对象
  observations/                  单向剪切和二维 beam 模型观测映射
  postprocess/                   测点刚性楼板映射
  theory/                        层刚度、梁单元和弯剪模型理论公式
  backends/
    direct_stiffness.py          三自由度：直接矩阵 + Newmark
    opensees_story.py            三自由度：OpenSeesPy 建模和动力分析
    direct_shear.py              单向层剪切：直接矩阵 + Newmark
    opensees_shear.py            单向层剪切：OpenSeesPy
    direct_euler.py              Euler 梁：统一线性直接法
    opensees_euler.py            Euler 梁：OpenSees elasticBeamColumn
    direct_rayleigh.py           Rayleigh 梁：Euler 刚度 + 节点转动惯量
    opensees_rayleigh.py         Rayleigh 梁：elasticBeamColumn + 节点转动质量
    direct_timoshenko.py         Timoshenko 梁：显式 Timoshenko 矩阵
    opensees_timoshenko.py       Timoshenko 梁：ElasticTimoshenkoBeam
    direct_shear_flexure.py      弯剪建筑：Euler 分支 + 层间剪切分支
    opensees_shear_flexure.py    弯剪建筑：elasticBeamColumn + twoNodeLink
```

## 两种后端

### Direct

Direct 后端使用 NumPy 显式组装总体质量矩阵 `M`、刚度矩阵 `K` 和 Rayleigh 阻尼矩阵 `C`，再用统一线性 Newmark 方法进行时程积分。该方法主要用于理论对照和回归测试。

当前 Direct 后端按模型类型分发：

- `direct_stiffness`：三自由度刚性楼板剪切模型
- `direct_shear`：单向层剪切模型
- `direct_euler`：Euler-Bernoulli 二维梁
- `direct_rayleigh`：Rayleigh 二维梁
- `direct_timoshenko`：Timoshenko 二维梁
- `direct_shear_flexure`：二维弯剪建筑模型

三自由度刚性楼板模型支持两种层刚度定义：

- 通过构件布置自动计算：`elements`
- 直接给定层刚度和刚心：`direct_stiffness`

二维线性模型复用同一个 `run_linear_direct()` 入口，不复制 Newmark、Rayleigh damping 或 modal analysis。

### OpenSees

使用 OpenSeesPy 建立二维三自由度楼层模型：

- `ops.model("basic", "-ndm", 2, "-ndf", 3)`
- 每层质心设置主节点
- 构件位置设置从属节点，并通过 `rigidLink("beam", master, slave)` 表示刚性楼板
- 相邻楼层同一构件位置之间使用 `zeroLength` 弹簧
- 使用 `UniformExcitation` 输入 X/Y 双向地面加速度
- 使用和直接法一致的 Rayleigh 阻尼系数

注意：OpenSees 后端要求每层显式给出 `elements`。若配置只给了 `direct_stiffness`，请使用 `direct_stiffness` 后端。
构件可通过可选 `id` 字段声明跨楼层对应关系；一旦使用 ID，每层所有构件都必须提供唯一且一致的 ID 集合。当前 `rigid_floor_shear_3d` OpenSees backend 假定层间抗侧构件沿高度保持相同平面位置，因此相邻楼层同一构件的归一化 `x/y` 坐标必须一致。

二维模型使用独立的 OpenSees 表示：

- `euler_beam_2d`：`elasticBeamColumn -cMass`
- `rayleigh_beam_2d`：`elasticBeamColumn -cMass` 加节点转动质量
- `timoshenko_beam_2d`：`ElasticTimoshenkoBeam -cMass`
- `shear_flexure_building_2d`：`elasticBeamColumn -cMass` 与水平 `twoNodeLink` 并联

二维模型的 OpenSees 后端使用与 Direct 一致的等效基底惯性荷载进行水平地面输入，并将 OpenSees `Rz` 映射为项目约定的 `Theta` 符号。Stage 3 另有专用 imposed support motion 集成验证，用 OpenSees `MultipleSupport`/`imposedMotion` 对比 Direct 等效惯性输入；该验证路径不替换现有 backend。

## 单向层剪切模型

除三自由度楼层模型外，本目录还提供单向层剪切模型。该模型每层只有一个平动自由度，适合快速生成一维层间剪切响应，也适合做基础动力算法验证。

单向模型配置的核心字段如下：

```json
{
  "model": {
    "num_stories": 16,
    "dof_per_floor": ["Ux"]
  },
  "floor_defaults": {
    "mass": 1000000.0
  },
  "stories": [
    {"story": 1, "stiffness": 800000000.0},
    {"story": 2, "stiffness": 800000000.0}
  ]
}
```

字段说明：

- `dof_per_floor` 可为 `["Ux"]` 或 `["Uy"]`
- `mass` 为楼层集中质量
- `stiffness` 为对应层间剪切刚度，第 1 层表示第 1 层相对地面的层间刚度

单向模型也提供两个后端：

- `direct_shear`：显式组装一维 `M/C/K` 并使用 Newmark 积分
- `opensees_shear`：使用 OpenSeesPy 的一维节点和 `zeroLength` 弹簧

## 二维梁与弯剪模型

Stage 2 新增的二维模型每层使用两个自由度：

```text
U, Theta
```

其中 `U` 是水平相对位移，`Theta` 是弯曲转角。示例配置位于：

```text
beam2d/configs/euler_3story.json
beam2d/configs/rayleigh_3story.json
beam2d/configs/timoshenko_3story.json
beam2d/configs/shear_flexure_3story.json
```

Euler、Rayleigh 和 Timoshenko 使用 `section_defaults` 与 `sections` 描述逐层等效截面：

```json
{
  "model": {
    "type": "euler_beam_2d",
    "num_stories": 3,
    "dof_per_floor": ["U", "Theta"]
  },
  "geometry": {
    "story_heights": [3.0, 3.0, 3.0]
  },
  "section_defaults": {
    "E": 30000000000.0,
    "A": 20.0,
    "I": 90.0,
    "density": 2500.0
  },
  "sections": [
    {"story": 1},
    {"story": 2},
    {"story": 3}
  ]
}
```

模型差异集中在 theory 层：

- Euler：Euler-Bernoulli 弯曲刚度与 consistent beam mass。
- Rayleigh：离散 Rayleigh-type beam，在 Euler 刚度与 consistent mass 基础上增加节点/楼层集中 `rotational_inertia`；它不是严格连续分布的 Rayleigh 梁单元实现。
- Timoshenko：使用 `G` 和 `shear_area` 定义剪切刚度，质量矩阵包含平动 consistent mass 与截面 rotary inertia。
- Shear-Flexure：Euler 弯曲分支与层间水平 `shear_stiffness` 并联。

Shear-Flexure 配置使用 `story_defaults`/`stories` 描述剪切分支，可在每层覆盖 `flexural_section`：

```json
{
  "model": {
    "type": "shear_flexure_building_2d",
    "num_stories": 3,
    "dof_per_floor": ["U", "Theta"]
  },
  "section_defaults": {
    "E": 30000000000.0,
    "A": 20.0,
    "I": 90.0,
    "density": 2500.0
  },
  "story_defaults": {
    "shear_stiffness": 800000000.0
  },
  "stories": [
    {"story": 1},
    {"story": 2, "flexural_section": {"I": 80.0}},
    {"story": 3, "shear_stiffness": 900000000.0}
  ]
}
```

统一 CLI 可直接运行这些配置：

```bash
.venv/bin/python -m qrest_model.cli run beam2d/configs/timoshenko_3story.json --backend direct
.venv/bin/python -m qrest_model.cli run beam2d/configs/shear_flexure_3story.json --backend opensees
```

## Python API

新的统一 backend 入口返回结构化 `AnalysisResult`：

```python
from qrest_model.backends import run_analysis

result = run_analysis("story3d/configs/default_10story.json", backend="direct")
print(result.relative.acceleration.shape)
```

`AnalysisResult` 将相对响应、绝对响应、地面运动、观测结果、质量/刚度/阻尼矩阵、模态结果和 metadata 分开保存。所有模型统一约定：`relative` 是结构相对地面响应，`ground` 是输入地面运动，`absolute` 是平动自由度叠加地面运动后的响应；旋转自由度在当前纯平动地面输入下不叠加地面运动。传感器 `value` 表示绝对响应，`relative_value` 表示相对响应。metadata 中的 `matrix_source`、`modal_source` 和 `response_source` 明确记录矩阵、模态和时程响应来源；OpenSees 后端的 `mass_matrix/stiffness_matrix/damping_matrix/modal` 来自 qrest_model 理论矩阵，并额外记录 `backend_modal_source: opensees_eigen`。现阶段 backend 仍保留旧 dict 输出，以便已有脚本继续运行；内部 `run_result()` 和统一 `run_analysis()` 已优先返回结构化结果。

## 观测语义

Stage 3 起，qREST Model 明确区分：

- Structural Truth：模型完整状态，例如刚性楼板 `Ux/Uy/Rz` 或 beam-like 模型 `U/Theta`。
- Derived Structural Quantity：由结构状态计算得到的派生结构量，后续用于 drift、curvature、shear deformation 等扩展。
- Observation：从结构状态映射得到的可用数据，分为 physical sensor 和 virtual probe。

`AnalysisResult.observations` 是新的观测结果入口；`AnalysisResult.sensors` 仍保留为兼容别名。每个 observation channel 记录 `kind`、`quantity`、`unit`、来源信息和 `operator`。`operator` 当前表示线性观测算子，用 `terms` 明确通道如何由 structural truth 的响应分量组合得到，例如刚性楼板 X 向偏置测点会记录 `Ux - y Rz`。当前规则为：

- 刚性楼板 X/Y 偏置测点是 physical translational observation，虽然映射中使用 `Rz`。
- 单向剪切模型测点是 physical translational observation。
- beam-like 模型 `U` 测点是 physical translational observation。
- beam-like 模型 `Theta` 和刚性楼板 `Rz` 是 structural truth 中的广义转角，可作为 virtual probe 输出，但不默认进入 qREST physical Instrument channel。

旧 `sensors` 配置仍兼容。若旧 beam 配置写了 `dof: "Theta"` 且未声明 `kind`，归一化时会将其视为 `kind: "virtual"`；若显式声明 `kind: "physical"` 又使用 `Theta` 或 `Rz`，配置会被拒绝。qREST metadata/export 默认只使用 physical observation，virtual probe 不会被伪装为 X/Y/Z 物理通道。

单位语义随观测类型区分：

- 平动位移、速度、加速度：`m`、`m/s`、`m/s^2`
- 转角位移、速度、加速度：`rad`、`rad/s`、`rad/s^2`

旧的脚本级 backend 函数仍返回兼容 dict：

```python
from qrest_model.backends.direct_stiffness import run

legacy = run("story3d/configs/default_10story.json")
```

backend 的 legacy 文件输出已迁移到 `qrest_model/exporters/backend_outputs.py`。官方数据集的工况定义、生成流程、OpenSees sensor-node 验证、master time-history 输出、结构属性输出、qREST metadata、算法配置和 qREST 文本数据集导出已经下沉到 `qrest_model/datasets/`、`qrest_model/postprocess/` 与 `qrest_model/exporters/`；`scripts/*.py` 只保留 CLI 入口和兼容重导出。

安装为 editable package 后可使用统一命令：

```bash
qrest-model run story3d/configs/default_10story.json --backend direct
qrest-model validate story3d/configs/default_10story.json --backend-a direct --backend-b opensees --abs-tol 1e-10 --rel-tol 1e-8
qrest-model generate-datasets --case two_x_one_y_torsion
qrest-model export-qrest --input output/test_datasets
qrest-model generate-research beam2d/configs/euler_3story.json --validate
qrest-model generate-research-cases --case oma_shear_3story --validate
```

未安装时可使用等价模块入口：

```bash
python -m qrest_model.cli generate-datasets --case single_x
```

## Linux 运行入口

下面命令默认从项目根目录 `/home/yue/CodeFiles/qrest_model` 执行，并使用项目虚拟环境：

```bash
.venv/bin/python --version
```

### 运行单个三自由度模型

直接刚度后端：

```bash
.venv/bin/python story3d/scripts/run_direct_stiffness.py \
  --config story3d/configs/default_10story.json
```

OpenSees 后端：

```bash
.venv/bin/python story3d/scripts/run_opensees_story.py \
  --config story3d/configs/default_10story.json
```

默认输出目录为：

```text
output/story3d/default_10story/direct_stiffness
output/story3d/default_10story/opensees_story
```

也可以手动指定输出目录：

```bash
.venv/bin/python story3d/scripts/run_direct_stiffness.py \
  --config story3d/configs/default_10story.json \
  --output output/story3d/compare_default/direct_stiffness
```

```bash
.venv/bin/python story3d/scripts/run_opensees_story.py \
  --config story3d/configs/default_10story.json \
  --output output/story3d/compare_default/opensees_story
```

### 运行单向模型

单向 16 层外部激励样例配置位于：

```text
shear1d/configs/shear_16story_external_gm.json
```

直接刚度后端：

```bash
.venv/bin/python shear1d/scripts/run_direct_shear.py \
  --config shear1d/configs/shear_16story_external_gm.json
```

OpenSees 后端：

```bash
.venv/bin/python shear1d/scripts/run_opensees_shear.py \
  --config shear1d/configs/shear_16story_external_gm.json
```

### 后端对比

推荐使用统一 CLI 对比任意模型：

```bash
.venv/bin/python -m qrest_model.cli validate beam2d/configs/euler_3story.json --backend-a direct --backend-b opensees
.venv/bin/python -m qrest_model.cli validate beam2d/configs/shear_flexure_3story.json --backend-a direct --backend-b opensees
```

当一个 case 目录下同时存在 `direct_stiffness` 和 `opensees_story` 子目录时，可运行：

```bash
.venv/bin/python story3d/scripts/compare_backends.py \
  --case output/story3d/compare_default \
  --output output/story3d/compare_default/compare_metrics.txt
```

单向模型对比命令为：

```bash
.venv/bin/python shear1d/scripts/compare_shear_backends.py \
  --case output/shear1d/shear_16story_external_gm \
  --output output/shear1d/shear_16story_external_gm/compare_metrics.txt
```

比较脚本默认读取：

```text
direct_stiffness/master_response.csv
opensees_story/master_response.csv
```

输出指标包括各响应量的最大绝对误差和相对 L2 误差。

## 生成 qREST 测试数据集

面向 qREST 算法测试的数据集由统一脚本生成，不再直接在脚本里硬编码工况。工况配置放在：

```text
config/datasets/
```

每个 JSON 对应一个工况，包含模型类型、质量/刚度、输入地震动和测点布局。脚本会把配置中的简写布局展开成后端可直接读取的完整 `config.json`。例如 `layout: two_x` 会在指定楼层生成两侧 X 向测点，`layout: center_y` 会在指定楼层生成中心 Y 向测点。

生成全部工况：

```bash
qrest-model generate-datasets
```

只生成一个工况：

```bash
qrest-model generate-datasets --case two_x_one_y_torsion
```

指定外部配置目录：

```bash
qrest-model generate-datasets --config-root path/to/dataset_configs
```

默认输出到：

```text
output/test_datasets/
```

每个工况一个子目录，目录结构为：

```text
config.json                展开后的模型配置，可被 direct 后端直接读取
metadata.json              qREST 元信息，可与 time_history/acceleration.csv 配套使用
dataset_info.json          数据集生成说明
master_time_history/       所有楼层质点绝对响应
time_history/              配置测点映射后的绝对响应
  acceleration.csv
  velocity.csv
  displacement.csv
structural_properties/     质量、刚度、阻尼、主频和振型等结构动力特性
config/                    与该模型数据匹配的 qREST 算法配置
```

`master_time_history` 输出所有质点的绝对时程，每个文件第 1 列是 `time`，其余列形如：

```text
story_01_x, story_01_y, story_01_rz, ..., story_16_x, story_16_y, story_16_rz
```

`time_history` 下每个文件的第 1 列是 `time`，其余每列是一个观测点的单向绝对物理量，例如 2X1Y 工况中：

```text
time,01f_x_yneg,01f_x_ypos,01f_y_xpos,...
```

`structural_properties` 保留结构动力学基础信息，不混入时程文件：

```text
mass_matrix.csv
stiffness_matrix.csv
damping_matrix.csv
modal_frequencies.csv
mode_shapes.csv
story_stiffness.csv
summary.json
```

其中矩阵 CSV 使用 DOF 标签作为行列名；`modal_frequencies.csv` 输出圆频率、Hz 频率和周期；`mode_shapes.csv` 输出质量归一化振型，列为 `mode_01`、`mode_02` 等。

`config` 目录仿照 `resource/qrest_data/<dataset>/config`，但参数由当前模型数据生成，而不是复制 Kunming/Wuhan 或通用 `resource/config`：

- 预处理和 RR 的滤波频带根据采样频率和结构基频生成。
- OMA 的 `init_frequencies` 来自 `structural_properties/modal_frequencies.csv`。
- MaxEDP 的 `column_position` 来自模型平面足迹。
- IM 的特征周期使用结构基准周期。

导出为 qREST 文本数据集时，`qrest_model.exporters.qrest_dataset` 会优先复制生成数据目录中的这个 `config/`；`scripts/export_datasets.py` 仍保留为兼容命令行入口。

正式工况主要在 1F、3F、7F、11F、16F 布设测点，错层混合工况额外在 1F、4F、8F、12F、16F 布设中心 Y 测点。模型配置使用均匀侧向刚度：所有楼层继承同一个四角构件布置，`stories` 中只保留楼层编号以简化配置。扭转工况通过质量中心偏心 `[0.2, 0.3]` 产生，几何中心仍为 `[0.0, 0.0]`。输入地震动采样间隔按原始文件设置为 `0.02s`。

也可以单独从模型配置生成 qREST 元信息：

```bash
.venv/bin/python scripts/make_metadata.py \
  --config output/test_datasets/two_x_one_y_torsion/config.json \
  --data output/test_datasets/two_x_one_y_torsion/time_history/acceleration.csv \
  --output output/test_datasets/two_x_one_y_torsion/metadata.json
```

该脚本生成的 `metadata.json` 使用 qREST 标准字段：`BuildingInfo`、`InstrumentInfo` 和 `DataInfo`。通道顺序与 `acceleration.csv` 中观测列顺序一致，X/Y/Z 方向分别使用 Azimuth `90/0/-1`。

如果只调整测点方案，不需要重新计算结构响应。修改 `config.json` 中的 `sensors` 后，可用所有质点时程重新映射测点：

```bash
.venv/bin/python scripts/map_sensors.py \
  --config output/test_datasets/two_x_one_y_torsion/config.json \
  --master-dir output/test_datasets/two_x_one_y_torsion/master_time_history \
  --output-dir output/test_datasets/two_x_one_y_torsion/time_history \
  --metadata-output output/test_datasets/two_x_one_y_torsion/metadata.json
```

若要把这些生成数据作为 `src/qrest_algorithm_test` 的输入数据源，可导出为 qREST 文本数据集目录：

```bash
qrest-model export-qrest --input output/test_datasets
```

默认导出到：

```text
output/qrest_datasets/
```

若要直接给相邻 qREST C++ 测试工程使用，可显式指定 qrest_module 下的输出目录。

导出的目录包含 `<case>_metadata.json`、`<case>_data.txt` 和模型数据自身的 `config/`，可直接传给 C++ 测试：

```bash
xmake run test_qrest_algorithm_im resource/test_output/generated_datasets/single_x
xmake run test_qrest_algorithm_rr resource/test_output/generated_datasets/two_x_one_y_torsion
```

也可直接传给 `src/qrest_algorithm_example` 下的原生 C ABI 示例：

```bash
xmake run example_im resource/test_output/generated_datasets/single_x
xmake run example_edp_max resource/test_output/generated_datasets/two_x_torsion
```

PyMethod 示例也支持相同的数据目录参数：

```bash
xmake run example_rr_pymethod resource/test_output/generated_datasets/two_x_one_y_torsion
```

## 生成研究数据集

Stage 3 新增 research dataset 出口，用于同时保存完整结构真值、physical observation 和 virtual probe。它与 qREST text dataset 分离：research dataset 面向算法研究和真值验证，qREST dataset 面向模拟真实监测数据。

生成单个研究数据集：

```bash
qrest-model generate-research beam2d/configs/euler_3story.json --validate
```

生成内置研究 benchmark：

```bash
qrest-model generate-research-cases --validate
qrest-model generate-research-cases --case mbi_timoshenko_3story_sparse --validate
```

默认输出到：

```text
output/research_datasets/<case-name>/
```

批量生成时，`output/research_datasets/manifest.json` 是集合级索引；每个子目录仍保留自己的 `manifest.json`。集合索引按 case name 排序，汇总 `research` 标签、truth 尺寸、physical/virtual observation 数量、derived quantity、稳定配置哈希和噪声配置状态。当前第一批 benchmark 不注入噪声，因此集合索引中的 `noise.configured` 为 `false`。

目录结构为：

```text
manifest.json
config.json
truth/
  response.npz
  matrices.npz
  modal.npz
  structural_properties.json
derived/
  structural.npz
observations/
  physical/
    acceleration.csv
    velocity.csv
    displacement.csv
  virtual/
    acceleration.csv
    velocity.csv
    displacement.csv
metadata/
  derived.json
  observation.json
  provenance.json
```

`truth/response.npz` 保存完整 `relative/absolute/ground` 时程；`truth/matrices.npz` 保存 `M/K/C` 和 DOF 标签；`truth/modal.npz` 保存真实频率、周期和质量归一化振型。`derived/structural.npz` 保存由 truth 计算得到的派生结构量，当前包括平动层间位移差、层间位移角和 beam-like 模型的层间转角差，并在 `metadata/derived.json` 记录单位、shape 和来源。`observations/physical` 只保存 physical sensor 通道，`observations/virtual` 保存研究用 virtual probe。`metadata/observation.json` 为每个 channel 保存 observation operator，research validator 会检查 operator 结构、frame、quantity、story、DOF 和系数合法性。单个 dataset 的 `manifest.json` 带有 `content_summary`，用于快速读取 time steps、DOF 数、observation 数量、observation quantity 和 derived quantity ID。`manifest.json` 和 `metadata/provenance.json` 使用稳定配置哈希，不写生成时间戳，因此同一 config/backend 生成结果可复现。

`config/research/` 当前提供 9 个小规模 deterministic benchmark，覆盖所有 schema model family，并满足 Stage 3 第一批 OMA/MBI 族类覆盖：

```text
oma_shear_3story                    shear_building_1d，OMA 用全楼层 X 加速度
oma_euler_3story                    euler_beam_2d，OMA 用 U 加速度与 Theta virtual probe
oma_timoshenko_3story               timoshenko_beam_2d，OMA 用 U 加速度与 Theta virtual probe
mbi_shear_3story_sparse             shear_building_1d，稀疏 X 加速度
mbi_euler_3story_sparse             euler_beam_2d，稀疏 U 加速度与 Theta virtual probe
mbi_rigid_3story_sparse             rigid_floor_shear_3d，稀疏 X/Y 加速度与 Rz virtual probe
mbi_rayleigh_3story_sparse          rayleigh_beam_2d，稀疏 U 加速度与 Theta virtual probe
mbi_timoshenko_3story_sparse        timoshenko_beam_2d，稀疏 U 加速度与 Theta virtual probe
mbi_shear_flexure_3story_sparse     shear_flexure_building_2d，稀疏 U 加速度与 Theta virtual probe
```

这些 benchmark 的单个 `manifest.json` 会保留 `truth_policy`、`observation_config`、`noise_config`、`export_policy` 和 `research` 元数据；批量根目录的集合索引会把这些 case 摘要汇总到一个稳定 JSON 中，便于后续 OMA、mode completion 和 model-based identification 流程按研究任务筛选。

## 官方批量测试工况

官方 qREST 文本数据集仍会生成 5 类工况：

```text
single_x                 单向 X 数据
dual_xy                  双向 X/Y 数据
two_x_one_y_torsion      2X1Y，可体现扭转
two_x_torsion            2X，可体现单向平动和扭转
staggered_2x_center_y    错层混合数据：1/3/7/11/16F 两侧 X，1/4/8/12/16F 中心 Y
```

竖向 Z 数据暂不生成，因为当前模型本体未引入竖向结构自由度。`2X1Y` 和 `2X` 工况使用质量中心偏心，使输入能够激发 `Rz`。两个 X 测点布置在同一 `x`、不同 `y` 位置，因此通道差异中包含扭转贡献。

`staggered_2x_center_y` 是用于算法研究的错层特殊数据。它在不同楼层形成不同数据能力：1F/16F 为 `XYR`，3F/7F/11F 为 `MX`，4F/8F/12F 为 `Y`，整体会被 qREST 识别为 `MIXED_DIRECTION`。
当前 OMA 后处理明确拒绝 `MIXED_DIRECTION`，因此该工况可用于 qREST 数据读取、IM、Preprocess、RR、EDP 测试和后续算法研究，但不作为现有 OMA 通过用例。

## 输出文件约定

两个后端尽量使用相同文件名，便于自动对比。

响应时程统一使用 CSV：

```text
master_response.csv
sensor_response.csv
```

参数、矩阵和元信息统一使用 TXT：

```text
mass_matrix.txt
stiffness_matrix.txt
damping_matrix.txt
story_stiffness_theory.txt
metadata.txt
```

### `master_response.csv`

每一行对应一个时间步和一个楼层主节点。三自由度刚性楼板模型字段为：

```text
time, story, node_or_sensor_id,
ux, uy, rz, vx, vy, vrz, ax, ay, arz,
abs_ux, abs_uy, abs_rz, abs_vx, abs_vy, abs_vrz, abs_ax, abs_ay, abs_arz
```

其中：

- `ux, uy, rz`、`vx, vy, vrz`、`ax, ay, arz`：相对地面的主自由度响应
- `abs_*`：在平动方向叠加地面运动后的绝对响应；`Rz` 无地面转动输入，因此 `abs_rz/abs_vrz/abs_arz` 与相对值相同

地面位移和速度由输入地面加速度按梯形积分得到，初始地面位移和速度取 0。

二维 `beam2d` 模型字段为：

```text
time, story, node_or_sensor_id,
u, theta, v, vtheta, a, atheta,
abs_u, abs_theta, abs_v, abs_vtheta, abs_a, abs_atheta
```

其中 `u/v/a` 是水平平动响应，`theta/vtheta/atheta` 是弯曲转角响应；绝对响应只对水平平动叠加地面运动。

### `sensor_response.csv`

每一行对应一个时间步和一个测点。三自由度直接刚度后端的测点响应由刚性楼板公式从楼层主自由度映射得到：

```text
u(x, y) = Ux - y * Rz
v(x, y) = Uy + x * Rz
```

OpenSees 后端会按传感器坐标创建仅用于记录的 sensor node，并通过 `rigidLink("beam", master, sensor)` 连接到楼层主节点。

字段包含：

```text
time, story, node_or_sensor_id, direction, quantity,
ux, uy, rz, vx, vy, vrz, ax, ay, arz,
abs_ux, abs_uy, abs_rz, abs_vx, abs_vy, abs_vrz, abs_ax, abs_ay, abs_arz,
value, relative_value
```

`value` 是按测点 `direction` 和 `quantity` 投影后的绝对标量响应；`relative_value` 保留对应的相对响应。

二维模型的传感器字段使用 `dof` 代替 `direction`，支持 `U` 与 `Theta`，其余响应语义保持一致。

### 矩阵和参数文件

- `mass_matrix.txt`：总体质量矩阵 `M`
- `stiffness_matrix.txt`：总体刚度矩阵 `K`
- `damping_matrix.txt`：Rayleigh 阻尼矩阵 `C = alpha M + beta K`
- `story_stiffness_theory.txt`：逐层理论刚度或截面/分支参数表
- `metadata.txt`：后端名称、响应定义、Rayleigh 阻尼系数等

矩阵文件使用逗号分隔，方便用 `numpy.loadtxt(path, delimiter=",")` 读取。

## 配置说明

默认配置文件为：

```text
story3d/configs/default_10story.json
```

另有一个 16 层变刚度外部激励样例：

```text
story3d/configs/variable_stiffness_16story_external_gm.json
```

关键配置项：

- `model.num_stories`：楼层数
- `floor_defaults.mass`：默认楼层质量
- `floor_defaults.jz`：默认楼层绕 z 轴转动惯量
- `floor_defaults.mass_center`：质量中心坐标
- `elements`：构件位置和 X/Y 向刚度
- `sensors`：测点楼层、坐标、方向和响应类型
- `damping`：Rayleigh 阻尼设置
- `ground_motion`：地震动时间步、总时长、文件输入或合成输入

坐标默认相对于几何中心。加载配置时，程序会把构件、测点和刚心坐标转换到每层质心坐标系：

```text
x_c = x_g - x_mass_center
y_c = y_g - y_mass_center
```

### 逐层参数变化

程序支持每层参数不同。配置加载时会先读取 `floor_defaults`，再用 `stories` 中对应楼层的字段覆盖默认值。因此：

- 如果每层完全相同，可以只在 `floor_defaults` 中写 `mass`、`jz`、`elements` 等参数，并在 `stories` 中只列出楼层编号。
- 如果某一层参数不同，在该层的 `stories` 条目中写出需要覆盖的字段即可。
- 如果覆盖 `elements`，该层会使用新的构件列表，而不是和默认构件列表逐项合并。

例如，下面表示第 1 层继承默认质量和转动惯量，但使用自己的构件刚度：

```json
{
  "story": 1,
  "elements": [
    {"id": "corner_sw", "x": -5.0, "y": -3.0, "kx": 2.0e8, "ky": 2.0e8},
    {"id": "corner_se", "x": 5.0, "y": -3.0, "kx": 2.0e8, "ky": 2.0e8},
    {"id": "corner_ne", "x": 5.0, "y": 3.0, "kx": 2.0e8, "ky": 2.0e8},
    {"id": "corner_nw", "x": -5.0, "y": 3.0, "kx": 2.0e8, "ky": 2.0e8}
  ]
}
```

`variable_stiffness_16story_external_gm.json` 中 16 层结构的构件刚度从底层到顶层线性降低，顶层刚度为底层的 80%。底层单个构件刚度为 `2.0e8`，顶层单个构件刚度为 `1.6e8`。

### 外部激励文件

外部地震动通过 `ground_motion.ax_file` 和 `ground_motion.ay_file` 指定：

```json
{
  "ground_motion": {
    "dt": 0.01,
    "duration": 149.99,
    "ax_file": "../../input/gm_x.txt",
    "ay_file": "../../input/gm_y.txt",
    "ax_scale": 1.0,
    "ay_scale": 1.0
  }
}
```

路径相对于配置文件所在目录解析。例如三自由度配置位于 `story3d/configs/`，则 `../../input/gm_x.txt` 指向 `input/gm_x.txt`。

支持两种文件格式：

- 单列：每行一个加速度值。程序使用配置中的 `dt` 生成时间轴。
- 两列：第一列为时间，第二列为加速度。程序会插值到配置中的统一时间轴。

`duration` 和 `dt` 共同决定输出步数：

```text
n_steps = round(duration / dt) + 1
```

如果单列文件有 15000 个点，且 `dt=0.01`，应设置 `duration=149.99`，这样输出时间为 `0.00 ~ 149.99 s`，正好使用全部 15000 个点。

`ax_scale` 和 `ay_scale` 可用于单位换算或幅值缩放。例如输入文件单位为 `g`，而分析希望使用 `m/s^2`，可设置缩放系数为 `9.80665`。

## 测试

运行模型相关测试：

```bash
.venv/bin/python -m pytest tests
```

当前测试覆盖：

- schema、响应语义、`AnalysisResult` invariant 和 legacy wrapper
- schema 分层重导出、矩阵/模态/响应 provenance metadata 和独立观测映射
- 对称结构在 X 向输入下扭转响应接近 0
- 偏心结构能激发扭转响应
- 测点刚性楼板映射公式
- 对称构件布置的层刚度矩阵耦合项
- Euler、Rayleigh、Timoshenko 和 Shear-Flexure 的单元矩阵、装配矩阵和模型分发
- Rayleigh → Euler、Timoshenko → Euler、Shear-Flexure → Flexure 的物理极限
- 新增二维模型的 Direct 与 OpenSees 后端逐点对照
- OpenSees imposed support motion 与 Direct 等效基底惯性输入的独立对照
- story/global 刚度正定性与 Rayleigh 参考频率重频保护
- dataset/exporter/CLI 生成链路和 golden regression signatures

OpenSees 集成测试带有独立 marker。默认若未设置环境变量会跳过实际 OpenSees 求解：

```bash
QREST_RUN_OPENSEES_TESTS=1 .venv/bin/python -m pytest -m opensees
```

仓库内的 GitHub Actions 会在 push/pull_request 上运行非 OpenSees 单元测试，并在 `workflow_dispatch` 手动触发时运行 OpenSees marker 测试。

## 已知说明

三自由度刚性楼板 OpenSees 后端使用 `UniformExcitation`，输出为 OpenSees 节点相对响应；直接刚度后端也输出相对楼层响应，并在内存结果中保留平动绝对位移、速度和加速度。两种方法在线弹性、小时间步下响应趋势和峰值时刻应保持一致，但由于 OpenSees 内部时程分析、约束处理和阻尼实现与直接矩阵积分并非完全同一路径，逐点误差不一定为零。

二维 beam2d 模型的 OpenSees 后端使用与 Direct 质量矩阵对应的等效基底惯性荷载输入，并通过测试比较频率、相对位移、速度、加速度和绝对加速度。Shear-Flexure 的 `twoNodeLink` 水平弹簧显式指定 local x 方向，因此 OpenSees 会打印 “ignoring nodes and using specified local x vector to determine orientation” 的提示；这是预期行为，不影响数值对照。
