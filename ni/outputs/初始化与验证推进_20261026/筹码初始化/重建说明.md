# 本地重建

```sh
/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  work/chip_initialization_oct26/build_initialization_v2.py \
  --project-root /Users/puchun/Documents/Codex/2026-10-07/ni
```

依赖Python 3.12.14、NumPy 2.3.5、SQLite 3.53.1，不联网。只写本任务work与outputs/初始化与验证推进_20261026/筹码初始化。源统一库以只读immutable方式打开。

common_origin为2022-06-01交易前：未知质量1、已观察质量0；首日换手包含在乘积。每日子概率Q不重归一，U不硬置零。known_observed_bins.observed_contribution_mass求和为1−U；conditional_known_mass才另行归一，不能作为总体筹码。CDF上下界只依赖未知质量，不限制未知价格支持，网格外允许未知质量。总体均值空值，分位无穷界用kind标记。

SQL未读取未来收益表、网页筹码摘要或现时前复权序列。prefix测试是计算因果性证明；原始输入历史可用性未认证，模型门不因此开放。

源统一库SHA-256：9538ca8bf5944acca50a563967c98f04c010943637bf608ba17fc50eda25dd14。
脚本SHA-256：a1a84e0e4efc0ef8eb42c1179cb2759eb9b9e1db30edd22a7231d627565c6342。
SQLite SHA-256：601198bc50663b005ec08fda6b7e97364fc8a37bcb84a23bc90a3683559f00fc。
