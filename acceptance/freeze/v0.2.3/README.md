# v0.2.3 acceptance freeze

This directory freezes the exact product and machine schema used for the
2026-08-14 beta acceptance run.

- Product version: `0.2.3`
- Machine schema version: `2.1`
- Engine: `hands-on-deck@a24b996`
- Source tree SHA-256: `ce1bbdebd8b8e94dcfb25523d45bba59c8016d4e4ee91989e515743a285ad12f`
- EXE SHA-256: `9825ce12fb2e05c5e3a0fc5820ed4f770d59adf1d9ce0fa6acd3f58cf56a2cb5`
- Full apply schema SHA-256: `3cc3dd898ac23e8203dd6842aca51743429c5f7113218a209f27b40f82b8a263`

`freeze-manifest.json` contains per-file hashes for every distribution input.
`capabilities.json` and `apply-schema.json` are the exported machine contracts.

The copied project did not include its own `.git` directory. This is therefore
a content-addressed acceptance freeze, not a Git commit or tag. Do not claim a
Git release freeze until the repository metadata has been restored or a new
repository has been initialized intentionally.
