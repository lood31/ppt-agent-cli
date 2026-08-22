# Vendored engine notice

- Upstream: https://github.com/EveryInc/hands-on-deck
- Commit: `a24b996ecff6393ccf39c4fee2b88c493fb0b693`
- License: MIT (`LICENSE` in this directory)
- Included with source content unchanged; checkout line endings are normalized by Git on Windows: `deck.py`, `inventory.py`, `replace.py`
- Vendored-file SHA-256 at freezing time:
  - `deck.py`: `c8ab0f1001fa711efd3aa878a13d03908abc18af8c4fecaf08e25306b1e68c50`
  - `inventory.py`: `8b123f18dcc988fe2e4a54ee0e049f6e84f8cb2ecf2c699e6c266cc80390ed57`
  - `replace.py`: `62b449c6888d996cbca0b06c3e50525a34b550ec30eb2d88b69540660c88245e`

The three source files were also downloaded again from the fixed commit during the 2026-08-12 freeze review. Their text is identical after line-ending normalization.

The public `xml set` escape hatch in the upstream tool is not exposed by `ppt-agent`.
