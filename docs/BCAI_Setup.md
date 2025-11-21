# BCAI Integration Guide

## Quick Setup (3 Steps)

### 1. Get BCAI Credentials
- Obtain a BCAI PAT token from your organization
- Ensure you're on Boeing network or VPN

### 2. Configure `.env`
```bash
cp .env.example .env
```

Edit `.env` and update:
```bash
LLM__PROVIDER=bcai
LLM__MODEL=gpt-4o-mini
LLM__API_BASE=https://bcai.web.boeing.com
LLM__API_KEY=<your-bcai-pat-token>

EMBEDDINGS__PROVIDER=bcai
EMBEDDINGS__MODEL=text-embedding-3-small
```

### 3. Run Diagnostic
```bash
python tests/bcai_diagnostics.py
```

**Expected:** `✅ All checks passed!`

Done! Start your application.

---

## Available Models

**LLMs:** `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4o-sovereign`  
**Embeddings:** `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`

---

## Common Issues

### ❌ "LLM__API_KEY is still the placeholder value"
**Fix:** Replace `your-bcai-pat` with your actual PAT token

### ❌ "Access forbidden (403)"
**Causes:**
- Invalid PAT token
- PAT lacks BCAI API permissions
- Not on Boeing network/VPN

**Fix:**
1. Verify you're on Boeing VPN
2. Test your PAT:
   ```bash
   curl -X POST https://bcai.web.boeing.com/bcai-public-api/conversation \
     -H "Authorization: basic YOUR_PAT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}],"stream":false}'
   ```
3. If 403 persists, contact BCAI support

### ❌ "Cannot connect to bcai.web.boeing.com"
**Fix:** Connect to Boeing VPN

### ❌ "LLM__PROVIDER is 'openai' but should be 'bcai'"
**Fix:** Set `LLM__PROVIDER=bcai` in `.env`

---

## Diagnostic Tool

The diagnostic checks:
- ✅ `.env` file configuration
- ✅ Network connectivity
- ✅ Authentication
- ✅ API functionality

**Run it:** `python tests/bcai_diagnostics.py`

It will tell you exactly what's wrong and how to fix it.

---

## Verification

### Check Logs
Look for:
```
✓ LlamaIndex LLM configured: BCAI (gpt-4o-mini)
```

### Process a Document
Upload a PDF - it should process without 403 errors.

---

## Environment Variables Reference

| Variable | Required | Example |
|----------|----------|---------|
| `LLM__PROVIDER` | Yes | `bcai` |
| `LLM__MODEL` | Yes | `gpt-4o-mini` |
| `LLM__API_BASE` | Yes | `https://bcai.web.boeing.com` |
| `LLM__API_KEY` | Yes | Your PAT token |
| `EMBEDDINGS__PROVIDER` | No | `bcai` |
| `EMBEDDINGS__MODEL` | No | `text-embedding-3-small` |

---

## BCAI vs OpenAI

**Differences:**
- **Auth:** BCAI uses `basic <PAT>` not `Bearer sk-...`
- **Endpoint:** `/bcai-public-api/conversation`
- **Network:** Requires Boeing VPN

**Similarities:**
- Same request/response format
- Multi-modal support (vision)
- Structured outputs (JSON schema)
- Embeddings API

**Switching:** Just change `.env` - no code changes needed!

---

## Need Help?

1. **Run diagnostic:** `python tests/bcai_diagnostics.py`
2. **Read error messages** - they tell you what to fix
3. **Check VPN connection**
4. **Verify PAT token** has BCAI API access

**Reference:** `docs/BCAI_doc.md` for full API documentation

