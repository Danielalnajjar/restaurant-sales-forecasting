# Event Automation Quick Start

**One-page guide to automate event date research for your forecasting system.**

---

## 🚀 Quick Command

```bash
cd /home/ubuntu/forecasting
python scripts/research_events_simple.py --year 2027
```

**Runtime:** 2-3 minutes  
**Success rate:** 70-85% of events  
**Output:** `data/events/recurring_event_mapping_2025_2026_clean_with_2027.csv`

---

## 📋 Complete Workflow

### **Step 1: Run Automation**
```bash
python scripts/research_events_simple.py --year 2027
```

### **Step 2: Check Results**
```bash
# How many events were found?
python3 -c "import pandas as pd; \
df = pd.read_csv('data/events/recurring_event_mapping_2025_2026_clean_with_2027.csv'); \
print(f'{df[\"start_2027\"].notna().sum()}/{len(df)} events found')"
```

### **Step 3: Review & Fix**
Open the CSV file and:
- ✅ Verify major holidays (Memorial Day, Labor Day, Easter)
- ✅ Check convention dates against official websites
- ✅ Fill in missing events manually

### **Step 4: Finalize**
```bash
# Copy to main file
cp data/events/recurring_event_mapping_2025_2026_clean_with_2027.csv \
   data/events/recurring_event_mapping_2025_2026_clean.csv
```

### **Step 5: Update Config**
Edit `configs/config.yaml`:
```yaml
forecast_start: 2027-01-01
forecast_end: 2027-12-31
```

### **Step 6: Run Forecasting**
```bash
python -m src.forecasting.main
```

---

## 🎯 What You Need for 2027 Forecasts

| File | How to Get It |
|------|---------------|
| **Recurring events** | ✅ Automated (this script) |
| **Exact date events** | Create `events_2027_exact_dates_clean_v2.csv` |
| **Hours calendar** | Create `hours_calendar_2027_v2.csv` |
| **Hours overrides** | Create `hours_overrides_2027_v2.csv` |
| **2026 actuals** | Export from POS system |

---

## 🔧 Options

### **Adjust batch size** (smaller = more accurate)
```bash
python scripts/research_events_simple.py --year 2027 --batch-size 5
```

### **Custom input/output**
```bash
python scripts/research_events_simple.py \
  --year 2027 \
  --input data/events/my_events.csv \
  --output data/events/my_events_2027.csv
```

### **Deep Research** (more thorough, requires API key)
```bash
export GEMINI_API_KEY="your-key"
python scripts/automate_event_research.py --year 2027
```

---

## ⚠️ Important Notes

1. **Always verify results** - AI is 70-85% accurate, not 100%
2. **Check official sources** for major conventions
3. **Fill missing events** manually (typically 10-15 events)
4. **Run in late 2026** for best results (more dates announced)

---

## 📊 Time Savings

| Task | Manual | Automated |
|------|--------|-----------|
| Research 47 events | 2-3 hours | 2 minutes |
| Review & verify | 30 min | 30 min |
| Fill missing | 1 hour | 30 min |
| **Total** | **3-4 hours** | **~1 hour** |

**You save 2-3 hours!** ⏱️

---

## 🆘 Troubleshooting

**No results?**
- Check internet connection
- Try smaller batch size: `--batch-size 3`

**Low success rate (<50%)?**
- Re-run with `--batch-size 3`
- Use Deep Research option
- Manually research remaining events

**Wrong dates?**
- Always verify against official sources
- Correct manually in CSV file

---

## 📚 Full Documentation

See `documentation/AUTOMATED_EVENT_RESEARCH.md` for complete guide.

---

**Last Updated:** January 8, 2026
