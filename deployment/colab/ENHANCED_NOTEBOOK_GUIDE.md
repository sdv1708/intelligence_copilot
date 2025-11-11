# 📓 Enhanced Colab Notebook - User Guide

## 🎯 What's New in This Version

Your new enhanced notebook includes:

✅ **Google Drive Persistence** - Data survives session restarts  
✅ **Better Error Messages** - Clear status at each step  
✅ **Streamlined Setup** - Fewer cells, clearer flow  
✅ **Real-Time Logging** - See exactly what's happening  
✅ **Debug Tools** - Check database and GPU usage  

---

## 📋 File Location

```
deployment/colab/intelligence_copilot_enhanced.ipynb
```

**Original notebook** (still available):
```
deployment/colab/intelligence_copilot.ipynb
```

---

## 🚀 How to Use

### 1. Upload to Google Colab

**Option A: Upload File**
1. Go to https://colab.research.google.com/
2. File → Upload notebook
3. Select `intelligence_copilot_enhanced.ipynb`

**Option B: Open from Drive**
1. Upload notebook to your Google Drive
2. Right-click → Open with → Google Colaboratory

---

### 2. Enable GPU

1. Click **Runtime** menu
2. Select **Change runtime type**
3. Choose **T4 GPU**
4. Click **Save**

---

### 3. Run All Cells

Press **Ctrl+F9** or click **Runtime → Run all**

The notebook will:
1. ✅ Check GPU (should show T4)
2. ✅ Mount Google Drive (allow access when prompted)
3. ✅ Wait for project upload
4. ✅ Install dependencies
5. ✅ Ask for API keys
6. ✅ Launch your app

---

## 📊 What Each Step Does

### Step 1: GPU Check
Shows if GPU is detected. You want to see:
```
✅ GPU DETECTED!
   Device: Tesla T4
```

### Step 2: Google Drive Mount
**IMPORTANT:** Click "Allow" when prompted!

Your data saves to:
```
/content/drive/MyDrive/intelligence_copilot_data/
```

This means your meetings/briefs **persist forever**!

### Step 3: Project Upload
**Before running this cell:**
1. Click folder icon on left sidebar
2. Click upload folder icon
3. Select your entire `intelligence_copilot` folder
4. Wait for upload (shows progress)
5. Then run the cell

### Step 4: Dependencies
Installs all packages (~2 minutes). Runs quietly.

### Step 5: API Keys
Interactive prompts for:
- **LLM provider** (choose Gemini for free)
- **Gemini API key** (get at https://makersuite.google.com/app/apikey)
- **Ngrok token** (get at https://dashboard.ngrok.com/signup)

### Step 6: Launch!
Starts your app and gives you the URL. Example:
```
✅ APP IS RUNNING!
🌐 URL: https://abc123.ngrok.io
```

**Click the URL** to access your app!

**Logs appear below** this cell in real-time.

### Step 7: Monitor (Optional)
Run anytime to check:
- GPU usage
- Database contents
- Number of meetings stored

---

## 📝 Usage Flow

Once app is running:

1. **Open URL** from Step 6
2. **Create meeting** in sidebar
3. **Upload documents** (PDF, DOCX, PPTX, TXT)
4. **Watch Colab logs** - should show embedding progress
5. **Generate brief** - Click button, wait ~10-30 seconds
6. **View brief** - Appears below Q&A section
7. **Ask questions** - Type in Q&A box

---

## 🔍 Monitoring Your App

### Watch Logs in Real-Time

After launching (Step 6), **scroll down** in that cell's output to see:

```
📋 LOGS (real-time):
--------------------------
INFO - Loading model...
INFO - GPU detected: Tesla T4
INFO - Encoding 150 chunks on GPU...
INFO - [Step 1] Recalling context
INFO - Retrieved 8 chunks
INFO - [Step 2] Synthesizing brief
OK - [Step 2] Brief synthesized
```

### Check GPU Usage

Run Step 7 anytime:
```python
!nvidia-smi
```

Look for Python process using GPU memory.

### Check Your Data

Also in Step 7:
```
📊 Database: 5 meetings
```

---

## 🐛 Troubleshooting

### GPU Not Detected
**Solution:**
1. Runtime → Change runtime type → GPU
2. Click "Save"
3. Rerun Step 1

### Project Not Found
**Solution:**
1. Upload hasn't finished
2. Make sure you uploaded the **entire folder** not individual files
3. Check folder is named `intelligence_copilot`

### Drive Mount Fails
**Solution:**
1. Click "Allow" when Google asks for permission
2. If still fails, run Step 2 again

### Dependencies Fail
**Solution:**
1. Check internet connection
2. Try: `%pip install --upgrade pip` first
3. Rerun Step 4

### Brief Not Generating
**Check Colab logs in Step 6 output:**
- Look for ERROR messages
- Common: JSON parse error (should be fixed now)
- Common: API key invalid

**Solutions:**
- If JSON error: Check `debug_json_error_*.txt` file
- If API error: Reenter API key (rerun Step 5)

### App Slow
**Check:**
- GPU enabled? (Step 1 should show GPU)
- Model loaded? (Should see in logs)
- Running on CPU? (much slower)

---

## 💡 Pro Tips

### Tip 1: Keep Logs Visible
Split your screen:
- Left: Colab with Step 6 output visible
- Right: Your app in browser

Watch logs update as you use the app!

### Tip 2: Data Persists
Your Google Drive storage means:
- Create meetings once
- Upload documents once
- Generate briefs anytime
- Data survives Colab restart

### Tip 3: Restart Sessions
If session times out:
1. Just rerun Steps 1-6
2. Your data is still in Drive!
3. Previous meetings load automatically

### Tip 4: Monitor Performance
Watch embedding speed in logs:
```
INFO - Encoding 150 chunks on GPU (batch_size=64)...
INFO - Encoded shape: (150, 384) on CUDA
```

Should take 1-2 seconds on GPU vs 15-30 seconds on CPU.

### Tip 5: Share the URL
The ngrok URL works for anyone:
- Share with team members
- They can access while your session runs
- Free tier: 40 connections/minute

---

## 📊 Performance Comparison

| Task | Original | Enhanced | Improvement |
|------|----------|----------|-------------|
| Setup time | 10 steps | 6 steps | Simpler |
| Data persistence | ❌ | ✅ | Major |
| Error debugging | Basic | Detailed | Better |
| GPU monitoring | Manual | Built-in | Easier |

---

## 🔄 Session Restart

If Colab disconnects (12-24 hours):

1. ✅ Your data is safe in Google Drive
2. ✅ Just click Runtime → Run all
3. ✅ Skip Drive mount if already mounted
4. ✅ Previous meetings load automatically

---

## ✅ Success Checklist

When running correctly, you should see:

- [ ] Step 1: "✅ GPU DETECTED"
- [ ] Step 2: "✅ PERSISTENT STORAGE CONFIGURED"
- [ ] Step 3: "✅ Working directory: /content/intelligence_copilot"
- [ ] Step 4: "✅ Dependencies installed!"
- [ ] Step 5: "✅ Configured: GEMINI + Ngrok"
- [ ] Step 6: "✅ APP IS RUNNING!" + ngrok URL
- [ ] Browser: App loads at ngrok URL
- [ ] App badge: "🚀 GPU Accelerated"

---

## 📚 Next Steps

1. **Test it now**: Run the notebook, upload a doc, generate brief
2. **Save to Drive**: Keep notebook in your Drive for easy access
3. **Bookmark ngrok signup**: You'll need it each session
4. **Try GPU monitor**: Run Step 7 while using app

---

## 🆘 Need Help?

1. **Check logs** in Step 6 cell output
2. **Run debug tools** in Step 7
3. **Look for ERROR messages** in logs
4. **Check files created**: `debug_json_error_*.txt`

---

**You're all set!** The enhanced notebook makes deployment easier and faster. Enjoy your GPU-accelerated Intelligence Copilot! 🚀

