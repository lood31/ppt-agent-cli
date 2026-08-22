# Third-party notices

本清单基于 `uv.lock` 和当前 Python 3.12 Windows 构建环境中的包元数据生成。版本与许可证标识必须在每次发布构建后重新核对；若发布包中的组件集合变化，本文件也必须同步更新。

这不是本项目自身许可证。本项目根许可证仍需由版权所有者明确选择并放入发行包。

## Vendored runtime engine

| Component | Version/source | License | License text |
|---|---|---|---|
| EveryInc/hands-on-deck | commit `a24b996ecff6393ccf39c4fee2b88c493fb0b693` | MIT | `vendor/hands_on_deck/LICENSE` |

上游来源、固定文件与审计记录见 `vendor/hands_on_deck/NOTICE.md` 和 `audit/hands-on-deck.md`。

## Declared runtime dependency closure

| Package | Locked version | License from installed metadata/license file |
|---|---:|---|
| Pillow | 12.3.0 | MIT-CMU |
| pydantic | 2.13.4 | MIT |
| python-pptx | 1.0.2 | MIT |
| pywin32 | 311 | PSF-style license shipped by pywin32 |
| typer | 0.27.1 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| colorama | 0.4.6 | BSD-3-Clause text |
| lxml | 6.1.1 | BSD-3-Clause; distribution also carries bundled component license texts |
| markdown-it-py | 4.2.0 | MIT |
| mdurl | 0.1.2 | MIT text |
| pydantic-core | 2.46.4 | MIT |
| Pygments | 2.20.0 | BSD-2-Clause |
| rich | 15.0.0 | MIT |
| shellingham | 1.5.4 | ISC |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| XlsxWriter | 3.2.9 | BSD-2-Clause |

`typer` 目前属于 `pyproject.toml` 的声明依赖，即使当前 CLI 入口直接使用 `argparse`，源安装的依赖闭包仍包含它及其传递依赖，因此没有从清单中省略。

## Single-file EXE build tooling

| Package | Locked version | License |
|---|---:|---|
| PyInstaller | 6.22.0 | GPL-2.0-or-later with the PyInstaller bootloader exception permitting distribution of non-free programs |
| pyinstaller-hooks-contrib | 2026.6 | Multi-license collection; authoritative terms are in its installed `LICENSE` file |
| altgraph | 0.17.5 | MIT |
| pefile | 2024.8.26 | MIT |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause text |

PyInstaller 是构建工具；其 bootloader 和运行时钩子可能进入单文件 EXE。发布审计必须保留 PyInstaller 的特殊例外及 community hooks 的实际许可证文件，不能只保留本摘要。

## Distribution requirement

正式发行 ZIP 至少应同时包含：

- 项目根 `LICENSE`（由版权所有者选择）；
- 本文件；
- `vendor/hands_on_deck/LICENSE` 与 `vendor/hands_on_deck/NOTICE.md`；
- 实际进入 EXE 的第三方组件所要求保留的完整许可证与版权声明。

本文件是可审计的组件索引，不替代各许可证要求的完整文本。构建后应检查 PyInstaller 分析结果并与本清单对账，避免遗漏隐式打包组件。

