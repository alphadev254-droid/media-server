# Media Server — Usage Guide

**Base URL:** `https://media.yourdomain.com` (or `http://localhost:3010` for local development)

All endpoints require the `X-API-Key` header.

---

## Endpoints

### Health Check

```
GET /health
```

```bash
curl https://media.yourdomain.com/health
```

**Response:**
```json
{ "status": "ok" }
```

---

### Upload File

```
POST /upload/
```

**Headers:**

| Header | Required | Description |
|---|---|---|
| `X-API-Key` | ✅ | API key |
| `X-Client-Id` | ✅ | Your system name e.g. `icims`, `aircnc` |
| `X-Media-Base-Url` | ✅ | Must match your `ALLOWED_MEDIA_BASE_URLS` in `.env` |

**Body:** `multipart/form-data` with field `file`

**Supported types:**

| Category | Formats |
|---|---|
| Images | `jpg`, `png`, `gif`, `webp`, `svg` |
| Videos | `mp4`, `webm`, `mov`, `mkv` |
| Audio | `mp3`, `wav`, `ogg`, `aac` |
| Documents | `pdf`, `doc`, `docx` |

**Max size:** 100MB

```bash
curl -X POST https://media.yourdomain.com/upload/ \
  -H "X-API-Key: your_api_key" \
  -H "X-Client-Id: aircnc" \
  -H "X-Media-Base-Url: https://media.yourdomain.com" \
  -F "file=@/path/to/photo.jpg"
```

**Response:**
```json
{
  "id": "a7690131-a5ef-4867-81c9-3467637a3835.webp",
  "bucket": "media-images",
  "url": "https://media.yourdomain.com/media-images/a7690131-a5ef-4867-81c9-3467637a3835.webp",
  "size": 3100,
  "mime": "image/webp"
}
```

> Images are auto-converted to WebP and optimized. Store the `url` in your database.

---

### Delete File

```
DELETE /upload/{bucket}/{key}
```

```bash
curl -X DELETE https://media.yourdomain.com/upload/media-images/a7690131-a5ef-4867-81c9-3467637a3835.webp \
  -H "X-API-Key: your_api_key"
```

**Response:**
```json
{ "deleted": true }
```

---

### Get Signed URL (private files)

For files that need temporary access (e.g. if you set a bucket back to private).

```
GET /media/signed/{bucket}/{key}?expires=3600
```

```bash
curl "https://media.yourdomain.com/media/signed/media-videos/uuid.mp4?expires=3600" \
  -H "X-API-Key: your_api_key"
```

**Response:**
```json
{
  "url": "https://media.yourdomain.com/media-videos/uuid.mp4?X-Amz-Expires=3600&...",
  "expires_in": 3600
}
```

---

### Metrics

```
GET /metrics
```

```bash
curl https://media.yourdomain.com/metrics \
  -H "X-Metrics-Token: your_metrics_token"
```

---

## Buckets

| Bucket | File types | Access |
|---|---|---|
| `media-images` | `jpg`, `png`, `gif`, `webp`, `svg` | Public |
| `media-audio` | `mp3`, `wav`, `ogg`, `aac` | Public |
| `media-documents` | `pdf`, `doc`, `docx` | Public |
| `media-videos` | `mp4`, `webm`, `mov` | Public |

---

## Integration Examples

### Node.js / Express

```js
const FormData = require('form-data')
const fetch = require('node-fetch')
const fs = require('fs')

async function uploadMedia(filePath, clientId) {
  const form = new FormData()
  form.append('file', fs.createReadStream(filePath))

  const res = await fetch('https://media.yourdomain.com/upload/', {
    method: 'POST',
    headers: {
      'X-API-Key': process.env.MEDIA_API_KEY,
      'X-Client-Id': clientId,
      'X-Media-Base-Url': 'https://media.yourdomain.com',
      ...form.getHeaders(),
    },
    body: form,
  })

  return res.json() // { id, bucket, url, size, mime }
}

// Usage
const { url } = await uploadMedia('./photo.jpg', 'icims')
// store url in your DB
```

### Python / Django / FastAPI

```python
import httpx

async def upload_media(file_bytes: bytes, filename: str, client_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            'https://media.yourdomain.com/upload/',
            headers={
                'X-API-Key': settings.MEDIA_API_KEY,
                'X-Client-Id': client_id,
                'X-Media-Base-Url': 'https://media.yourdomain.com',
            },
            files={'file': (filename, file_bytes)},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()  # { id, bucket, url, size, mime }

# Usage
data = await upload_media(file.read(), file.filename, 'repair-ai')
image_url = data['url']  # store in DB
```

### Flutter / Dart

```dart
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

Future<String> uploadMedia(List<int> bytes, String filename) async {
  final uri = Uri.parse('https://media.yourdomain.com/upload/');
  final request = http.MultipartRequest('POST', uri)
    ..headers.addAll({
      'X-API-Key': 'your_api_key',
      'X-Client-Id': 'aircnc',
      'X-Media-Base-Url': 'https://media.yourdomain.com',
    })
    ..files.add(http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: filename,
      contentType: MediaType('image', 'jpeg'),
    ));

  final response = await request.send();
  final body = await response.stream.bytesToString();
  final data = jsonDecode(body);
  return data['url']; // store in DB
}
```

### React / Axios

```jsx
import axios from 'axios'

const uploadMedia = async (file, clientId) => {
  const form = new FormData()
  form.append('file', file)

  const { data } = await axios.post(
    'https://media.yourdomain.com/upload/',
    form,
    {
      headers: {
        'X-API-Key': import.meta.env.VITE_MEDIA_API_KEY,
        'X-Client-Id': clientId,
        'X-Media-Base-Url': 'https://media.yourdomain.com',
      },
    }
  )

  return data // { id, bucket, url, size, mime }
}

// Usage
const { url } = await uploadMedia(fileInput.files[0], 'aircnc')
```

---

## Error Responses

| Code | Meaning |
|---|---|
| 400 | Missing `X-Media-Base-Url` header |
| 403 | Invalid API key or disallowed media base URL |
| 413 | File too large (max 100MB) |
| 415 | File type not allowed |
| 422 | Could not process image |
| 500 | Server error |

---

## API Test Script

A test script is included to verify all endpoints are working. It tests health, CORS, upload, public access, signed URLs, metrics, and delete — all in one run.

```bash
# Test the live server
python test_api.py --host https://media.yourdomain.com --image "path/to/test.jpg"

# Test locally
python test_api.py --image "path/to/test.jpg"

# Specify custom credentials
python test_api.py --host https://media.yourdomain.com \
  --image "bedsitter 2.jpg" \
  --api-key "your_api_key" \
  --metrics-token "your_metrics_token"
```

**What it checks:**
- ✅ Health endpoint returns `{status: ok}`
- ✅ CORS allows your origin, blocks others
- ✅ Upload with valid/invalid/missing headers
- ✅ File is publicly accessible after upload
- ✅ Signed URL generation with expiry
- ✅ Prometheus metrics with auth
- ✅ Delete and re-delete (idempotent)

---

## MinIO Admin Console

The MinIO web UI (console) runs on port **9001**, but it's blocked from public access via the firewall for security. Access it through an SSH tunnel:

```bash
# From your local machine (NOT the server)
ssh -L 9001:127.0.0.1:9001 root@91.108.121.232
```

Then open **[http://localhost:9001](http://localhost:9001)** in your browser.

**Login credentials** — use the values from your `.env` file:
- **Username:** `MINIO_ACCESS_KEY`
- **Password:** `MINIO_SECRET_KEY`

---

## Server Management

```bash
# Status
systemctl status minio media-api

# Logs
journalctl -u media-api -f
journalctl -u minio -f

# Restart
systemctl restart media-api
systemctl restart minio

# Update (pull latest code)
cd /data/media-server
git pull
systemctl restart media-api
```
