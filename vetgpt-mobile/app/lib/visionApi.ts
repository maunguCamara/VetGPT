/**
 * vetgpt-mobile/lib/visionApi.ts
 *
 * Phase 3 — Premium vision API client.
 * Handles image upload, OCR, X-ray, wound/lesion/parasite/cytology analysis.
 * Uses multipart/form-data — no axios, native fetch only.
 */

import { BASE_URL } from './api';
import { getItem } from './storage';

const TOKEN_KEY = 'vetgpt_auth_token';

export type ImageType =
  | 'general'
  | 'wound'
  | 'lesion'
  | 'parasite'
  | 'cytology'
  | 'xray'
  | 'ultrasound';

export interface VisionAnalysisResult {
  image_type: string;
  analysis: string;
  ocr_text: string;
  rag_context: Array<{
    text: string;
    document_title: string;
    page_number: number;
    score: number;
  }>;
  engine_used: string;
  latency_ms: number;
  disclaimer: string;
}

export interface OCRResult {
  text: string;
  word_count: number;
  message: string;
  configured: boolean;
}

// ─── Core upload helper ───────────────────────────────────────────────────────

async function uploadImage(
  endpoint: string,
  imageUri: string,
  fields: Record<string, string> = {},
): Promise<Response> {
  const token = await getItem(TOKEN_KEY);
  if (!token) throw new Error('Authentication required. Please sign in.');

  const formData = new FormData();

  // React Native file object format
  const filename  = imageUri.split('/').pop() ?? 'image.jpg';
  const extension = filename.split('.').pop()?.toLowerCase() ?? 'jpg';
  const mimeMap: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg',
    png: 'image/png',  webp: 'image/webp',
    tiff: 'image/tiff', tif: 'image/tiff',
    dcm: 'application/dicom',
  };
  const mimeType = mimeMap[extension] ?? 'image/jpeg';

  formData.append('file', {
    uri:  imageUri,
    name: filename,
    type: mimeType,
  } as any);

  for (const [key, value] of Object.entries(fields)) {
    formData.append(key, value);
  }

  return fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 403) {
    throw new Error('This feature requires a premium subscription. Upgrade in Settings.');
  }
  if (res.status === 401) {
    throw new Error('Session expired. Please sign in again.');
  }
  if (res.status === 413) {
    throw new Error('Image too large. Maximum size is 20 MB.');
  }
  if (res.status === 415) {
    throw new Error('Unsupported image format. Use JPEG, PNG, WebP, TIFF, or DICOM.');
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as any)?.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// ─── Public API ───────────────────────────────────────────────────────────────

export async function analyzeImage(
  imageUri: string,
  imageType: ImageType = 'general',
  query: string = '',
  runOcr: boolean = false,
): Promise<VisionAnalysisResult> {
  const res = await uploadImage('/api/vision/analyze', imageUri, {
    image_type: imageType,
    query,
    run_ocr: runOcr ? 'true' : 'false',
  });
  return handleResponse<VisionAnalysisResult>(res);
}

export async function analyzeXray(
  imageUri: string,
  query: string = '',
): Promise<VisionAnalysisResult> {
  const res = await uploadImage('/api/vision/xray', imageUri, { query });
  return handleResponse<VisionAnalysisResult>(res);
}

export async function analyzeWound(
  imageUri: string,
  query: string = '',
): Promise<VisionAnalysisResult> {
  const res = await uploadImage('/api/vision/wound', imageUri, { query });
  return handleResponse<VisionAnalysisResult>(res);
}

export async function analyzeLesion(
  imageUri: string,
  query: string = '',
): Promise<VisionAnalysisResult> {
  const res = await uploadImage('/api/vision/lesion', imageUri, { query });
  return handleResponse<VisionAnalysisResult>(res);
}

export async function analyzeParasite(
  imageUri: string,
  query: string = '',
): Promise<VisionAnalysisResult> {
  const res = await uploadImage('/api/vision/parasite', imageUri, { query });
  return handleResponse<VisionAnalysisResult>(res);
}

export async function analyzeCytology(
  imageUri: string,
  query: string = '',
): Promise<VisionAnalysisResult> {
  const res = await uploadImage('/api/vision/cytology', imageUri, { query });
  return handleResponse<VisionAnalysisResult>(res);
}

export async function extractOCRText(imageUri: string): Promise<OCRResult> {
  const res = await uploadImage('/api/vision/ocr', imageUri);
  return handleResponse<OCRResult>(res);
}
