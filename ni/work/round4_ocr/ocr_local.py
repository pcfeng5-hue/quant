#!/usr/bin/env python3
"""Offline OCR of source-hash-verified announcement pages; never writes SQLite."""
import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'deps'))
import numpy as np
import pypdfium2 as pdfium
from rapidocr import RapidOCR


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--output', default='pages.jsonl')
    parser.add_argument('--save-images', action='store_true')
    args = parser.parse_args()
    jobs = json.loads((HERE / 'jobs.json').read_text())
    if args.limit:
        jobs = jobs[:args.limit]
    model_dir = HERE / 'deps' / 'rapidocr' / 'models'
    model_paths = {
        'Det': model_dir / 'PP-OCRv6_det_small.onnx',
        'Rec': model_dir / 'PP-OCRv6_rec_small.onnx',
        'Cls': model_dir / 'ch_ppocr_mobile_v2.0_cls_mobile.onnx',
    }
    for p in model_paths.values():
        assert p.is_file(), p
    params = {f'{k}.model_path': str(v) for k, v in model_paths.items()}
    params.update({
        'Global.max_side_len': 3000,
        'EngineConfig.onnxruntime.intra_op_num_threads': 2,
        'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        'EngineConfig.onnxruntime.use_cuda': False,
        'EngineConfig.onnxruntime.use_coreml': False,
    })
    # The installed ONNX models are explicit local paths. Input is a local PIL image;
    # there is no image upload or network operation in this script.
    engine = RapidOCR(params=params)
    model_hashes = {k: sha(v) for k, v in model_paths.items()}
    images_dir = HERE / 'pilot_images'
    if args.save_images:
        images_dir.mkdir(exist_ok=True)
    started = time.monotonic()
    statuses = {}
    output_path = HERE / args.output
    with output_path.open('w', encoding='utf-8') as out:
        for i, job in enumerate(jobs, 1):
            begin = time.monotonic()
            row = dict(job)
            row.update({
                'engine': 'RapidOCR 3.9.2 / ONNX Runtime 1.23.2 CPU',
                'models_sha256': model_hashes,
                'render_engine': 'pypdfium2',
                'render_dpi': 200,
                'render_scale': 200 / 72,
                'parameters': params,
                'recognition_threshold': 0.5,
                'review_priority_threshold': 0.8,
                'text': '', 'observations': [], 'error': None,
                'status': 'failed',
                'numeric_facts_verified': False,
                'historical_input_eligible': False,
                'manual_review_status': 'not_reviewed',
                'uploaded': False,
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
            })
            try:
                actual_hash = sha(job['pdf_path'])
                row['source_hash_verified_before_ocr'] = actual_hash == job['source_sha256']
                if actual_hash != job['source_sha256']:
                    raise ValueError('original PDF hash mismatch')
                doc = pdfium.PdfDocument(job['pdf_path'])
                try:
                    page = doc[job['page_number'] - 1]
                    try:
                        bitmap = page.render(scale=200 / 72)
                        try:
                            pil = bitmap.to_pil().copy().convert('RGB')
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                finally:
                    doc.close()
                row['render_width'], row['render_height'] = pil.size
                if args.save_images:
                    image_path = images_dir / f"{job['art_code']}_p{job['page_number']}.png"
                    pil.save(image_path)
                    row['render_relative_path'] = str(image_path.relative_to(HERE))
                    row['render_sha256'] = sha(image_path)
                result = engine(pil, use_det=True, use_cls=True, use_rec=True)
                texts = list(result.txts or [])
                scores = list(result.scores or [])
                boxes = plain(result.boxes) if result.boxes is not None else []
                if not (len(texts) == len(scores) == len(boxes)):
                    raise ValueError('OCR text/score/box lengths differ')
                row['text'] = '\n'.join(texts)
                row['observations'] = [
                    {'text': t, 'confidence': float(s), 'box_pixels': b}
                    for t, s, b in zip(texts, scores, boxes)
                ]
                row['lines'] = len(texts)
                row['chars'] = len(row['text'])
                row['mean_confidence'] = statistics.mean(scores) if scores else None
                row['minimum_confidence'] = min(scores) if scores else None
                row['low_confidence_lines'] = sum(s < 0.8 for s in scores)
                row['engine_elapsed_seconds'] = float(result.elapse or 0)
                row['status'] = 'ocr_extracted_unverified' if row['text'].strip() else 'empty_unverified'
                pil.close()
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'
            row['elapsed_seconds'] = time.monotonic() - begin
            statuses[row['status']] = statuses.get(row['status'], 0) + 1
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            out.flush()
            print(f"{i}/{len(jobs)} {job['art_code']} p{job['page_number']} {row['status']} chars={len(row['text'])} seconds={row['elapsed_seconds']:.2f}", flush=True)
    summary = {'pages': len(jobs), 'statuses': statuses,
               'elapsed_seconds': time.monotonic() - started,
               'source_database_modified': False, 'uploaded': False,
               'numeric_facts_verified': False, 'model_hashes': model_hashes,
               'result_path': str(output_path), 'render_dpi': 200}
    (HERE / f'{output_path.stem}_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
