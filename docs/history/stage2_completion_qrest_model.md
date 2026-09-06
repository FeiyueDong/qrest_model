# qREST Model Stage 2 完成记录

本文记录 Stage 2 在当前源码中的已实现状态。开发计划仍保留在 `docs/dev/Stage 2 update qrest_model.md`，本文只描述已经落地并通过验证的内容。

## 完成范围

Stage 2 已把 `qrest_model` 从刚性楼板和一维剪切模型扩展为多模型族线性结构动力学试验平台。

当前支持的 `model.type`：

- `rigid_floor_shear_3d`
- `shear_building_1d`
- `euler_beam_2d`
- `rayleigh_beam_2d`
- `timoshenko_beam_2d`
- `shear_flexure_building_2d`

新增二维模型统一使用每层 `[U, Theta]` 自由度，并在 `beam2d/configs/` 提供 3 层示例配置。

## 架构落点

新增模型主要落在以下边界：

- `qrest_model/schema/case.py`：模型常量、dataclass、load/normalize 入口。
- `qrest_model/theory/`：单元矩阵、装配矩阵和等效基底激励荷载。
- `qrest_model/models/`：结构模型包装，暴露 `mass_matrix()`、`stiffness_matrix()`、`influence_matrix()`。
- `qrest_model/backends/`：Direct 与 OpenSees 的模型专用入口。
- `qrest_model/backends/base.py`：统一后端分发。
- `qrest_model/exporters/backend_outputs.py`：二维模型 legacy 文件输出。
- `qrest_model/cli.py`：统一运行和默认输出路径。

`run_linear_direct()` 仍然是二维模型的 Direct 计算核心；Newmark、Rayleigh damping 和 modal analysis 没有在各模型后端内复制。

## 模型说明

Euler-Bernoulli：

- 刚度使用标准 Euler-Bernoulli 弯曲梁单元。
- 质量使用 consistent beam mass。
- OpenSees 对照使用 `elasticBeamColumn -cMass`。

Rayleigh：

- 刚度与 Euler 相同。
- 质量为 Euler consistent mass 加节点 `rotational_inertia`。
- OpenSees 对照使用 `elasticBeamColumn -cMass` 加节点转动质量。

Timoshenko：

- 刚度使用 `E/I/G/shear_area` 构造，包含剪切变形参数 `phi`。
- 质量显式实现 translational consistent mass 加 section rotary inertia。
- OpenSees 对照使用 `ElasticTimoshenkoBeam -cMass`。

Shear-Flexure：

- 弯曲分支使用 Euler-Bernoulli 梁刚度。
- 剪切分支使用层间水平剪切弹簧，并与弯曲分支并联。
- OpenSees 对照使用 `elasticBeamColumn -cMass` 加水平 `twoNodeLink`。

## 验收映射

Stage 2 开发计划中的验收项当前状态：

- Geometry：已完成，模型配置支持 `story_heights` 与 `elevations`，导出元信息不再自行假设固定楼层高度。
- Model family：已完成，Euler、Rayleigh、Timoshenko、Shear-Flexure 均已落地。
- Unified Direct：已完成，新增二维模型复用 `run_linear_direct()`。
- OpenSees：已完成，新增二维模型均具备独立 OpenSees representation。
- Theory validation：已完成，测试覆盖单元矩阵、装配、模态和正定性边界。
- Physics validation：已完成，覆盖 Rayleigh -> Euler、Timoshenko -> Euler、Shear-Flexure -> Flexure。
- Integration validation：已完成，新增二维模型均有 Direct 与 OpenSees 对照。
- Regression：已完成，新增二维模型均有 golden reference。

## 验证记录

本阶段收尾时通过以下验证：

```bash
.venv/bin/python -m pytest -q
```

结果：

```text
78 passed, 19 skipped
```

```bash
PYTHONPATH=.:/home/yue/CodeFiles/qrest_module/py_scripts .venv/bin/python -m pytest -q
```

结果：

```text
80 passed, 17 skipped
```

```bash
env QREST_RUN_OPENSEES_TESTS=1 PYTHONPATH=.:/home/yue/CodeFiles/qrest_module/py_scripts .venv/bin/python -m pytest -q
```

结果：

```text
97 passed
```

同时完成：

- `.venv/bin/python -m compileall -q qrest_model tests`
- `git diff --check`
- `beam2d/configs/shear_flexure_3story.json` 的 Direct/OpenSees CLI 冒烟输出
- `beam2d/configs/timoshenko_3story.json` 的 Direct/OpenSees CLI 冒烟输出
- `beam2d/configs/shear_flexure_3story.json` 的 Direct/OpenSees CLI validate，对比误差为 1e-13 量级

## 保留边界

Stage 2 仍保持线性、小模型、可控 ground-truth 定位，未引入：

- 三维梁族
- 竖向自由度
- 多点支承输入
- nonlinear/hysteretic story model
- base isolation
- massless DOF static condensation

这些内容适合进入后续阶段单独设计。
