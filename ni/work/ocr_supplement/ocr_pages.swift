import Foundation
import PDFKit
import Vision
import AppKit

// Local OCR of source pages only. No database writes or network operations.
let args = CommandLine.arguments
guard args.count == 3 else { fatalError("usage: ocr_pages jobs.json output.jsonl") }
let jobsData = try Data(contentsOf: URL(fileURLWithPath: args[1]))
let jobs = try JSONSerialization.jsonObject(with: jobsData) as! [[String: Any]]
let outputURL = URL(fileURLWithPath: args[2])
FileManager.default.createFile(atPath: outputURL.path, contents: nil)
let output = try FileHandle(forWritingTo: outputURL)
defer { try? output.close() }

let iso = ISO8601DateFormatter()
for (position, job) in jobs.enumerated() {
    autoreleasepool {
        var result: [String: Any] = [
            "art_code": job["art_code"]!,
            "page_number": job["page_number"]!,
            "source_sha256": job["source_sha256"]!,
            "source_hash_verified_before_ocr": job["sha256_verified"]!,
            "engine": "Apple Vision VNRecognizeTextRequest / PDFKit",
            "operating_system": ProcessInfo.processInfo.operatingSystemVersionString,
            "recognition_level": "accurate",
            "recognition_languages": ["zh-Hans", "en-US"],
            "uses_language_correction": false,
            "automatically_detects_language": false,
            "uses_cpu_only": true,
            "text": "", "observations": [], "error": NSNull(),
            "status": "failed", "retrieved_at": iso.string(from: Date()),
            "numeric_facts_verified": false,
        ]
        do {
            let pdfPath = job["pdf_path"] as! String
            guard let doc = PDFDocument(url: URL(fileURLWithPath: pdfPath)),
                  let page = doc.page(at: (job["page_number"] as! Int) - 1) else {
                throw NSError(domain: "OCRSupplement", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "Unable to read source PDF page"])
            }
            let bounds = page.bounds(for: .mediaBox)
            let targetWidth = 2400.0
            let targetSize = NSSize(width: targetWidth, height: targetWidth * bounds.height / bounds.width)
            let pageImage = page.thumbnail(of: targetSize, for: .mediaBox)
            guard let cgImage = pageImage.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                throw NSError(domain: "OCRSupplement", code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "Unable to render source page"])
            }
            result["render_width"] = cgImage.width
            result["render_height"] = cgImage.height
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.usesLanguageCorrection = false
            request.automaticallyDetectsLanguage = false
            request.usesCPUOnly = true
            result["vision_revision"] = request.revision
            result["supported_recognition_languages"] = try request.supportedRecognitionLanguages()
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            try handler.perform([request])
            var observations: [[String: Any]] = []
            for observation in request.results ?? [] {
                if let candidate = observation.topCandidates(1).first {
                    let bbox = observation.boundingBox
                    observations.append(["text": candidate.string,
                        "confidence": candidate.confidence,
                        "bounding_box": ["x": bbox.origin.x, "y": bbox.origin.y,
                            "width": bbox.width, "height": bbox.height]])
                }
            }
            let text = observations.compactMap { $0["text"] as? String }.joined(separator: "\n")
            let confidences = observations.compactMap { $0["confidence"] as? Float }
            result["text"] = text
            result["observations"] = observations
            result["status"] = text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? "empty_unverified" : "ocr_extracted_unverified"
            result["mean_confidence"] = confidences.isEmpty ? NSNull()
                : confidences.reduce(0, +) / Float(confidences.count) as Any
            result["minimum_confidence"] = confidences.min().map { $0 as Any } ?? NSNull()
        } catch {
            result["error"] = String(describing: error)
        }
        do {
            var encoded = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
            encoded.append(0x0a)
            try output.write(contentsOf: encoded)
            try output.synchronize()
        } catch { fatalError("Output write failed: \(error)") }
        print("page \(position + 1)/\(jobs.count) \(job["art_code"]!) \(job["page_number"]!) \(result["status"]!)")
        fflush(stdout)
    }
}
