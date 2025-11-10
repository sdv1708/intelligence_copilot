---
title: Executive Intelligence Copilot
emoji: 🧠
colorFrom: blue
colorTo: purple
sdk: streamlit
sdk_version: "1.39.0"
app_file: app.py
pinned: false
license: mit
python_version: "3.11"
---

# 🧠 Executive Intelligence Copilot

**Prepare for meetings in minutes, not hours.**

An AI-powered meeting preparation assistant that analyzes documents, generates meeting briefs, and answers questions about your materials.

## Features

- 📄 **Document Upload**: Support for PDF, DOCX, PPTX, and TXT files
- 🤖 **AI-Powered Briefs**: Generate comprehensive meeting briefs automatically
- 💬 **Q&A Interface**: Ask questions about your documents
- 🚀 **GPU Acceleration**: Optimized for fast embeddings on GPU hardware
- 🔍 **Semantic Search**: Powered by FAISS and sentence-transformers

## Quick Start on Hugging Face Spaces

### 1. Fork this Repository

Click the "Fork" button to create your own copy.

### 2. Create a New Space

1. Go to [Hugging Face Spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Choose "Streamlit" as the SDK
4. Link your forked repository

### 3. Configure Secrets

Add your API keys in the Space settings under "Settings" → "Repository secrets":

**Required (choose one):**
- `GEMINI_API_KEY` - For Google Gemini (recommended, free tier available)
- `OPENAI_API_KEY` - For OpenAI GPT-4
- `ANTHROPIC_API_KEY` - For Anthropic Claude

**Environment Variable:**
- `LLM_PROVIDER` - Set to `gemini`, `openai`, or `anthropic`

### 4. Choose Hardware

**Free Tier (CPU):**
- Works out of the box
- Slower embeddings (~15-30s for 10 pages)
- Perfect for demos and light usage

**Upgrade to GPU ($0.60/hour):**
- 15-20x faster embeddings (~1-2s for 10 pages)
- Recommended for production use
- Enable in Space settings → "Hardware" → "T4 GPU"

## Deployment Steps (Detailed)

### Option A: Direct GitHub Connection

1. **Push your code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/intelligence_copilot.git
   git push -u origin main
   ```

2. **Create HF Space**
   - Go to https://huggingface.co/new-space
   - Name: `intelligence-copilot`
   - SDK: Streamlit
   - Python version: 3.11
   - Click "Create Space"

3. **Link GitHub repo**
   - Settings → "Files and versions"
   - "Import repository" → Enter your GitHub URL
   - Wait for build to complete

4. **Configure secrets**
   - Settings → "Repository secrets"
   - Add your API keys (see step 3 above)

### Option B: Direct Upload

1. **Create Space** on Hugging Face
2. **Upload files** directly through the web interface
3. **Add `.env` file** with your API keys (not recommended for production)

## Environment Variables

Set these in your Space's Repository Secrets:

| Variable | Description | Required |
|----------|-------------|----------|
| `LLM_PROVIDER` | LLM provider (`gemini`, `openai`, or `anthropic`) | Yes |
| `GEMINI_API_KEY` | Google Gemini API key | If using Gemini |
| `OPENAI_API_KEY` | OpenAI API key | If using OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic API key | If using Anthropic |

## Performance Tips

1. **Enable GPU** for production workloads
   - Settings → Hardware → T4 GPU
   - Cost: ~$0.60/hour (pay as you go)
   - 15-20x faster than CPU

2. **Optimize for CPU** if staying on free tier
   - Keep documents under 20 pages
   - Process files one at a time
   - Be patient with embeddings

3. **Monitor usage**
   - Check Space logs for performance
   - Watch for timeouts on large files
   - Consider upgrading if slow

## Troubleshooting

### App won't start
- Check logs in the Space → "Logs" tab
- Verify all required secrets are set
- Ensure `requirements.txt` dependencies installed

### Slow performance
- Upgrade to GPU hardware
- Check if model is loading on each request
- Verify GPU is detected (should show "🚀 GPU Accelerated" badge)

### Out of memory
- Reduce document size
- Lower embedding batch size
- Upgrade to higher memory hardware

### API errors
- Verify API keys are correct
- Check API key has sufficient credits
- Ensure `LLM_PROVIDER` matches your key

## Cost Estimates

| Configuration | Cost | Speed | Best For |
|---------------|------|-------|----------|
| CPU (Free) | $0 | Slow | Demos, testing |
| T4 GPU | $0.60/hr* | Fast | Production, demos |
| A10G GPU | $3.15/hr* | Fastest | Heavy usage |

*Only charged when Space is running (can pause when not in use)

## Architecture

- **Frontend**: Streamlit
- **Database**: SQLite (persistent on HF Spaces)
- **Vector Store**: FAISS
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2
- **LLM**: Gemini / OpenAI / Anthropic (configurable)

## Files Required

Make sure these files are in your Space:

```
├── app.py                 # Main Streamlit app
├── requirements.txt       # Python dependencies
├── .streamlit/
│   └── config.toml       # Streamlit configuration
├── core/                 # Core modules
│   ├── db.py
│   ├── embed.py
│   ├── recall.py
│   └── ...
├── agents/               # LLM orchestration
│   └── copilot_orchestrator.py
├── prompts/              # LLM prompts
│   ├── system_prompt.txt
│   ├── user_prompt.txt
│   └── ...
└── README.md            # This file (with HF metadata)
```

## Support

For issues or questions:
- Check the [main documentation](../../README.md)
- Review [DEPLOYMENT_GUIDE.md](../../DEPLOYMENT_GUIDE.md)
- Open an issue on GitHub

## License

MIT License - See [LICENSE](../../LICENSE) for details

