# 第四轮公告扫描页文字补充

范围：原数据库中185个 `needs_ocr` 页面，共20份原公告。主数据库只读；原件PDF与首次提取状态不改动。

本轮采用本地 RapidOCR 3.9.2 / ONNX Runtime 1.23.2 CPU；安装在 `work/round4_ocr/deps`，不安装全局包。模型由版本固定的RapidOCR wheel携带，不上传原件或渲染图片。渲染采用已有pypdfium2 5.14.0，200 DPI，CPU线程限制为2。依赖下载报告包含PyPI文件URL和wheel哈希，3个ONNX模型逐个记录哈希。

- `jobs.json`：185页原件、页码、SHA256、公告URL、标题和公告日期。
- `ocr_local.py`：可复现的OCR脚本，只输出工作目录的逐页JSONL。
- `pilot.jsonl`、`pilot_images/`、`pilot_validation.json`：两页小样本结果和有限视觉抽核。
- `pages.jsonl`、`pages_summary.json`：全量逐页结果及耗时。
- `verify_results.py`、`verification.json`：身份、完整性与状态校验，**不证明OCR文字准确**。
- `review_queue.json`：按低置信度行数排序的人工复核队列，优先级仅为启发规则。
- `install_report.json`、`dependency_sources.json`、`model_sources.json`、`environment.json`、`licenses/`：版本、来源和许可留档。

运行（在项目根目录）：

```sh
/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/round4_ocr/ocr_local.py --limit 2 --output pilot.jsonl --save-images
/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/round4_ocr/ocr_local.py --output pages.jsonl
/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/round4_ocr/verify_results.py
```

所有取得文本的页面仍是 `ocr_extracted_unverified`，`numeric_facts_verified=false`、`historical_input_eligible=false`、`manual_review_status=not_reviewed`。小样本只比较3处打印文字，既未审核完整页面，也未认证金额。印章、签名有乱码；数字和标点即使置信度高也可能错读；侧转表格的文字顺序不能直接还原单元格对应关系。后续财务入模前需原图逐字段复核。

[官方安装文档](https://rapidai.github.io/RapidOCRDocs/v3.9.2/install_usage/rapidocr/install/)、[官方使用文档](https://rapidai.github.io/RapidOCRDocs/v3.9.2/install_usage/rapidocr/usage/)、[参数文档](https://rapidai.github.io/RapidOCRDocs/v3.9.2/install_usage/rapidocr/parameters/)。RapidOCR与PaddleOCR官方仓库许可证为Apache-2.0；ONNX Runtime为MIT，副本与哈希已保存。模型来源按RapidOCR官方README记为衍生自官方PaddleOCR模型，具体转换构建以wheel及模型哈希固定，未扩张许可结论。
